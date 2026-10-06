package com.seventeen17.commerceagent.returns;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
import com.seventeen17.commerceagent.logistics.LogisticsService;
import com.seventeen17.commerceagent.order.AfterSalesStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T040：受保护的退货写入，以及它的权威状态读面。US2 的"已签收商品改走退货"在这里第一次真的落盘。
 *
 * <p>它与 {@code RefundService} 刻意对称，因为两者面对的是同一类风险：一个有副作用的写、一个可能被重放的调用方、
 * 以及"钱/商品状态不能出现第二笔"的硬要求。四条纪律逐条照搬：
 *
 * <ol>
 *   <li><b>写前重校验</b>：资格是"某一时刻"的结论。进入事务后重新 {@code evaluate} 一次，而不是相信上游传来的
 *       快照 —— 否则"评估时合格、提交时不合格"会静默落库。
 *   <li><b>锁 + 复查</b>：先取订单行锁（ownership 写在锁查询自己的 WHERE 里），拿到锁之后再查一次幂等键。只加锁
 *       不复查，等于把并发请求排了队却让后面的那个拿着过期结论继续写（T017/T021 的同一个结论）。
 *   <li><b>数据库兜底</b>：V004 的两条唯一约束才是最终保证；服务把 23505 按<b>约束名</b>翻译成确定业务错误，
 *       未知约束名原样上抛（那说明有人绕过这个模型写表，属于真实缺陷）。
 *   <li><b>状态与审计同事务</b>：订单投影 {@code RETURN_REQUESTED}、退货行、审计在同一事务里提交，不出现
 *       "审计说成功、业务回滚了"的假 SUCCESS。
 * </ol>
 *
 * <p><b>本任务刻意不做的事</b>：{@code RETURN_REFUND} 的"退款"这一半不在 {@code POST /returns} 里发生。退货行
 * 表达的是"这件商品在走退货流程"，钱仍然只能由退款行表达（V004 刻意没有金额列）。让退款去引用一笔<b>活动退货行</b>
 * 才是正确的长期形态，那属于后续任务；本次绝不放宽 {@code RefundService} 的 {@code REFUND_ONLY} 授权守卫 ——
 * 放宽它等于把"已签收订单被直接退款"这件事重新放回来。
 */
@Service
public class ReturnService {

    private static final String AUDIT_ACTION_RETURN_CREATED = "RETURN_CREATED";

    /**
     * 幂等键的字符集与退款侧完全一致（下界 8 来自契约 {@code Idempotency-Key: minLength: 8}）。
     *
     * <p>不含点号、冒号与空白不是审美：key 会被持久化，而点号是 JWT 的形状特征。限制字符集让"把一个 token
     * 误当 key 传进来"这条路根本走不通（T013/T015/T017 反复确认"凭据不得进入持久化状态"）。
     */
    private static final Pattern IDEMPOTENCY_KEY_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{8,128}$");

    /** V004 的两个唯一约束名。两者在 PostgreSQL 里都报 23505，只有约束名能区分"重放"与"第二笔退货"。 */
    private static final String IDEMPOTENCY_CONSTRAINT = "uq_return_requests_user_idempotency_key";

    private static final String LIVE_RETURN_CONSTRAINT = "uq_return_requests_order_id_active";

    private final OrderService orderService;
    private final OrderRepository orderRepository;
    private final EligibilityService eligibilityService;
    private final AfterSalesRuleRepository ruleRepository;
    private final LogisticsService logisticsService;
    private final ReturnRequestRepository returnRequestRepository;
    private final AuditWriter auditWriter;

    public ReturnService(
            OrderService orderService,
            OrderRepository orderRepository,
            EligibilityService eligibilityService,
            AfterSalesRuleRepository ruleRepository,
            LogisticsService logisticsService,
            ReturnRequestRepository returnRequestRepository,
            AuditWriter auditWriter) {
        this.orderService = orderService;
        this.orderRepository = orderRepository;
        this.eligibilityService = eligibilityService;
        this.ruleRepository = ruleRepository;
        this.logisticsService = logisticsService;
        this.returnRequestRepository = returnRequestRepository;
        this.auditWriter = auditWriter;
    }

    /**
     * 创建一笔逻辑退货。同一个 {@code idempotencyKey} 重复调用会返回**同一笔**退货，而不是第二笔。
     *
     * <p>返回值只包含权威事实（数据库里那一行的 id/状态/冻结的截止日）。调用方（写后验证）必须再用
     * {@link #listReturns} 读回一次，而不是相信自己是第一个知道结果的人。
     */
    @Transactional
    public ReturnResult createReturn(CommercePrincipal principal, String idempotencyKey, ReturnCommand command) {
        requireCustomerCapability(principal);
        String key = requireValidIdempotencyKey(idempotencyKey);
        requireReturnActionIsSupportedInThisVersion(command);

        // 订单行锁：ownership 写在这条查询自己的 WHERE 里，因此"不是你的"与"不存在"在这里就已经不可区分。
        Order order = orderService.requireOwnedOrderForUpdate(principal, command.orderId());

        // 锁后复查：等待锁期间，另一个请求可能已经用同一个 key 提交了。没有这一步，排队只是把竞态推迟。
        ReturnResult replayed = replayIfPresent(principal, key, command);
        if (replayed != null) {
            return replayed;
        }

        if (order.getAfterSalesStatus() != null) {
            throw new BusinessException(
                    ErrorCode.DUPLICATE_AFTER_SALES,
                    "This order already has an after-sales action; a second return would be a duplicate");
        }

        // 写前重校验：结论必须来自当下的权威事实，而不是上游传下来的快照。
        EligibilityDecision decision = eligibilityService.evaluate(principal, command.orderId());
        requireReturnAuthorized(decision);
        Instant returnDeadline = frozenReturnDeadline(principal, command.orderId(), decision);

        ReturnRequest request = ReturnRequest.create(
                newReturnId(),
                order.getId(),
                principal.userId(),
                command.reasonCode(),
                command.returnMethod(),
                key,
                decision.ruleCode(),
                // V1 没有权威审批记录可绑定；带审批引用的请求已在前面被拒绝，因此这里恒为 null。
                null,
                command.runId(),
                returnDeadline);

        persistReturn(request);

        order.setAfterSalesStatus(AfterSalesStatus.RETURN_REQUESTED);
        orderRepository.saveAndFlush(order);

        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.USER,
                principal.userId(),
                AUDIT_ACTION_RETURN_CREATED,
                "RETURN",
                request.getId(),
                UUID.fromString(command.runId()),
                "SUCCESS",
                Map.of(
                        "orderId", order.getId(),
                        "ruleCode", decision.ruleCode(),
                        "returnDeadline", returnDeadline.toString())));
        // 幂等键刻意不进 metadata：它是调用方提供的任意字符串，已经在退货行里，审计只需指向那一行。

        return ReturnResult.from(request);
    }

    /**
     * 读回某订单的权威退货状态。
     *
     * <p>这是"未知写入结果恢复"的读面：写请求超时并不等于没提交，调用方必须靠这里读回来的**已提交事实**判断，
     * 而不是换一个幂等键盲目重试。先过 ownership，因此越权读与"订单不存在"依旧不可区分。
     */
    @Transactional(readOnly = true)
    public List<ReturnResult> listReturns(CommercePrincipal principal, String orderId) {
        requireCustomerCapability(principal);
        orderService.getOrder(principal, orderId);
        return returnRequestRepository.findByOrderIdAndUserIdOrderByCreatedAtAsc(orderId, principal.userId()).stream()
                .map(ReturnResult::from)
                .toList();
    }

    /**
     * 按逻辑写的 idempotency key 精确读回（供写后验证与 unknown-write recovery）。
     *
     * <p>先验证订单 ownership，再校验 key 形状，然后用 user + order + key 三重谓词查退货。显式空列表表示：
     * 当前权威状态下，这个用户在这个订单上没有以该 key 提交过退货。
     */
    @Transactional(readOnly = true)
    public List<ReturnResult> listReturns(CommercePrincipal principal, String orderId, String idempotencyKey) {
        requireCustomerCapability(principal);
        orderService.getOrder(principal, orderId);
        String key = requireValidIdempotencyKey(idempotencyKey);
        return returnRequestRepository
                .findByOrderIdAndUserIdAndIdempotencyKey(orderId, principal.userId(), key)
                .map(ReturnResult::from)
                .stream()
                .toList();
    }

    /**
     * 冻结对客户的截止日。
     *
     * <p>它把决策已经据以放行的两件事重新读一次（规则行、运单签收时刻），用**同一个**窗口算术
     * （{@link EligibilityService#returnDeadline}）算出截止时刻，然后写进那一行。为什么要读第二次而不是让决策
     * 带回来：{@code EligibilityDecision} 是对外契约的一部分，为写路径塞一个只被写路径用到的字段，会同时改到
     * 消费端（Python 的 {@code EligibilitySnapshot}）。重新读的代价是同一事务里两次查询，换来的是契约不动、
     * 而窗口算术仍然只有一处。
     *
     * <p>算不出来时<b>不猜</b>也不写半截行：决策刚刚基于同样的事实放行，此处的 {@code null} 只能说明事实在
     * 评估与提交之间变了，因此按可重试的依赖问题上报（503），而不是编一个截止日。
     */
    private Instant frozenReturnDeadline(CommercePrincipal principal, String orderId, EligibilityDecision decision) {
        AfterSalesRule rule = ruleRepository
                .findByRuleCodeAndVersion(decision.ruleCode(), decision.ruleVersion())
                .orElseThrow(() -> new BusinessException(
                        ErrorCode.INTERNAL_ERROR, "The authorising rule row disappeared before commit"));
        Instant deadline = EligibilityService.returnDeadline(logisticsService.getLogistics(principal, orderId), rule);
        if (deadline == null) {
            throw new BusinessException(
                    ErrorCode.LOGISTICS_UNAVAILABLE,
                    "The return window could not be frozen: authoritative signed-at evidence is unavailable");
        }
        return deadline;
    }

    /**
     * 只有客户能为自己发起退货。
     *
     * <p>与退款侧同一条**补偿性控制**：端点权限注解仍然是第一道闸，但资金/商品状态相关的写入应当在最内层也
     * 无条件 fail closed —— 将来某个新入口忘了加注解，这里仍然拦得住。
     */
    private static void requireCustomerCapability(CommercePrincipal principal) {
        if (principal.role() != UserRole.CUSTOMER) {
            throw new BusinessException(
                    ErrorCode.ACCESS_DENIED, "Only the owning customer may create a return for their own order");
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
     * <p>与退款侧同样的理由：把无法验证的 {@code approvalRequestId} 原样存进退货行，会让这张表里出现"看起来
     * 已获批准"的记录，而没有任何权威来源能证明它。宁可拒绝，也不留一条日后被误读的证据。
     */
    private static void requireReturnActionIsSupportedInThisVersion(ReturnCommand command) {
        if (command.approvalRequestId() != null) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "This version cannot validate an approval reference, so it must not be presented");
        }
    }

    /**
     * 幂等重放判断。
     *
     * <p>指纹 = (orderId, reasonCode, returnMethod)；{@code runId} 不参与，理由与退款侧相同：Agent 在 run 恢复
     * 后重试时 runId 可能不同，若它参与指纹，"恢复执行"会被判成 key 冲突 —— 恰好破坏最需要的那条恢复路径。
     * runId 是溯源信息，不是逻辑请求的身份。
     *
     * <p>这是 {@code return_method} 必须落库的原因：判断"是不是同一次逻辑请求"的字段，必须能与第一次尝试存下来
     * 的值比较。
     */
    private ReturnResult replayIfPresent(CommercePrincipal principal, String key, ReturnCommand command) {
        Optional<ReturnRequest> existing =
                returnRequestRepository.findByUserIdAndIdempotencyKey(principal.userId(), key);
        if (existing.isEmpty()) {
            return null;
        }

        ReturnRequest request = existing.get();
        boolean sameOrder = request.getOrderId().equals(command.orderId());
        boolean sameReason = request.getReasonCode().equals(command.reasonCode());
        boolean sameMethod = Objects.equals(request.getReturnMethod(), command.returnMethod());
        if (!sameOrder || !sameReason || !sameMethod) {
            throw new BusinessException(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "This Idempotency-Key was already used for a different return request");
        }
        return ReturnResult.from(request);
    }

    /**
     * 把 T039 的确定性结论翻译成写路径的错误码。
     *
     * <p>沿用 T020/T021 立下的分界：**评估完成的拒绝是结论，不是异常**；只有在"要动这笔售后"的上下文里，拒绝
     * 才变成错误码。三种不批准对调用方的含义完全不同 —— 证据不足要转人工、规则拒绝要解释、需要审批要先去拿审批，
     * 不能合成一个笼统的"不行"。
     *
     * <p>注意 US2 守卫（已签收订单不得被授予直接退款）走的是 {@code DENY} 分支 → {@code ELIGIBILITY_DENIED}：
     * 一张已签收订单即使被某条规则写成 {@code REFUND_ONLY}，也无法在这里拿到退货之外的授权。
     */
    private static void requireReturnAuthorized(EligibilityDecision decision) {
        if (decision.eligible()
                && (decision.allowedAction() == AllowedAction.RETURN
                        || decision.allowedAction() == AllowedAction.RETURN_REFUND)) {
            if (decision.approvalRequired()) {
                throw new BusinessException(
                        ErrorCode.APPROVAL_REQUIRED,
                        "Eligible, but an authoritative approval is required before this return may be written");
            }
            return;
        }
        if (decision.allowedAction() == AllowedAction.MANUAL_REVIEW) {
            throw new BusinessException(
                    ErrorCode.MANUAL_REVIEW_REQUIRED,
                    "This case cannot be decided automatically; a human must decide it");
        }
        throw new BusinessException(
                ErrorCode.ELIGIBILITY_DENIED,
                "Deterministic after-sales rules do not authorise a return for this order");
    }

    /**
     * 落库退货行，并把唯一约束冲突翻译成确定的业务错误。
     *
     * <p>正常情况下走不到 catch 分支：行锁 + 二次幂等检查 + 订单状态检查已覆盖所有已知并发路径。它存在是因为
     * 约束是**最后一道防线**，而"最后一道防线被触发"也该有确定的对外语义：数据库报的是两个不同的 23505，只有
     * 约束名能区分"同一个 key 被并发重放"与"同一订单被开了第二笔退货"。让它们逃逸成 500 会让一次并发重试看起来
     * 像服务端故障，调用方于是去重试一个永远不可能成功的请求。
     */
    private void persistReturn(ReturnRequest request) {
        try {
            returnRequestRepository.saveAndFlush(request);
        } catch (DataIntegrityViolationException exception) {
            String constraintName = constraintNameOf(exception);
            if (IDEMPOTENCY_CONSTRAINT.equals(constraintName)) {
                throw new BusinessException(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "This Idempotency-Key was committed concurrently by another request");
            }
            if (LIVE_RETURN_CONSTRAINT.equals(constraintName)) {
                throw new BusinessException(
                        ErrorCode.DUPLICATE_AFTER_SALES,
                        "A live return already exists for this order; a second one would be a duplicate");
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

    /** 退货 id 用 UUIDv4：与 run_id 同理，随机 id 不需要靠 404 隐藏存在性（T019 的判据是"能不能被猜"）。 */
    private static String newReturnId() {
        return UUID.randomUUID().toString();
    }
}
