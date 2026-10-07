package com.seventeen17.commerceagent.refund;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
import com.seventeen17.commerceagent.order.AfterSalesStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T021 / T027：受保护的退款写入 —— 本项目里第一个"钱真的会动"的服务。
 *
 * <p>它要同时守住四件事，缺任何一件都会造成真实损失：
 *
 * <ol>
 *   <li><b>归属</b>：退款只能由订单所有者发起。复用 {@link OrderService#requireOwnedOrderForUpdate}，因此越权与
 *       "订单不存在"对外完全不可区分（T019 的 concealment 口径在写路径上同样成立）。
 *   <li><b>资格与金额</b>：写入前**重新**跑一次确定性资格（T020）。调用方传来的任何"我之前查过可以退"都不算数，
 *       因为订单、物流与规则都可能已经变了。金额只取权威结论里的上界。
 *   <li><b>恰好一个逻辑退款</b>：幂等键重放返回同一笔；同订单的第二笔被拒绝。并发下靠订单行锁串行化，靠 V003 的
 *       两个唯一约束兜底。
 *   <li><b>可追溯</b>：退款行记录授权它的规则与 run_id，审计记录谁在什么时候退了多少（与业务写入同一事务提交，
 *       不会出现"审计说成功、业务回滚了"）。
 * </ol>
 *
 * <h2>请求处理顺序（每一步的顺序都有理由，不是随手写的）</h2>
 *
 * <pre>
 * 1. 能力校验（只有 CUSTOMER 能为自己发起退款）
 * 2. Idempotency-Key 形状校验 ............ 绝不带着垃圾参数进数据库
 * 3. V1 不接受的字段（任何 approval 引用）
 * 4. 幂等键快速重放 .................... 超时重试的常见路径，不该为读回一行而抢订单锁
 * 5. 锁订单行（owner 谓词在锁查询里）..... 并发写入在这里排队
 * 6. 拿到锁后**二次**检查幂等键 ......... 排队期间别人可能已经用同一个 key 提交了
 * 7. 订单售后状态 ....................... 已有售后 → DUPLICATE_AFTER_SALES（终端结论，先判更省事）
 * 8. 重新评估资格 ....................... DENY → ELIGIBILITY_DENIED；MANUAL_REVIEW → MANUAL_REVIEW_REQUIRED
 * 9. 金额必须等于授权全额 ............... V1 只做整单退款，超限 → AMOUNT_EXCEEDS_ALLOWED
 * 10. 同一事务写入：退款行 + 订单投影 + 审计
 * </pre>
 *
 * <h2>为什么第 5 步的锁和第 6 步的二次检查必须成对出现</h2>
 *
 * 只加锁不复查，等于只把并发请求排了队，排在后面的那个仍然会拿着"进入方法时读到的结论"继续往下写：那个结论是在
 * 别人提交之前得到的，它已经过期了。锁让检查不竞态，<b>复查</b>才让过期可见。这与 T017 在 resume 上的结论同源
 * （"`SELECT ... FOR UPDATE` 只把并发请求串行化；没有 version 比较时，第二个请求醒来后仍会按旧快照继续执行"）。
 */
@Service
public class RefundService {

    private static final String AUDIT_ACTION_REFUND_CREATED = "REFUND_CREATED";

    /**
     * 幂等键的字符集刻意不含点号、冒号与空白。
     *
     * <p>除了"机器生成的 key 不需要这些字符"之外，还有一个更硬的理由：key 会被持久化，而点号是 JWT 的形状特征。
     * 若允许任意字符，一个误把 token 当成 key 传进来的调用方就会让凭据落进退款表 —— 本项目在 T013/T015/T017 已经
     * 反复确认"凭据不得进入持久化状态"。限制字符集让"拿 token 当 key"这条路根本走不通。
     *
     * <p>下界 8 来自契约（{@code Idempotency-Key: minLength: 8}），上界 128 与数据库列宽一致。
     */
    private static final Pattern IDEMPOTENCY_KEY_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{8,128}$");

    /** V003 的两个唯一约束名。两者在 PostgreSQL 里都报 23505，只有约束名能区分"重放"与"第二笔退款"。 */
    private static final String IDEMPOTENCY_CONSTRAINT = "uq_refund_requests_user_idempotency_key";

    private static final String LIVE_REFUND_CONSTRAINT = "uq_refund_requests_order_id_active";

    private final OrderService orderService;
    private final OrderRepository orderRepository;
    private final EligibilityService eligibilityService;
    private final RefundRequestRepository refundRequestRepository;
    private final AuditWriter auditWriter;

    public RefundService(
            OrderService orderService,
            OrderRepository orderRepository,
            EligibilityService eligibilityService,
            RefundRequestRepository refundRequestRepository,
            AuditWriter auditWriter) {
        this.orderService = orderService;
        this.orderRepository = orderRepository;
        this.eligibilityService = eligibilityService;
        this.refundRequestRepository = refundRequestRepository;
        this.auditWriter = auditWriter;
    }

    /**
     * 创建一个逻辑退款。同一个 {@code idempotencyKey} 重复调用会返回**同一笔**退款，而不是第二笔。
     *
     * <p>返回值只包含权威事实（数据库里那一行的 id/状态/金额）。调用方（T031 的写后验证）必须再用
     * {@link #listRefunds} 读回一次，而不是相信自己是第一个知道结果的人。
     */
    @Transactional
    public RefundResult createRefund(CommercePrincipal principal, String idempotencyKey, RefundCommand command) {
        requireCustomerCapability(principal);
        String key = requireValidIdempotencyKey(idempotencyKey);
        requireRefundActionIsSupportedInThisVersion(command);

        RefundResult replayed = replayIfPresent(principal, key, command);
        if (replayed != null) {
            return replayed;
        }

        Order order = orderService.requireOwnedOrderForUpdate(principal, command.orderId());

        // 二次检查：等待订单锁期间，另一个请求可能已经用同一个 key 提交了退款。没有这一步，排队只会把竞态推迟到
        // 更靠后的位置，而不是消除它。
        replayed = replayIfPresent(principal, key, command);
        if (replayed != null) {
            return replayed;
        }

        if (order.getAfterSalesStatus() != null) {
            throw new BusinessException(
                    ErrorCode.DUPLICATE_AFTER_SALES,
                    "This order already has an after-sales action; a second refund would be a duplicate payment");
        }

        // 写前重校验：资格是"某一时刻"的结论，进入事务后必须重新计算一次，而不是相信上游传下来的快照。
        EligibilityDecision decision = eligibilityService.evaluate(principal, command.orderId());
        requireRefundAuthorized(decision);
        BigDecimal amount = requireAuthorizedWholeOrderAmount(command, decision.maxRefundAmount());

        RefundRequest refund = RefundRequest.create(
                newRefundId(),
                order.getId(),
                principal.userId(),
                command.reasonCode(),
                amount,
                key,
                decision.ruleCode(),
                // V1 没有权威审批记录可绑定；带审批引用的请求已在前面被拒绝，因此这里恒为 null。
                null,
                command.runId());

        persistRefund(refund);

        order.setAfterSalesStatus(AfterSalesStatus.REFUND_REQUESTED);
        orderRepository.saveAndFlush(order);

        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.USER,
                principal.userId(),
                AUDIT_ACTION_REFUND_CREATED,
                "REFUND",
                refund.getId(),
                UUID.fromString(command.runId()),
                "SUCCESS",
                Map.of(
                        "orderId", order.getId(),
                        "amount", amount.toPlainString(),
                        "ruleCode", decision.ruleCode())));
        // 幂等键刻意不进 metadata：它是调用方提供的任意字符串，已经在退款行里，审计只需指向那一行。

        return RefundResult.from(refund);
    }

    /**
     * 读回某订单的权威售后状态（退款部分）。
     *
     * <p>这是"未知写入结果恢复"的读面：写请求超时并不等于没提交，Agent 必须靠这里读回来的**已提交事实**判断，
     * 而不是换一个幂等键盲目重试。先过 ownership，因此越权读与"订单不存在"依旧不可区分。
     */
    @Transactional(readOnly = true)
    public List<RefundResult> listRefunds(CommercePrincipal principal, String orderId) {
        requireCustomerCapability(principal);
        orderService.getOrder(principal, orderId);
        return refundRequestRepository.findByOrderIdAndUserIdOrderByCreatedAtAsc(orderId, principal.userId()).stream()
                .map(RefundResult::from)
                .toList();
    }

    /**
     * 按逻辑写的 idempotency key 精确读回。这个重载专供 T022/T031 unknown-write recovery。
     *
     * <p>先验证订单 ownership，再校验 key 形状，然后用 user + order + key 三重谓词查退款。显式空列表表示：
     * 当前权威状态下，这个用户在这个订单上没有以该 key 提交过退款；它不能说明同一个 key 是否被用在别的订单。
     */
    @Transactional(readOnly = true)
    public List<RefundResult> listRefunds(CommercePrincipal principal, String orderId, String idempotencyKey) {
        requireCustomerCapability(principal);
        orderService.getOrder(principal, orderId);
        String key = requireValidIdempotencyKey(idempotencyKey);
        return refundRequestRepository
                .findByOrderIdAndUserIdAndIdempotencyKey(orderId, principal.userId(), key)
                .map(RefundResult::from)
                .stream()
                .toList();
    }

    /**
     * 只有客户能为自己发起退款。
     *
     * <p>这是一条**补偿性控制**，不是端点权限声明的替代品：T028 的控制器仍必须按角色限制端点。放在服务里的理由
     * 是"资金写入应当在最内层也无条件 fail closed"—— 将来某个新入口忘了加注解，这里仍然拦得住。
     */
    private static void requireCustomerCapability(CommercePrincipal principal) {
        if (principal.role() != UserRole.CUSTOMER) {
            throw new BusinessException(
                    ErrorCode.ACCESS_DENIED, "Only the owning customer may create a refund for their own order");
        }
    }

    private static String requireValidIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null
                || !IDEMPOTENCY_KEY_PATTERN.matcher(idempotencyKey).matches()) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER, "Idempotency-Key must be 8-128 characters of [A-Za-z0-9_-]");
        }
        return idempotencyKey;
    }

    /**
     * V1 无法校验任何审批引用，因此带审批引用的请求一律拒绝。
     *
     * <p>两种错误看起来都像"挑剔"，其实是在防一件具体的事：把无法验证的 approvalRequestId **原样存进退款行**，
     * 会让这张表里出现"看起来已获批准"的记录，而没有任何权威来源能证明它。宁可拒绝，也不留一条日后被误读的证据。
     */
    private static void requireRefundActionIsSupportedInThisVersion(RefundCommand command) {
        if (command.approvalRequestId() != null) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "This version cannot validate an approval reference, so it must not be presented");
        }
    }

    /**
     * 幂等重放判断。
     *
     * <p>指纹 = (orderId, amount, reasonCode)；<b>runId 不参与</b>。理由不是图省事：Agent 在 run 恢复后重试时
     * runId 可能不同，若它参与指纹，"恢复执行"会被判成 key 冲突 —— 恰好破坏 T031 最需要的那条恢复路径。
     * runId 是溯源信息，不是逻辑请求的身份。
     *
     * <p>金额比较对"省略金额"放宽：省略表示"按授权全额"，因此它与"显式写出当时算出的全额"等价；只有显式给出一个
     * **不同**的金额才算冲突。
     */
    private RefundResult replayIfPresent(CommercePrincipal principal, String key, RefundCommand command) {
        Optional<RefundRequest> existing =
                refundRequestRepository.findByUserIdAndIdempotencyKey(principal.userId(), key);
        if (existing.isEmpty()) {
            return null;
        }

        RefundRequest refund = existing.get();
        boolean sameOrder = refund.getOrderId().equals(command.orderId());
        boolean sameReason = refund.getReasonCode().equals(command.reasonCode());
        boolean sameAmount =
                !command.hasExplicitAmount() || command.requestedAmount().compareTo(refund.getAmount()) == 0;
        if (!sameOrder || !sameReason || !sameAmount) {
            throw new BusinessException(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "This Idempotency-Key was already used for a different refund request");
        }
        return RefundResult.from(refund);
    }

    /**
     * 把 T020 的确定性结论翻译成写路径的错误码。
     *
     * <p>这一步体现 T020 立下的规矩：**评估完成的拒绝是结论，不是异常**。只有在"要动这笔钱"的上下文中，拒绝才会
     * 变成错误码；而且三种拒绝的原因对 Agent 的含义完全不同 —— 证据不足要转人工，规则拒绝要解释，需要审批要先去
     * 拿审批，不能合成一个笼统的"不行"。
     */
    private static void requireRefundAuthorized(EligibilityDecision decision) {
        if (decision.eligible() && decision.allowedAction() == AllowedAction.REFUND_ONLY) {
            if (decision.approvalRequired()) {
                throw new BusinessException(
                        ErrorCode.APPROVAL_REQUIRED,
                        "Eligible, but an authoritative approval is required before this refund may be written");
            }
            return;
        }
        if (decision.allowedAction() == AllowedAction.MANUAL_REVIEW) {
            throw new BusinessException(
                    ErrorCode.MANUAL_REVIEW_REQUIRED,
                    "This case cannot be decided automatically; a human must decide it");
        }
        throw new BusinessException(
                ErrorCode.ELIGIBILITY_DENIED, "Deterministic after-sales rules deny a refund for this order");
    }

    /**
     * V1 只支持整单退款：省略金额表示"按授权全额"，显式给出时必须**正好等于**授权金额。
     *
     * <p>三种失败分开报：超过授权额是 {@code AMOUNT_EXCEEDS_ALLOWED}（契约里就是这个含义），少于是
     * {@code INVALID_PARAMETER}（本版本没有部分退款的表达，不是"你退得太少"）。刻意不做
     * {@code min(requested, authorized)} 这种静默取小：金额被服务端悄悄改掉，比明确报错危险得多。
     */
    private static BigDecimal requireAuthorizedWholeOrderAmount(RefundCommand command, BigDecimal authorizedAmount) {
        if (!command.hasExplicitAmount()) {
            return authorizedAmount;
        }
        int comparison = command.requestedAmount().compareTo(authorizedAmount);
        if (comparison > 0) {
            throw new BusinessException(
                    ErrorCode.AMOUNT_EXCEEDS_ALLOWED,
                    "Requested amount exceeds the amount the deterministic eligibility decision authorises");
        }
        if (comparison < 0) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "This version refunds the whole order only; a partial amount is not expressible yet");
        }
        return authorizedAmount;
    }

    /**
     * 落库退款行，并把唯一约束冲突翻译成确定的业务错误。
     *
     * <p>正常情况下走不到 catch 分支：行锁 + 二次幂等检查 + 订单状态检查已经覆盖了所有已知并发路径。它存在是因为
     * 约束是**最后一道防线**，而"最后一道防线被触发"这件事也应该有一个确定的对外语义：数据库报的是两个不同的
     * 23505，只有约束名能区分"同一个 key 被并发重放"与"同一订单被开了第二笔退款"。让它们逃逸成 500 会让一次并发
     * 重试看起来像服务端故障，Agent 于是会去重试一个永远不可能成功的请求。
     *
     * <p>未知约束名**不**翻译，直接向上抛：那说明有人在这个模型之外写了这张表，属于真实缺陷，必须响。
     */
    private void persistRefund(RefundRequest refund) {
        try {
            refundRequestRepository.saveAndFlush(refund);
        } catch (DataIntegrityViolationException exception) {
            String constraintName = constraintNameOf(exception);
            if (IDEMPOTENCY_CONSTRAINT.equals(constraintName)) {
                throw new BusinessException(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "This Idempotency-Key was committed concurrently by another request");
            }
            if (LIVE_REFUND_CONSTRAINT.equals(constraintName)) {
                throw new BusinessException(
                        ErrorCode.DUPLICATE_AFTER_SALES,
                        "A live refund already exists for this order; a second one would be a duplicate payment");
            }
            throw exception;
        }
    }

    private static String constraintNameOf(Throwable exception) {
        Throwable current = exception;
        while (current != null) {
            if (current instanceof ConstraintViolationException constraintViolation) {
                return constraintViolation.getConstraintName();
            }
            current = current.getCause();
        }
        return null;
    }

    /** 退款 id 用 UUIDv4：与 run_id 同理，随机 id 不需要靠 404 来隐藏存在性（T019 的判据是"能不能被猜"）。 */
    private static String newRefundId() {
        return UUID.randomUUID().toString();
    }
}
