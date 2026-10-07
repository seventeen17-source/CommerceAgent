package com.seventeen17.commerceagent.eligibility;

import com.seventeen17.commerceagent.logistics.LogisticsService;
import com.seventeen17.commerceagent.logistics.LogisticsSnapshot;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.order.OrderSnapshot;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T020：确定性退款/退货资格判定。
 *
 * <p>这是本项目里"钱能不能动"的第一道权威闸门（spec FR-009/FR-010）。它被拆成两层，拆法本身就是设计的一部分：
 *
 * <ul>
 *   <li>{@link #evaluate} —— <b>I/O 外壳</b>：过 ownership、读规则行、按需读物流事实；
 *   <li>{@link #selectRule} / {@link #decide} —— <b>纯函数</b>：只依赖传入的权威事实，不读时钟、不查库、
 *       不调用其它服务。
 * </ul>
 *
 * <p>为什么要这样拆：面试里"确定性"经常只是一句形容词。把决策写成纯函数之后，它可以被逐条断言（见
 * {@code EligibilityServiceTest}），而"同输入必得同输出"也就有了可执行的证据，不再依赖"代码读起来没有随机
 * 数"。时间同样从外部传入（{@code now} 来自注入的 {@link Clock}），因此规则生效窗口与审批阈值这类和时间有关
 * 的判断也能被精确测试，而不是写成"大概吧"。
 *
 * <p>三个刻意选择的边界：
 *
 * <ol>
 *   <li><b>不读契约里的 reasonCode。</b>用户或模型给的理由是**描述性**输入，不参与规则选择与金额计算。如果
 *       它可以影响结论，那么"用措辞换个说法"就成了一条绕过规则的路径 —— 这正是 FR-009 要防的事。
 *   <li><b>只收集规则要求的证据。</b>规则没有声明停滞阈值时不会去读物流；否则一个不需要物流的规则会被一次
 *       物流依赖故障拖成 503，把本来能确定性回答的问题变成失败。
 *   <li><b>"证明不符合"与"无法证明符合"分开。</b>前者 {@code DENY}，后者 {@code MANUAL_REVIEW}，两者都
 *       不动钱，但 Agent 的后续动作完全不同（解释拒绝 vs 转人工）。把它们合并成一种"不批准"，会让 US5 的
 *       人工升级路径失去触发依据。
 * </ol>
 *
 * <p>规则选择本身也是确定性的：先按类目与订单状态筛出候选，再要求候选只属于**同一个 ruleCode**，最后取版本号
 * 最大的那条。两个不同 ruleCode 同时匹配同一订单时不会"任选一条"，而是转人工 —— 任意选一条等于让 seed 数据的
 * 插入顺序决定用户能退多少钱。
 */
@Service
@Transactional(readOnly = true)
public class EligibilityService {

    private final OrderService orderService;
    private final LogisticsService logisticsService;
    private final AfterSalesRuleRepository ruleRepository;
    private final Clock clock;

    public EligibilityService(
            OrderService orderService,
            LogisticsService logisticsService,
            AfterSalesRuleRepository ruleRepository,
            Clock clock) {
        this.orderService = orderService;
        this.logisticsService = logisticsService;
        this.ruleRepository = ruleRepository;
        this.clock = clock;
    }

    /**
     * 对某个订单做一次确定性资格评估。
     *
     * <p>ownership 复用 {@link OrderService#getOrder}，因此"订单不存在"与"订单属于别人"对外依旧是同一个
     * {@code 404 ORDER_NOT_FOUND}（T019 的 concealment 口径）。eligibility 是一个新的读入口，如果它自己写一遍
     * 归属判断，就会成为绕过该口径的第二条路径。
     *
     * <p>失败语义与决策语义的分界：**评估无法完成**（越权、依赖不可用、订单状态与规则前提冲突）抛异常；
     * **评估完成但结论是不批准**返回 {@code eligible=false} 的决策，由 reason 码说明原因。
     */
    public EligibilityDecision evaluate(CommercePrincipal principal, String orderId) {
        OrderSnapshot order = orderService.getOrder(principal, orderId);
        Instant now = clock.instant();

        RuleSelection selection = selectRule(order, ruleRepository.findByActiveTrue(), now);
        LogisticsSnapshot logistics =
                needsLogisticsFacts(order, selection) ? logisticsService.getLogistics(principal, orderId) : null;

        return decide(order, selection, logistics, now);
    }

    /** 现在管这个订单的是哪条规则，或者为什么没有规则可选。纯函数，不读时钟（{@code now} 由调用方给出）。 */
    static RuleSelection selectRule(OrderSnapshot order, List<AfterSalesRule> rules, Instant now) {
        List<AfterSalesRule> categoryMatches = rules.stream()
                .filter(AfterSalesRule::isActive)
                .filter(rule -> isEffectiveAt(rule, now))
                .filter(rule -> matchesCategory(rule, order))
                .toList();
        if (categoryMatches.isEmpty()) {
            return RuleSelection.notSelected(RuleSelection.Status.NO_APPLICABLE_RULE);
        }

        List<AfterSalesRule> statusMatches = categoryMatches.stream()
                .filter(rule -> matchesOrderStatus(rule, order))
                .toList();
        if (statusMatches.isEmpty()) {
            return RuleSelection.notSelected(RuleSelection.Status.ORDER_STATE_NOT_ELIGIBLE);
        }

        Set<String> distinctRuleCodes =
                statusMatches.stream().map(AfterSalesRule::getRuleCode).collect(Collectors.toSet());
        if (distinctRuleCodes.size() > 1) {
            return RuleSelection.notSelected(RuleSelection.Status.CONFLICTING_RULES);
        }

        // 同一 ruleCode 的多个版本是正常的历史版本共存（V001 的唯一约束是 code + version），取最新版本。
        // 版本号在 (rule_code, version) 唯一约束下不可能相同，因此这里没有"再随机挑一个"的空间。
        AfterSalesRule newest = statusMatches.stream()
                .max(Comparator.comparingInt(AfterSalesRule::getVersion))
                .orElseThrow(() -> new IllegalStateException("a non-empty candidate list must have a newest version"));
        return RuleSelection.selected(newest);
    }

    /**
     * 是否必须先去读物流事实。
     *
     * <p>判据必须与 {@link #decide} 里的前置检查保持一致，否则会出现"外壳以为不需要读、决策层却要求非空"的
     * 断言失败。三个条件缺一不可：规则已选中、订单尚无售后动作（已有售后是终止性结论，不需要更多证据）、规则
     * 确实声明了停滞阈值且动作是需要物流证据的退款。
     */
    static boolean needsLogisticsFacts(OrderSnapshot order, RuleSelection selection) {
        if (!selection.isSelected() || order.afterSalesStatus() != null) {
            return false;
        }
        // 已签收订单不能被授予直接退款（判据与 decide 里那道守卫是同一个函数，见
        // deliveredOrderCannotTakeADirectRefund）。这条路径因此不需要物流事实：去读一次只会把一次确定性的拒绝
        // 变成一次依赖故障（503），把客户本来能得到答案的问题变成失败。
        if (deliveredOrderCannotTakeADirectRefund(order, selection.rule().getAllowedAction())) {
            return false;
        }
        // REFUND_ONLY 要的是停滞证据；RETURN / RETURN_REFUND 要的是签收时刻（退货窗口的起算点）。
        // 漏掉后者会让退货永远拿到 null 快照 → 每个退货都变成 RETURN_WINDOW_UNKNOWN：
        // 测试可能全绿，而功能在真实环境里是死的。
        return switch (selection.rule().getAllowedAction()) {
            case REFUND_ONLY -> selection.rule().getLogisticsStalledHours() != null;
            case RETURN, RETURN_REFUND -> selection.rule().getReturnWindowDays() != null;
            default -> false;
        };
    }

    /**
     * T036 / US2 不变量：一张**已经签收**的订单，不能被授予"直接退款"这个动作。
     *
     * <p>规则行是配置，配置可以写错；服务端不能照做。判据因此在代码里，而不是寄托于"seed 数据里没有这种规则"
     * —— 一条写着 {@code REFUND_ONLY} 且匹配 {@code DELIVERED} 的规则行本身与产品不变量冲突，必须在决策层
     * 被拦下。
     *
     * <p>判据取**订单的生命周期状态**（权威、一定有值），不取运单：这里可能压根没有运单行，而"签收"在本仓库
     * 别处也是 {@code signedAt != null || status == DELIVERED}（见 {@code LogisticsStallCalculator.isSigned}）。
     *
     * <p>它是**唯一判据**，被外壳（要不要读物流）与决策层（产出哪个原因码）共用 —— 两处各写一遍条件迟早会
     * 漂移，而漂移的后果正是 {@link #needsLogisticsFacts} 注释里警告过的那种断言失败。
     */
    static boolean deliveredOrderCannotTakeADirectRefund(OrderSnapshot order, AllowedAction action) {
        return action == AllowedAction.REFUND_ONLY && order.status() == OrderStatus.DELIVERED;
    }

    /**
     * T039 / T040：退货窗口的截止时刻 —— 规则声明的窗口天数，从运单的签收时刻起算。
     *
     * <p>它是**唯一**的窗口算术：决策层用它判断"还来不来得及"（{@link #decide} 的 RETURN 分支），写路径
     * （T040 的 {@code ReturnService}）用它冻结对客户的承诺。两处各算一遍的后果不是重复代码，而是
     * "据以拒绝的窗口"与"已经承诺给客户的窗口"可以悄悄不一致。
     *
     * <p>两个事实缺一不可，缺任何一个返回 {@code null}：规则没有声明窗口，或拿不到签收时刻。调用方必须把它
     * 当作"算不出来"，而不是回落到订单状态自己编一个起点 —— 那正是 T039 拒绝使用
     * {@code orders.delivered_at} 的理由（那一列没有任何生产写入路径）。
     *
     * <p>它是 {@code public} 的，因为写路径（{@code returns.ReturnService}）也要用它 —— 这是唯一一处允许跨包
     * 复用的决策算术；把它私有化就等于逼写路径自己抄一遍公式。
     */
    public static Instant returnDeadline(LogisticsSnapshot logistics, AfterSalesRule rule) {
        Integer windowDays = rule.getReturnWindowDays();
        if (windowDays == null || logistics == null || logistics.signedAt() == null) {
            return null;
        }
        return logistics.signedAt().plus(windowDays, ChronoUnit.DAYS);
    }

    /**
     * 纯决策函数：把权威事实翻译成资格结论。
     *
     * <p>{@code logistics} 可以为 {@code null}，但**仅当**被选中的规则没有声明停滞阈值时。若规则要求停滞证据
     * 而调用方没给（说明 {@link #needsLogisticsFacts} 与这里漂移了），这里直接抛 {@link IllegalArgumentException}
     * 而不是编一个"没有证据"的结论：那是实现缺陷，不该被伪装成一个业务结果。
     */
    static EligibilityDecision decide(
            OrderSnapshot order, RuleSelection selection, LogisticsSnapshot logistics, Instant now) {
        if (!selection.isSelected()) {
            return unresolved(selection, now);
        }

        AfterSalesRule rule = selection.rule();

        // 已有的售后动作是终止性结论，必须先判：否则一次物流依赖故障会把这个"本来就该拒绝"的请求变成 503，
        // 让 Agent 去重试一个永远不会有结果的依赖。
        if (order.afterSalesStatus() != null) {
            return denied(rule, EligibilityReasonCode.ORDER_ALREADY_HAS_AFTER_SALES, now);
        }

        switch (rule.getAllowedAction()) {
            case DENY -> {
                return denied(rule, EligibilityReasonCode.RULE_ACTION_DENY, now);
            }
            case MANUAL_REVIEW -> {
                return manualReview(rule, EligibilityReasonCode.RULE_ACTION_MANUAL_REVIEW, now);
            }
            case RETURN, RETURN_REFUND -> {
                // T039：退货窗口。判据只依赖两件已经存在的权威事实 —— 规则声明的窗口天数，以及运单的签收
                // 时刻（本仓库自己的"已签收"判据也用它）。它回答的是"还来不来得及"，而不是"能不能"。
                Integer returnWindowDays = rule.getReturnWindowDays();
                if (returnWindowDays == null) {
                    // 规则声称可以退货却没声明窗口：这是配置问题，不是客户的错，所以转人工而不是拒绝。
                    return manualReview(rule, EligibilityReasonCode.RULE_ACTION_NOT_SUPPORTED, now);
                }
                if (logistics == null || logistics.signedAt() == null) {
                    // 拿不到签收时刻时【不猜】：窗口算不出来就明确说算不出来 —— 与"过了窗口"是两件事，
                    // 因此用不同的原因码，好让数据缺口被看见，而不是被伪装成一个业务结论。
                    return denied(rule, EligibilityReasonCode.RETURN_WINDOW_UNKNOWN, now);
                }
                // 截止时刻只在一个地方算（returnDeadline）：判定用它、T040 写给客户的承诺也用它，否则
                // "我们据以拒绝的窗口"与"我们承诺出去的窗口"会各自演化。
                if (returnDeadline(logistics, rule).isBefore(now)) {
                    return denied(rule, EligibilityReasonCode.RETURN_WINDOW_EXPIRED, now);
                }
                // 窗口内：这里不 return，贯穿到下面的金额与审批校验 —— RETURN_REFUND 同样会动钱，那两道闸
                // 必须一样过。另注意：退货规则不得声明 logistics_stalled_hours，否则已签收运单会让停滞分支
                // 命中 LOGISTICS_CONFLICTS_WITH_ORDER 而转人工。
            }
            case REFUND_ONLY -> {
                // US2 守卫必须排在下面的停滞检查之前：对一张已签收的订单，"停滞时长够不够"根本没有意义，
                // 先回答那个问题只会给出一条误导性的原因码 —— LOGISTICS_CONFLICTS_WITH_ORDER 描述的是
                // "订单说 SHIPPED、运单说已签收"，而这里的订单自己就说 DELIVERED。
                if (deliveredOrderCannotTakeADirectRefund(order, rule.getAllowedAction())) {
                    return denied(rule, EligibilityReasonCode.DELIVERED_ORDER_IS_RETURN_ONLY, now);
                }
                // 继续做退款所需的证据与金额校验。
            }
            default -> throw new IllegalStateException("Unhandled allowed action: " + rule.getAllowedAction());
        }

        List<EligibilityReasonCode> reasons = new ArrayList<>();

        Integer stallThresholdHours = rule.getLogisticsStalledHours();
        if (stallThresholdHours != null) {
            if (logistics == null) {
                throw new IllegalArgumentException(
                        "logistics facts are required when the selected rule declares a stall threshold");
            }
            if (logistics.signed()) {
                // 订单行说 SHIPPED，运单说已签收：两个权威来源冲突时不猜，因为选错方向就是"给已签收订单退款"。
                return manualReview(rule, EligibilityReasonCode.LOGISTICS_CONFLICTS_WITH_ORDER, now);
            }
            if (logistics.stalledHours() == null) {
                return manualReview(rule, EligibilityReasonCode.LOGISTICS_EVIDENCE_UNAVAILABLE, now);
            }
            if (!logistics.stalledAtLeast(stallThresholdHours)) {
                return denied(rule, EligibilityReasonCode.STALL_THRESHOLD_NOT_MET, now);
            }
            reasons.add(EligibilityReasonCode.STALL_THRESHOLD_MET);
        }

        // 金额只对**会动钱**的动作有意义：REFUND_ONLY 与 RETURN_REFUND。纯 RETURN 是"把商品退回来"，与金额
        // 无关，因此两件事都必须挡住：
        //   1. 不能用退款上限去否掉一次退货 —— 一条 RETURN 规则声明 max_refund_amount 不代表它不能退货；
        //   2. 更不能把金额塞进决策 —— EligibilityDecision 自身的不变量禁止"纯退货动作带金额"，塞进去就是一次
        //      IllegalArgumentException（500）。这正是 T040 的用例抓到的 T039 遗留缺陷：演示数据里的
        //      DEMO_HOME_30D_RETURN 是纯 RETURN 规则，它一旦判定成功就会 500。
        boolean moneyGranting = rule.getAllowedAction() == AllowedAction.REFUND_ONLY
                || rule.getAllowedAction() == AllowedAction.RETURN_REFUND;
        if (!moneyGranting) {
            return new EligibilityDecision(
                    true, rule.getAllowedAction(), null, false, rule.getRuleCode(), rule.getVersion(), reasons, now);
        }

        // 金额一律取权威订单金额，不接受调用方传入的金额：契约的 eligibility 请求里根本没有金额字段，这样
        // "把金额说大/说小"在类型层面就写不出来。V1 只做整单退款，因此可退金额就是订单总额。
        BigDecimal refundableAmount = order.totalAmount();
        BigDecimal ruleLimit = rule.getMaxRefundAmount();
        if (ruleLimit != null && refundableAmount.compareTo(ruleLimit) > 0) {
            return denied(rule, reasons, EligibilityReasonCode.AMOUNT_EXCEEDS_RULE_LIMIT, now);
        }

        boolean approvalRequired =
                rule.getApprovalThreshold() != null && refundableAmount.compareTo(rule.getApprovalThreshold()) >= 0;
        if (approvalRequired) {
            reasons.add(EligibilityReasonCode.APPROVAL_REQUIRED_BY_AMOUNT);
        }

        return new EligibilityDecision(
                true,
                rule.getAllowedAction(),
                refundableAmount,
                approvalRequired,
                rule.getRuleCode(),
                rule.getVersion(),
                reasons,
                now);
    }

    private static EligibilityDecision unresolved(RuleSelection selection, Instant now) {
        return new EligibilityDecision(
                false,
                AllowedAction.MANUAL_REVIEW,
                null,
                false,
                null,
                null,
                List.of(selection.unresolvedReason()),
                now);
    }

    private static EligibilityDecision denied(AfterSalesRule rule, EligibilityReasonCode reason, Instant now) {
        return denied(rule, List.of(), reason, now);
    }

    /** 保留已经评估过并通过的证据段原因码，让 Trace 能还原"在拒绝之前系统已经确认了什么"。 */
    private static EligibilityDecision denied(
            AfterSalesRule rule,
            List<EligibilityReasonCode> alreadyEstablished,
            EligibilityReasonCode reason,
            Instant now) {
        List<EligibilityReasonCode> reasons = new ArrayList<>(alreadyEstablished);
        reasons.add(reason);
        return new EligibilityDecision(
                false, AllowedAction.DENY, null, false, rule.getRuleCode(), rule.getVersion(), reasons, now);
    }

    private static EligibilityDecision manualReview(AfterSalesRule rule, EligibilityReasonCode reason, Instant now) {
        return new EligibilityDecision(
                false,
                AllowedAction.MANUAL_REVIEW,
                null,
                false,
                rule.getRuleCode(),
                rule.getVersion(),
                List.of(reason),
                now);
    }

    /**
     * 规则是否在 {@code now} 生效。
     *
     * <p>区间取半开 {@code [effectiveFrom, effectiveTo)}：这样"同一 ruleCode 的相邻版本首尾相接"不需要写
     * {@code -1 秒} 这种补丁，也不会出现两条规则在同一个瞬间同时生效的歧义。
     */
    private static boolean isEffectiveAt(AfterSalesRule rule, Instant now) {
        return !rule.getEffectiveFrom().isAfter(now)
                && (rule.getEffectiveTo() == null || now.isBefore(rule.getEffectiveTo()));
    }

    /** {@code product_category} 为 null 表示通配：这条规则不限类目。 */
    private static boolean matchesCategory(AfterSalesRule rule, OrderSnapshot order) {
        return rule.getProductCategory() == null
                || order.items().stream()
                        .anyMatch(item -> rule.getProductCategory().equals(item.productCategory()));
    }

    /** {@code required_order_status} 为 null 表示通配：这条规则不限订单状态。 */
    private static boolean matchesOrderStatus(AfterSalesRule rule, OrderSnapshot order) {
        return rule.getRequiredOrderStatus() == null || rule.getRequiredOrderStatus() == order.status();
    }
}
