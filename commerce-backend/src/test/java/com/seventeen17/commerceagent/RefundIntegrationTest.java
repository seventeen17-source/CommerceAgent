package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditLog;
import com.seventeen17.commerceagent.audit.AuditLogRepository;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.logistics.LogisticsEvent;
import com.seventeen17.commerceagent.logistics.LogisticsEventRepository;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.refund.RefundCommand;
import com.seventeen17.commerceagent.refund.RefundRequest;
import com.seventeen17.commerceagent.refund.RefundRequestRepository;
import com.seventeen17.commerceagent.refund.RefundResult;
import com.seventeen17.commerceagent.refund.RefundService;
import com.seventeen17.commerceagent.refund.RefundStatus;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * T021：受保护退款写入的可执行规格 —— refund authorization / amount bound / illegal state /
 * idempotency reuse-conflict / timeout recovery。
 *
 * <p>这个类要证明的不是"能写进去一行"，而是**钱不会写错**。五个区域各自对应一种真实损失：
 *
 * <ol>
 *   <li><b>authorization</b>：越权退款（别人的订单）与角色越界（审批者替客户退款）；
 *   <li><b>amount bound</b>：金额被调用方抬高，或者被服务端静默改成别的数；
 *   <li><b>illegal state</b>：规则拒绝、证据不足、需要审批、依赖故障被伪装成"可以退"；
 *   <li><b>idempotency</b>：重试变成第二笔退款，或者同一个 key 被拿去付另一笔钱；
 *   <li><b>timeout recovery</b>：写请求超时后，Agent 必须能靠**已提交事实**恢复，而不是换 key 盲重试。
 * </ol>
 *
 * <p>四条设计决定由用户拍板，测试逐条钉住：
 *
 * <ul>
 *   <li>幂等键命名空间属于**用户**（{@code UNIQUE(user_id, idempotency_key)}）：别人用过的 key 不会让你失败，
 *       {@link #theSameKeyFromAnotherUserIsNotAConflict()} 证明两个用户可以各自用自己的；
 *   <li>幂等指纹 =（orderId, amount, reasonCode），**runId 不参与**：run 恢复后重试必须仍是同一笔
 *       （见 {@link #replayingTheSameKeyReturnsTheSameRefundWithoutASecondRow()}）；
 *   <li>V1 只支持**整单退款**：显式金额必须正好等于授权全额，少于或超出都是明确错误，绝不静默取小
 *       （{@link #aPartialAmountIsRejectedInsteadOfBeingSilentlyChanged()}）；
 *   <li>并发靠**订单行锁 + 锁后二次检查 + 两个唯一约束兜底**
 *       （{@link #concurrentRefundsWithTheSameKeyProduceExactlyOneRefund()} 与
 *       {@link #concurrentRefundsWithDifferentKeysProduceExactlyOneRefund()}）。
 * </ul>
 *
 * <p>与 T019/T020 相同的约定：不标注 {@code @Transactional}（每个服务调用必须跑在自己的事务里，否则测不出并发与
 * 提交语义）；只清理自己造的 {@code t021-} / {@code T021-} 数据；使用 T021 专属类目，避免与别的测试类遗留的规则行
 * 形成"两个 ruleCode 同时匹配"的冲突。
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class RefundIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-09-20T08:00:00Z");
    private static final Instant EFFECTIVE_FROM = Instant.parse("2026-09-01T00:00:00Z");

    /** T021 专属类目：见类注释里的隔离理由。 */
    private static final String CATEGORY = "T021-CATEGORY";

    /** 刻意没有任何规则覆盖的类目，用来触发"规则集无法决定"。 */
    private static final String UNCOVERED_CATEGORY = "T021-NO-RULE-CATEGORY";

    private static final String RULE_CODE = "T021-STALLED-REFUND";
    private static final String OWNER_ID = "t021-owner";
    private static final String OTHER_ID = "t021-other";

    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);
    private static final CommercePrincipal OTHER = new CommercePrincipal(OTHER_ID, UserRole.CUSTOMER);

    /** 每个用例都用一个新的 Agent run id：它是溯源信息，不是身份。 */
    private static final String RUN_ID = "6f1d0f7e-6a2b-4c3d-8e4f-5a6b7c8d9e0f";

    @Autowired
    private RefundService refundService;

    @Autowired
    private RefundRequestRepository refundRequestRepository;

    @Autowired
    private AfterSalesRuleRepository ruleRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private LogisticsEventRepository logisticsEventRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private AuditLogRepository auditLogRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    // ------------------------------------------------------------------
    // refund authorization
    // ------------------------------------------------------------------

    @Test
    void ownerCreatesExactlyOneWholeOrderRefund() {
        seedRefundableOrder("t021-order-happy", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        RefundResult result =
                refundService.createRefund(OWNER, "t021-key-happy", command("t021-order-happy", null, null));

        assertNotNull(result.refundRequestId());
        assertEquals(RefundStatus.CREATED, result.status());
        assertEquals(0, result.acceptedAmount().compareTo(new BigDecimal("199.00")));
        assertEquals(1, refundRowCount("t021-order-happy"));

        // 订单与退款在同一事务里更新：after_sales_status 是"这个订单已经在售后中"的可查询投影，
        // T020 的资格判定读的正是它。只写退款行不更新投影，会让下一次资格判定继续认为"没人退过款"。
        assertEquals("REFUND_REQUESTED", afterSalesStatusOf("t021-order-happy"));

        // 退款行本身携带授权来源与溯源信息，且归属只来自 principal。
        RefundRequest refund = refundRequestRepository
                .findByUserIdAndIdempotencyKey(OWNER_ID, "t021-key-happy")
                .orElseThrow();
        assertEquals(OWNER_ID, refund.getUserId());
        assertEquals(RULE_CODE, refund.getEligibilityRuleCode());
        assertEquals(RUN_ID, refund.getRunId());
        assertNull(refund.getApprovalRequestId(), "V1 恒为 null：没有可绑定的权威审批记录");

        // 审计与业务写入同事务提交（T013 的 writeBusinessEvent 使用 REQUIRED），因此不会出现"审计说成功、
        // 业务回滚了"的假 SUCCESS。
        List<AuditLog> auditTrail =
                auditLogRepository.findByActionAndResourceIdOrderByCreatedAtAsc("REFUND_CREATED", refund.getId());
        assertEquals(1, auditTrail.size());
        assertEquals(AuditActorType.USER, auditTrail.get(0).getActorType());
        assertEquals(OWNER_ID, auditTrail.get(0).getActorId());
        assertEquals(UUID.fromString(RUN_ID), auditTrail.get(0).getRunId());
        assertEquals("t021-order-happy", auditTrail.get(0).getMetadataJson().get("orderId"));
        assertEquals("199.00", auditTrail.get(0).getMetadataJson().get("amount"));
        assertEquals(RULE_CODE, auditTrail.get(0).getMetadataJson().get("ruleCode"));
    }

    @Test
    void anotherUsersOrderIsIndistinguishableFromAMissingOrder() {
        seedRefundableOrder("t021-order-owned", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        BusinessException notMine = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(OTHER, "t021-key-cross", command("t021-order-owned", null, null)));
        BusinessException missing = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(OTHER, "t021-key-missing", command("t021-order-gone", null, null)));

        assertEquals(ErrorCode.ORDER_NOT_FOUND, notMine.getErrorCode());
        assertEquals(ErrorCode.ORDER_NOT_FOUND, missing.getErrorCode());
        assertEquals(missing.getMessage(), notMine.getMessage(), "写路径不得重新引入存在性泄露");
        assertEquals(0, refundRowCount("t021-order-owned"), "越权尝试不得留下任何写入痕迹");
    }

    @Test
    void aNonCustomerRoleCannotCreateARefund() {
        seedRefundableOrder("t021-order-role", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        CommercePrincipal approver = new CommercePrincipal(OWNER_ID, UserRole.APPROVER);

        BusinessException denied = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(approver, "t021-key-role", command("t021-order-role", null, null)));

        // 403 在这里只表示"角色/能力不足"，与订单归属无关（T019 的口径）：能力检查在 ownership 之前，
        // 因此审批者拿别人的 orderId 探测也只会得到同一个 403。
        assertEquals(ErrorCode.ACCESS_DENIED, denied.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-role"));
    }

    @Test
    void aRunIdIsProvenanceAndCannotChangeOwnership() {
        seedRefundableOrder("t021-order-runid", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        String foreignRunId = UUID.randomUUID().toString();

        RefundResult result = refundService.createRefund(
                OWNER,
                "t021-key-runid",
                new RefundCommand("t021-order-runid", "STALLED_LOGISTICS", null, null, foreignRunId));

        RefundRequest refund =
                refundRequestRepository.findById(result.refundRequestId()).orElseThrow();
        // Java 把 run_id 记下来用于跨服务追查，但它不能、也不应该被用来授权：agent.agent_runs 属于另一个 schema 与
        // 另一个数据库角色，本服务无从验证。归属永远只来自 principal。
        assertEquals(foreignRunId, refund.getRunId());
        assertEquals(OWNER_ID, refund.getUserId());
    }

    // ------------------------------------------------------------------
    // amount bound
    // ------------------------------------------------------------------

    @Test
    void anExplicitWholeOrderAmountIsAccepted() {
        seedRefundableOrder("t021-order-explicit", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        RefundResult result = refundService.createRefund(
                OWNER, "t021-key-explicit", command("t021-order-explicit", new BigDecimal("199.00"), null));

        assertEquals(0, result.acceptedAmount().compareTo(new BigDecimal("199.00")));
    }

    @Test
    void anAmountAboveTheAuthorisedMaximumIsRejected() {
        seedRefundableOrder("t021-order-over", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-over", command("t021-order-over", new BigDecimal("250.00"), null)));

        assertEquals(ErrorCode.AMOUNT_EXCEEDS_ALLOWED, failure.getErrorCode());
        assertFalse(failure.getErrorCode().retryable());
        assertEquals(0, refundRowCount("t021-order-over"));
    }

    /**
     * 少于全额也拒绝，而不是"退款金额被服务端静默改成全额"或"按部分金额退"。
     *
     * <p>V1 只做整单退款（data-model 与 US1 的用户故事都只描述整单）。服务端静默改金额比报错危险得多：调用方会
     * 以为自己退了 100，实际退了 199。
     */
    @Test
    void aPartialAmountIsRejectedInsteadOfBeingSilentlyChanged() {
        seedRefundableOrder("t021-order-partial", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-partial", command("t021-order-partial", new BigDecimal("100.00"), null)));

        assertEquals(ErrorCode.INVALID_PARAMETER, failure.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-partial"));
    }

    @Test
    void aNonPositiveAmountIsRejected() {
        seedRefundableOrder("t021-order-zero", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        BusinessException zero = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-zero", command("t021-order-zero", BigDecimal.ZERO, null)));
        BusinessException negative = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-negative", command("t021-order-zero", new BigDecimal("-5.00"), null)));

        assertEquals(ErrorCode.INVALID_PARAMETER, zero.getErrorCode());
        assertEquals(ErrorCode.INVALID_PARAMETER, negative.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-zero"));
    }

    // ------------------------------------------------------------------
    // illegal state
    // ------------------------------------------------------------------

    @Test
    void anOrderThatAlreadyHasALiveRefundCannotGetASecondOne() {
        seedRefundableOrder("t021-order-duplicate", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        RefundResult first =
                refundService.createRefund(OWNER, "t021-key-first", command("t021-order-duplicate", null, null));

        BusinessException second = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-second", command("t021-order-duplicate", null, null)));

        assertEquals(ErrorCode.DUPLICATE_AFTER_SALES, second.getErrorCode());
        assertEquals(1, refundRowCount("t021-order-duplicate"));
        assertEquals(
                List.of(first.refundRequestId()),
                refundService.listRefunds(OWNER, "t021-order-duplicate").stream()
                        .map(RefundResult::refundRequestId)
                        .toList(),
                "被拒绝的第二次请求不得改变第一笔退款");
    }

    @Test
    void anOrderBelowTheStallThresholdIsDeniedByTheRules() {
        seedRefundableOrder("t021-order-not-stalled", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(47));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-not-stalled", command("t021-order-not-stalled", null, null)));

        assertEquals(ErrorCode.ELIGIBILITY_DENIED, failure.getErrorCode());
        assertFalse(failure.getErrorCode().retryable());
        assertEquals(0, refundRowCount("t021-order-not-stalled"));
    }

    @Test
    void anOrderWithNoApplicableRuleRequiresAHumanInsteadOfAWrite() {
        // 规则只覆盖 CATEGORY，因此这个订单的类目没有任何规则适用。
        seedOrderAndRule("t021-order-uncovered", OWNER_ID, new BigDecimal("199.00"), UNCOVERED_CATEGORY);
        seedStalledShipment("t021-ship-uncovered", "t021-order-uncovered", Duration.ofHours(120));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-uncovered", command("t021-order-uncovered", null, null)));

        // "规则集无法决定"不是"业务上拒绝"：前者要转人工，后者只需解释。两者的错误码必须不同。
        assertEquals(ErrorCode.MANUAL_REVIEW_REQUIRED, failure.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-uncovered"));
    }

    @Test
    void anAmountThatNeedsApprovalCannotBeWrittenWithoutOne() {
        // 订单 400.00 达到规则的 300.00 审批阈值：资格允许，但必须先有权威审批。
        seedRefundableOrder("t021-order-approval", OWNER_ID, new BigDecimal("400.00"), Duration.ofHours(120));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-approval", command("t021-order-approval", null, null)));

        assertEquals(ErrorCode.APPROVAL_REQUIRED, failure.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-approval"), "审批前资金写入必须为 0");
    }

    @Test
    void anApprovalReferenceCannotBeAcceptedInThisVersion() {
        seedRefundableOrder("t021-order-approvalref", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-approvalref", command("t021-order-approvalref", null, "approval-001")));

        // 无法验证的审批引用被原样存进退款行，会在表里留下"看起来已获批准"的证据。宁可拒绝。
        assertEquals(ErrorCode.INVALID_PARAMETER, failure.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-approvalref"));
    }

    @Test
    void missingAuthoritativeLogisticsStaysARetryableDependencyFailure() {
        seedOrderAndRule("t021-order-noship", OWNER_ID, new BigDecimal("199.00"), CATEGORY);
        // 刻意不建运单：订单状态说已发货、却没有权威物流记录。

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(OWNER, "t021-key-noship", command("t021-order-noship", null, null)));

        assertEquals(ErrorCode.LOGISTICS_UNAVAILABLE, failure.getErrorCode());
        assertTrue(failure.getErrorCode().retryable(), "依赖不可用是'结果未知'，不是'业务拒绝'");
        assertEquals(0, refundRowCount("t021-order-noship"));
    }

    // ------------------------------------------------------------------
    // idempotency reuse / conflict
    // ------------------------------------------------------------------

    @Test
    void replayingTheSameKeyReturnsTheSameRefundWithoutASecondRow() {
        seedRefundableOrder("t021-order-replay", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        RefundCommand command = command("t021-order-replay", null, null);

        RefundResult first = refundService.createRefund(OWNER, "t021-key-replay", command);
        // 第二次调用模拟"上一次的响应丢了，Agent 用同一个 key 重试"。runId 可能不同，因此它不在指纹里。
        RefundCommand retriedFromAResumedRun = new RefundCommand(
                "t021-order-replay",
                "STALLED_LOGISTICS",
                null,
                null,
                UUID.randomUUID().toString());
        RefundResult replayed = refundService.createRefund(OWNER, "t021-key-replay", retriedFromAResumedRun);

        assertEquals(first.refundRequestId(), replayed.refundRequestId(), "重放必须返回同一笔逻辑退款");
        assertEquals(1, refundRowCount("t021-order-replay"));
    }

    @Test
    void replayingWithAnExplicitWholeOrderAmountIsStillAReplay() {
        seedRefundableOrder("t021-order-replay-explicit", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        RefundResult first = refundService.createRefund(
                OWNER, "t021-key-replay-explicit", command("t021-order-replay-explicit", null, null));
        RefundResult replayed = refundService.createRefund(
                OWNER,
                "t021-key-replay-explicit",
                command("t021-order-replay-explicit", new BigDecimal("199.00"), null));

        // 省略金额表示"按授权全额"，因此它与"显式写出那个全额"是同一个逻辑请求。
        assertEquals(first.refundRequestId(), replayed.refundRequestId());
        assertEquals(1, refundRowCount("t021-order-replay-explicit"));
    }

    @Test
    void theSameKeyWithADifferentAmountIsAConflict() {
        seedRefundableOrder("t021-order-key-amount", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        refundService.createRefund(OWNER, "t021-key-amount", command("t021-order-key-amount", null, null));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER, "t021-key-amount", command("t021-order-key-amount", new BigDecimal("100.00"), null)));

        assertEquals(ErrorCode.IDEMPOTENCY_CONFLICT, failure.getErrorCode());
        assertEquals(1, refundRowCount("t021-order-key-amount"));
    }

    @Test
    void theSameKeyWithADifferentOrderIsAConflict() {
        seedRefundableOrder("t021-order-key-a", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        seedRefundableOrder("t021-order-key-b", OWNER_ID, new BigDecimal("89.00"), Duration.ofHours(120));
        refundService.createRefund(OWNER, "t021-key-reused", command("t021-order-key-a", null, null));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(OWNER, "t021-key-reused", command("t021-order-key-b", null, null)));

        assertEquals(ErrorCode.IDEMPOTENCY_CONFLICT, failure.getErrorCode());
        assertEquals(0, refundRowCount("t021-order-key-b"), "被拒绝的请求不得在另一个订单上留下写入");
    }

    /**
     * 幂等键的命名空间属于用户，而不是整张表。
     *
     * <p>如果 key 全局唯一，一个用了朴素 key（比如 "retry-1"）的客户端会因为别人先用了同一个字符串而失败 —— 而且
     * 失败本身泄露了"这个 key 被别人用过"。按用户隔离之后，两个用户可以各自使用同一个 key，且查询一律带 owner
     * 谓词，所以谁也读不回别人的退款。
     */
    @Test
    void theSameKeyFromAnotherUserIsNotAConflict() {
        seedRefundableOrder("t021-order-owner-key", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        seedRefundableOrder("t021-order-other-key", OTHER_ID, new BigDecimal("89.00"), Duration.ofHours(120));

        RefundResult ownerRefund =
                refundService.createRefund(OWNER, "t021-shared-key", command("t021-order-owner-key", null, null));
        RefundResult otherRefund =
                refundService.createRefund(OTHER, "t021-shared-key", command("t021-order-other-key", null, null));

        assertFalse(ownerRefund.refundRequestId().equals(otherRefund.refundRequestId()));
        assertEquals(1, refundRowCount("t021-order-owner-key"));
        assertEquals(1, refundRowCount("t021-order-other-key"));

        // 每个用户只能看到自己那笔：读面也带 owner 谓词。
        assertEquals(
                List.of(ownerRefund.refundRequestId()),
                refundService.listRefunds(OWNER, "t021-order-owner-key").stream()
                        .map(RefundResult::refundRequestId)
                        .toList());
    }

    @Test
    void aMalformedIdempotencyKeyIsRejected() {
        seedRefundableOrder("t021-order-key-shape", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        // 太短（契约要求 >= 8）、含空白、含点号（点号是 JWT 的形状特征：允许它等于给"把 token 当 key 落库"留门）。
        for (String invalidKey : List.of("short", "has space", "aaaa.bbbb.cccc")) {
            BusinessException failure = assertThrows(
                    BusinessException.class,
                    () -> refundService.createRefund(OWNER, invalidKey, command("t021-order-key-shape", null, null)),
                    invalidKey);
            assertEquals(ErrorCode.INVALID_PARAMETER, failure.getErrorCode(), invalidKey);
        }
        assertEquals(0, refundRowCount("t021-order-key-shape"));
    }

    @Test
    void aBlindRetryWithANewKeyCannotBuyASecondRefund() {
        seedRefundableOrder("t021-order-blind", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        refundService.createRefund(OWNER, "t021-key-original", command("t021-order-blind", null, null));

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(OWNER, "t021-key-brand-new", command("t021-order-blind", null, null)));

        // 这条断言是 T031 的地基：**不能**把"不重复付款"寄托在 Agent 记得复用 key 上。换 key 盲重试也会被拦。
        assertEquals(ErrorCode.DUPLICATE_AFTER_SALES, failure.getErrorCode());
        assertEquals(1, refundRowCount("t021-order-blind"));
    }

    // ------------------------------------------------------------------
    // timeout recovery
    // ------------------------------------------------------------------

    /**
     * 写请求超时后，"结果未知"必须能被权威读面回答。
     *
     * <p>模拟方式就是**不看返回值**：服务已经提交，调用方没收到。恢复路径有两条，且都必须指向同一笔退款 ——
     * 读状态（不写）与同 key 重放（写但幂等）。换新 key 重试在第 {@link #aBlindRetryWithANewKeyCannotBuyASecondRefund()}
     * 条被证明会被拒绝。
     */
    @Test
    void aCommittedRefundIsRecoverableByReadingTheAuthoritativeStatus() {
        seedRefundableOrder("t021-order-timeout", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));
        refundService.createRefund(OWNER, "t021-key-timeout", command("t021-order-timeout", null, null));

        // 路径一：读回权威状态。这是唯一不需要写入就能确认事实的方式。
        List<RefundResult> recovered = refundService.listRefunds(OWNER, "t021-order-timeout");
        assertEquals(1, recovered.size());
        assertEquals(RefundStatus.CREATED, recovered.get(0).status());
        assertEquals(0, recovered.get(0).acceptedAmount().compareTo(new BigDecimal("199.00")));

        // 路径二：同 key 重放。它返回的必须是同一笔，而不是"看起来像"的第二笔。
        RefundResult replayed =
                refundService.createRefund(OWNER, "t021-key-timeout", command("t021-order-timeout", null, null));
        assertEquals(recovered.get(0).refundRequestId(), replayed.refundRequestId());
        assertEquals(1, refundRowCount("t021-order-timeout"));
    }

    /**
     * 同一 key 的并发重放：两个真实线程 + {@code CyclicBarrier}，结果必须是**同一笔**退款。
     *
     * <p>没有订单行锁时，两个线程都会在"幂等键不存在"这个结论上继续往下写；有了锁但没有锁后二次检查，第二个线程
     * 会在锁释放后按**过期结论**继续写 —— 那正是"重试造出第二笔付款"的经典形态。这条用例同时证明两件事都在。
     */
    @Test
    void concurrentRefundsWithTheSameKeyProduceExactlyOneRefund() throws Exception {
        seedRefundableOrder("t021-order-concurrent-key", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        List<Callable<Object>> attempts = List.of(
                () -> attemptRefund(OWNER, "t021-key-concurrent", "t021-order-concurrent-key"),
                () -> attemptRefund(OWNER, "t021-key-concurrent", "t021-order-concurrent-key"));

        List<Object> outcomes = runConcurrently(attempts);

        List<String> refundIds = new ArrayList<>();
        for (Object outcome : outcomes) {
            assertTrue(outcome instanceof RefundResult, "同一 key 的并发重放不应产生错误，实际：" + outcome);
            refundIds.add(((RefundResult) outcome).refundRequestId());
        }
        assertEquals(1, refundIds.stream().distinct().count(), "两个线程必须拿到同一笔退款");
        assertEquals(1, refundRowCount("t021-order-concurrent-key"));
    }

    /**
     * 不同 key、同一订单的并发写入：允许一个赢家，输家必须是确定的业务错误而不是 500。
     *
     * <p>输家的形态取决于谁先拿到锁：先到者成功，后到者在锁后看到 {@code after_sales_status} 已经是
     * {@code REFUND_REQUESTED}，得到 {@link ErrorCode#DUPLICATE_AFTER_SALES}。这里断言"恰好一行 + 恰好一个成功
     * + 失败者是 409"而不是断言固定顺序 —— 顺序由调度决定，语义不该依赖顺序。
     */
    @Test
    void concurrentRefundsWithDifferentKeysProduceExactlyOneRefund() throws Exception {
        seedRefundableOrder("t021-order-concurrent-keys", OWNER_ID, new BigDecimal("199.00"), Duration.ofHours(120));

        List<Callable<Object>> attempts = List.of(
                () -> attemptRefund(OWNER, "t021-key-race-a", "t021-order-concurrent-keys"),
                () -> attemptRefund(OWNER, "t021-key-race-b", "t021-order-concurrent-keys"));

        List<Object> outcomes = runConcurrently(attempts);

        long succeeded =
                outcomes.stream().filter(RefundResult.class::isInstance).count();
        long duplicated = outcomes.stream()
                .filter(outcome -> outcome == ErrorCode.DUPLICATE_AFTER_SALES)
                .count();
        assertEquals(1, succeeded, "恰好一个请求可以创建退款，实际结果：" + outcomes);
        assertEquals(1, duplicated, "另一个必须是明确的 DUPLICATE_AFTER_SALES，而不是 500 或锁超时：" + outcomes);
        assertEquals(1, refundRowCount("t021-order-concurrent-keys"));
    }

    // ------------------------------------------------------------------
    // 夹具与工具
    // ------------------------------------------------------------------

    @AfterEach
    void removeT021Rows() {
        // 审计的 resource_id 既可能是订单 id（越权读的 concealment 审计），也可能是退款 id（UUID），两种都要清。
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't021-%' OR resource_id IN "
                + "(SELECT id FROM commerce.refund_requests WHERE order_id LIKE 't021-%')");
        jdbcTemplate.update("DELETE FROM commerce.refund_requests WHERE order_id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't021-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code = ?", RULE_CODE);
    }

    private static RefundCommand command(String orderId, BigDecimal requestedAmount, String approvalRequestId) {
        return new RefundCommand(orderId, "STALLED_LOGISTICS", requestedAmount, approvalRequestId, RUN_ID);
    }

    /** 线程里执行一次写入，把业务错误翻译成错误码返回，便于断言"失败也是确定的失败"。 */
    private Object attemptRefund(CommercePrincipal principal, String key, String orderId) {
        try {
            return refundService.createRefund(principal, key, command(orderId, null, null));
        } catch (BusinessException exception) {
            return exception.getErrorCode();
        }
    }

    private static List<Object> runConcurrently(List<Callable<Object>> attempts) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(attempts.size());
        CyclicBarrier barrier = new CyclicBarrier(attempts.size());
        try {
            List<Future<Object>> futures = new ArrayList<>();
            for (Callable<Object> attempt : attempts) {
                futures.add(pool.submit(() -> {
                    barrier.await(30, TimeUnit.SECONDS);
                    return attempt.call();
                }));
            }
            List<Object> outcomes = new ArrayList<>();
            for (Future<Object> future : futures) {
                outcomes.add(future.get(30, TimeUnit.SECONDS));
            }
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }

    private void seedRefundableOrder(String orderId, String userId, BigDecimal totalAmount, Duration stalledFor) {
        seedOrderAndRule(orderId, userId, totalAmount, CATEGORY);
        seedStalledShipment(orderId + "-shipment", orderId, stalledFor);
    }

    private void seedOrderAndRule(String orderId, String userId, BigDecimal totalAmount, String category) {
        seedUser(userId);
        seedRule();
        seedOrder(orderId, userId, totalAmount, category);
    }

    private void seedUser(String userId) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.save(User.create(userId, userId + "-username", UserRole.CUSTOMER));
        }
    }

    private void seedRule() {
        if (ruleRepository.existsByRuleCodeAndVersion(RULE_CODE, 1)) {
            return;
        }
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                RULE_CODE,
                1,
                CATEGORY,
                OrderStatus.SHIPPED,
                48,
                7,
                new BigDecimal("500.00"),
                new BigDecimal("300.00"),
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null));
    }

    private void seedOrder(String orderId, String userId, BigDecimal totalAmount, String category) {
        Order order = Order.create(orderId, userId, OrderStatus.SHIPPED, totalAmount, "USD");
        order.addItem(OrderItem.create(
                orderId + "-item-1", orderId + "-product-1", "Test Product", category, totalAmount, 1));
        orderRepository.save(order);
    }

    private void seedStalledShipment(String shipmentId, String orderId, Duration stalledFor) {
        Shipment shipment =
                Shipment.create(shipmentId, orderId, "T021", shipmentId + "-tracking", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(stalledFor));
        shipmentRepository.save(shipment);
        logisticsEventRepository.save(
                LogisticsEvent.create(shipment, "IN_TRANSIT", "T021 synthetic event", NOW.minus(stalledFor)));
    }

    private long refundRowCount(String orderId) {
        Long count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.refund_requests WHERE order_id = ?", Long.class, orderId);
        return count == null ? 0 : count;
    }

    private String afterSalesStatusOf(String orderId) {
        return jdbcTemplate.queryForObject(
                "SELECT after_sales_status FROM commerce.orders WHERE id = ?", String.class, orderId);
    }

    /** 与 T019/T020 相同：把"现在"钉死，停滞判定与阈值比较才能精确断言。 */
    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
