package com.seventeen17.commerceagent.refund;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import java.math.BigDecimal;
import java.util.UUID;

/**
 * T021：创建退款请求的输入。
 *
 * <p><b>刻意没有 {@code userId} 字段。</b>退款归属只能来自服务端解析过的 principal（T011/T018）。把 userId 放进
 * 命令对象，等于给"模型/调用方自报身份"留一个字段；而"这个类型里根本没有这个字段"是比"记得不要用"更硬的约束
 * —— 与 T018 的 Run 创建同一条规则。
 *
 * <p>字段含义与可信度：
 *
 * <ul>
 *   <li>{@code orderId} —— 目标订单。只用于定位；真正的授权依据是 principal 对该订单的 ownership。
 *   <li>{@code reasonCode} —— 描述性原因，参与幂等指纹，但<b>不影响</b>资格与金额（那是 T020 的确定性规则）。
 *   <li>{@code requestedAmount} —— 可空。V1 只支持整单退款：省略表示"按授权全额"，显式给出时必须为正数、并且
 *       在资格校验之后正好等于授权金额（那一步需要权威结论，因此放在服务里）。不静默改金额。
 *   <li>{@code approvalRequestId} —— 可空。V1 没有权威审批记录可校验，因此任何非空值都会被拒绝（fail closed），
 *       而不是被原样存进退款行当作"已批准"的证据。US4/T049 会替换这条规则。
 *   <li>{@code runId} —— Agent run 的 UUID。它是**溯源**信息（写进退款行与审计的 run_id），不是身份：Java 不能
 *       也不应该用它授权，因为 {@code agent.agent_runs} 属于另一个 schema 与另一个数据库角色。
 * </ul>
 *
 * <p>形状校验放在紧凑构造器里，原因有两条：命令对象的构造点只有一个（T028 的控制器），非法值不该进入业务逻辑；
 * 而且抛的是 {@link BusinessException}（{@code INVALID_PARAMETER} → 400）而不是 {@code IllegalArgumentException}
 * —— 后者会被全局异常处理器归入 {@code INTERNAL_ERROR}，把一次正常的参数拒绝变成 500。
 */
public record RefundCommand(
        String orderId, String reasonCode, BigDecimal requestedAmount, String approvalRequestId, String runId) {

    public RefundCommand {
        orderId = requireText(orderId, "orderId", 64);
        reasonCode = requireText(reasonCode, "reasonCode", 100);
        runId = requireUuid(runId, "runId");
        approvalRequestId = requireOptionalText(approvalRequestId, "approvalRequestId", 64);
        if (requestedAmount != null && requestedAmount.signum() <= 0) {
            throw invalid("requestedAmount must be a positive amount when it is provided");
        }
    }

    /** 是否显式指定了金额。省略表示"按授权全额退款"。 */
    public boolean hasExplicitAmount() {
        return requestedAmount != null;
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw invalid(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw invalid(field + " exceeds max length " + maxLength);
        }
        if (containsControlCharacter(value)) {
            throw invalid(field + " must not contain control characters");
        }
        return value;
    }

    private static String requireOptionalText(String value, String field, int maxLength) {
        return value == null ? null : requireText(value, field, maxLength);
    }

    /**
     * {@code runId} 必须是 UUID，而不是"任意字符串"。
     *
     * <p>理由是它的三个落点都要求 UUID 形状：退款行的 {@code run_id}、审计的 {@code run_id UUID}，以及日后跨服务
     * 追查一次 run 的关联。形状错误属于调用方参数问题（400），不该等到审计写入时才炸成 500。
     */
    private static String requireUuid(String value, String field) {
        String candidate = requireText(value, field, 64);
        try {
            UUID.fromString(candidate);
        } catch (IllegalArgumentException exception) {
            throw invalid(field + " must be a UUID");
        }
        return candidate;
    }

    private static boolean containsControlCharacter(String value) {
        return value.chars().anyMatch(character -> character < 0x20 || character == 0x7F);
    }

    private static BusinessException invalid(String message) {
        return new BusinessException(ErrorCode.INVALID_PARAMETER, message);
    }
}
