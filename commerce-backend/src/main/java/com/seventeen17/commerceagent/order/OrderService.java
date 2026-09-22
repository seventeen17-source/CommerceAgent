package com.seventeen17.commerceagent.order;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T019：客户维度的订单读能力。
 *
 * <p>本类的重点不是"会查订单"，而是**把 ownership 收敛成唯一的判定点**：
 *
 * <ul>
 *   <li>所有读方法都接收 {@link CommercePrincipal} 而不是 {@code userId} 字符串。调用方无法自报身份：身份只能来
 *       自服务端解析过的 principal（JWT subject → 权威用户表，见 T011/T018）。
 *   <li>仓储层虽然已经提供 {@code findByIdAndOwnerId}，但 {@code JpaRepository} 自带的 {@code findById} 一直可
 *       用——**仓储方法名是约定，不是强制**。真正的把关在 {@link #requireOwnedOrder}。
 *   <li><b>"订单不存在"与"订单属于别人"对外完全不可区分</b>：同一个状态码、同一个
 *       {@link ErrorCode#ORDER_NOT_FOUND}、同一条 message。若对别人的订单单独回 403，攻击者就能靠状态码差异把哪些
 *       orderId 真实存在枚举出来（本系统的 id 形如 {@code order-001}，可枚举）。完整规则见
 *       {@code contracts/error-contracts.md} 的 Ownership Concealment Rule。
 *   <li><b>但"对外抹平"不等于"内部失明"</b>：cross-owner 读仍会被写成结构化安全审计，见
 *       {@link #auditConcealedCrossOwnerRead}。
 * </ul>
 */
@Service
@Transactional(readOnly = true)
public class OrderService {

    private static final Logger log = LoggerFactory.getLogger(OrderService.class);

    /**
     * 两条失败路径共用同一条消息。这不只是"省一个字符串"：任何措辞差异都会重新变成信息泄露通道，所以
     * {@code OrderLogisticsIntegrationTest} 直接断言两种情况下 {@code getMessage()} 逐字相同。
     */
    private static final String NOT_ACCESSIBLE_MESSAGE =
            "The order does not exist or is not accessible to the authenticated user";

    /**
     * 安全审计的 action：一次被拒绝的订单访问尝试。
     *
     * <p>刻意是 private：审计里出现的这两个字符串属于**对外可查询的契约**，所以测试直接断言字面量而不是引用常量
     * ——否则某天有人改了常量名，测试会跟着一起改，契约就悄悄漂移了。
     */
    private static final String AUDIT_ACTION_ORDER_ACCESS_DENIED = "ORDER_ACCESS_DENIED";

    /** 只在审计里出现的真实原因，绝不进入对外响应。 */
    private static final String AUDIT_REASON_CROSS_OWNER = "CROSS_OWNER";

    private final OrderRepository orderRepository;
    private final AuditWriter auditWriter;

    public OrderService(OrderRepository orderRepository, AuditWriter auditWriter) {
        this.orderRepository = orderRepository;
        this.auditWriter = auditWriter;
    }

    /**
     * 唯一的 ownership 判定入口。物流读能力
     * （{@link com.seventeen17.commerceagent.logistics.LogisticsService}）复用它，避免"什么算越权"在两个服务里
     * 各写一遍、然后慢慢漂移成两种语义。
     *
     * <p>它的代价要写明白：{@code Order} 实体因此跨包可见。V1 接受这个代价，因为调用方只读；一旦有调用方需要
     * 基于这个返回值写订单，写路径必须自己重新校验"当下仍然合法"，而不能复用这里"读的时候是合法的"这个结论。
     */
    public Order requireOwnedOrder(CommercePrincipal principal, String orderId) {
        Optional<Order> ownedOrder = orderRepository.findByIdAndOwnerId(orderId, principal.userId());
        if (ownedOrder.isPresent()) {
            return ownedOrder.get();
        }
        auditConcealedCrossOwnerRead(principal, orderId);
        throw notAccessible();
    }

    /**
     * 订单列表：ownership 直接进 SQL 谓词，所以返回的集合里**不可能**出现别人的订单——这是集合性质，比逐条检查
     * 单笔详情更强。
     *
     * <p>V1 刻意不支持 {@code productQuery} / {@code status} 过滤：那属于"候选订单解析"的查询形状，由 T030 用真实
     * 需求驱动（多候选打分、歧义检测），现在猜一个过滤语义只会写错。
     */
    public List<OrderSummary> listOwnOrders(CommercePrincipal principal) {
        return orderRepository.findByOwnerIdOrderByCreatedAtDesc(principal.userId()).stream()
                .map(OrderService::toSummary)
                .toList();
    }

    public OrderSnapshot getOrder(CommercePrincipal principal, String orderId) {
        return toSnapshot(requireOwnedOrder(principal, orderId));
    }

    /**
     * 把"查不到"进一步区分为"订单不存在"与"订单属于别人"，并把后者写成安全审计事件。
     *
     * <p><b>为什么用 {@code existsById} 而不是"按 id 查出订单再比 owner"：</b>前者只做一次存在性索引查询，不会把
     * 订单实体带进内存；{@code existsById} 也会在本方法的**两种失败情况下都执行**（不存在返回 false、
     * cross-owner 返回 true），避免最粗粒度的"一条路径少一次查询"差异。这里的安全承诺只到
     * status/errorCode/message concealment 为止，<b>不宣称 constant-time</b>：cross-owner 分支随后还会额外写一条
     * {@code REQUIRES_NEW} 安全审计，因此完整请求仍可能存在时序差异。
     *
     * <p><b>为什么只给 cross-owner 写审计：</b>普通 404（调用方打错 id、或 Agent 猜了一个不存在的单号）不是安全
     * 事件。为它写审计只会让一次 id 扫描把审计表刷爆，把真正值得追查的信号淹掉。
     *
     * <p><b>为什么审计失败要吞掉并降级为日志：</b>只有 cross-owner 这条路径会写审计。如果审计异常向上传播，
     * "审计子系统挂了 → 500"就重新变成一个可探测的信号，把刚刚在外层抹平的区别又泄露出去。请求本来就要被拒绝，
     * 此时丢掉的只是可观测性而不是业务动作，所以记录 ERROR 后继续抛出统一的 ORDER_NOT_FOUND。
     */
    private void auditConcealedCrossOwnerRead(CommercePrincipal principal, String orderId) {
        if (!orderRepository.existsById(orderId)) {
            return;
        }
        try {
            auditWriter.writeSecurityEvent(new AuditEvent(
                    AuditActorType.USER,
                    principal.userId(),
                    AUDIT_ACTION_ORDER_ACCESS_DENIED,
                    "ORDER",
                    orderId,
                    null,
                    "DENIED",
                    Map.of("reason", AUDIT_REASON_CROSS_OWNER, "concealedAs", ErrorCode.ORDER_NOT_FOUND.name())));
        } catch (RuntimeException exception) {
            log.error(
                    "Failed to record concealed cross-owner read denial actorId={} orderId={}",
                    principal.userId(),
                    orderId,
                    exception);
        }
    }

    private static BusinessException notAccessible() {
        return new BusinessException(ErrorCode.ORDER_NOT_FOUND, NOT_ACCESSIBLE_MESSAGE);
    }

    private static OrderSummary toSummary(Order order) {
        return new OrderSummary(order.getId(), summarizeProducts(order), order.getStatus(), order.getCreatedAt());
    }

    private static OrderSnapshot toSnapshot(Order order) {
        List<OrderSnapshot.Item> items = order.getItems().stream()
                .map(item -> new OrderSnapshot.Item(
                        item.getProductId(), item.getProductName(), item.getProductCategory(), item.getQuantity()))
                .toList();
        return new OrderSnapshot(
                order.getId(),
                order.getStatus(),
                order.getTotalAmount(),
                order.getCurrency(),
                order.getAfterSalesStatus(),
                items);
    }

    /**
     * 列表里只给一行摘要：单品直接给名字，多品给"首件 等 N 件"。
     *
     * <p>它只是帮助用户/Agent 定位订单的展示文案，不是权威数据——Agent 不得据此判断类目、金额或资格。
     */
    private static String summarizeProducts(Order order) {
        List<OrderItem> items = order.getItems();
        if (items.isEmpty()) {
            return "";
        }
        String firstProductName = items.get(0).getProductName();
        return items.size() == 1 ? firstProductName : firstProductName + " 等 " + items.size() + " 件";
    }
}
