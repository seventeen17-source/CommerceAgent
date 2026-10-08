package com.seventeen17.commerceagent.returns;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import java.util.UUID;

/**
 * T040：创建退货请求的输入（对应契约 {@code CreateReturnRequest}）。
 *
 * <p><b>刻意没有 {@code userId} 字段。</b>与 {@code RefundCommand} 同一条纪律：退货归属只能来自服务端解析过的
 * principal（T011/T018）。把 userId 放进命令对象，等于给"模型/调用方自报身份"留一个字段；而"这个类型里根本
 * 没有这个字段"是比"记得不要用"更硬的约束。
 *
 * <p>字段的可信度分级：
 *
 * <ul>
 *   <li>{@code orderId} —— 目标订单。只用于定位；真正的授权依据是 principal 对该订单的 ownership。
 *   <li>{@code reasonCode} —— 描述性原因。参与幂等指纹，但<b>不影响</b>资格（资格是 T039 的确定性规则）。
 *   <li>{@code returnMethod} —— 可空。契约发布了这个字段，但 V1 不给它任何行为：只做形状校验，落库并参与幂等
 *       指纹（否则"同一个 key、换一种退货方式"会被静默当成同一次逻辑请求）。
 *   <li>{@code approvalRequestId} —— 可空且只是 locator。当前 eligibility 要求审批时，
 *       {@link ReturnService} 会 owner-scoped 重读权威 ApprovalRequest，并校验 APPROVED + run/order/action/amount
 *       binding；当前不要求审批时携带该字段反而会被拒绝，避免把 approval id 当通用 bearer token。
 *   <li>{@code runId} —— Agent run 的 UUID。它是<b>溯源</b>信息（写进退货行与审计的 run_id），不是身份：Java
 *       不能也不应该用它授权，因为 {@code agent.agent_runs} 属于另一个 schema 与另一个数据库角色。
 * </ul>
 *
 * <p>形状校验放在紧凑构造器里，与 {@code RefundCommand} 同理：命令对象的构造点只有一个（T040 的控制器），
 * 非法值不该进入业务逻辑；而且抛的是 {@link BusinessException}（{@code INVALID_PARAMETER} → 400）而不是
 * {@code IllegalArgumentException} —— 后者会被全局异常处理器归入 {@code INTERNAL_ERROR}，把一次正常的参数
 * 拒绝变成 500。
 */
public record ReturnCommand(
        String orderId, String reasonCode, String returnMethod, String approvalRequestId, String runId) {

    public ReturnCommand {
        orderId = requireText(orderId, "orderId", 64);
        reasonCode = requireText(reasonCode, "reasonCode", 100);
        returnMethod = requireOptionalText(returnMethod, "returnMethod", 32);
        approvalRequestId = requireOptionalText(approvalRequestId, "approvalRequestId", 64);
        runId = requireUuid(runId, "runId");
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
     * <p>理由是它的三个落点都要求 UUID 形状：退货行的 {@code run_id}、审计的 {@code run_id UUID}，以及日后跨服务
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
