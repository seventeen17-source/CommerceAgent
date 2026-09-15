# CommerceAgent

**一个小范围、可验证的电商售后申请执行 Agent。**

当前状态：**方案已收缩，可开始 M0 编码；应用尚未实现。** 本分支不是可运行 Demo，也没有已实测的模型成功率、性能或安全结论。

## Git 分支约定

正式长期开发主线：`dev/002-commerce-after-sales-mvp`。

历史研究归档：`archive/001-career-research-project-selection`，只用于查看岗位研究、选题和旧设计依据，不继续开发。

旧名称 `speckit-tasks-001-agent-career-project` 和 `002-commerce-after-sales-agent` 仅作为历史 legacy ref 保留，不再作为新的编码入口。

每个阶段只有在对应 Gate **真实通过**后，才从通过的精确 commit 创建一个不可随意移动的快照分支：

```text
milestone/m0-foundation-risk-probes
milestone/m1-refund-request-e2e
milestone/m2-return-and-order-clarification
milestone/m3-approval-and-recovery
milestone/m4-policy-reference-safe-stop
milestone/m5-evaluation-release
```

这些 milestone 是历史锚点，不是新的长期开发线。后续开发始终继续在 `dev/002-commerce-after-sales-mvp`。如果较早 milestone 后来发现问题，后面的 milestone **仍然保留**；从最后确认正确的阶段新建 `fix/<阶段>-<问题>` 修复，再明确迁移后续改动，禁止为了回退直接覆盖或删除后面的阶段快照。完整规则见 [AGENTS.md](AGENTS.md)。

## 只做什么

用户用自然语言请求售后；Python Agent 理解、澄清并选择证据；Java 验证归属、资格、金额与审批，创建退款/退货退款申请；系统查询权威结果后返回申请编号和轨迹。高金额等待人工审批，证据不足或非法请求安全停止。

所有订单与政策为本地合成数据。**创建申请不等于退款到账，不声称已接入真实电商/支付平台。**

## 开始 coding

唯一入口：[任务清单](specs/002-commerce-after-sales-agent/tasks.md)。先执行 **T001–T008 / M0**；最高风险接入通过后执行 **T009–T022 / M1**，不要一口气生成整个系统。给编码 Agent 的仓库规则在 [AGENTS.md](AGENTS.md)。

```text
M0：官方脚手架 + 真实模型工具调用探针 + checkpoint 重启 + 数据库权限
M1：唯一订单退款申请 + 事务去重 + 写后验证 + 12 个 dev 案例 + 最小 UI/基线/CI
M2：已签收退货 + 模糊订单澄清
M3：人工审批 + 未知结果/并发/重启恢复
M4：政策代码/版本直查与引用（不做向量检索）
M5：冻结 60 例、确定性安全测试、真实模型对照报告、干净环境复现
```

44 个任务是重新组织后的执行单元，不代表工作量自动减半；周期须由 G1 的实际成本校准。计划额度与削减规则见 [plan.md](specs/002-commerce-after-sales-agent/plan.md)。

## 架构边界

`薄 Web → Python Agent → Java 业务 API → PostgreSQL`

Java：一个模块化应用，聚焦订单、统一售后申请、审批、操作去重与审计。Python：一个应用，显式状态图、模型适配、白名单工具、官方 checkpoint 与评测。Web：客户控制台与薄审批界面；轨迹内嵌，报告用文件。基线复用同一系统，仅替换 DecisionPolicy。

Flyway 管自定义 commerce/agent 表；官方 saver 管独立 checkpoint schema。运行账号按权限隔离，Python 无 commerce 权限。规则判断与政策文案分离；金额整数分、后端决定，不让模型填写。

## 方案文件

| 文件 | 作用 |
|---|---|
| [spec.md](specs/002-commerce-after-sales-agent/spec.md) | 首版边界、五个故事、可验收条件 |
| [plan.md](specs/002-commerce-after-sales-agent/plan.md) | 架构、范围裁剪、里程碑与条件化预算 |
| [research.md](specs/002-commerce-after-sales-agent/research.md) | 模型、迁移、认证、基线等关键决策与官方参考 |
| [data-model.md](specs/002-commerce-after-sales-agent/data-model.md) | 精简实体、约束、事务与图状态 |
| [runtime-contracts.md](specs/002-commerce-after-sales-agent/contracts/runtime-contracts.md) | 工具、预算、错误、幂等、审批与内部评测接口 |
| [Business API](specs/002-commerce-after-sales-agent/contracts/commerce-api.openapi.yaml) / [Agent API](specs/002-commerce-after-sales-agent/contracts/agent-api.openapi.yaml) | 唯一 HTTP 合同 |
| [evaluation.md](specs/002-commerce-after-sales-agent/evaluation.md) | 分层测试、诚实基线、固定时钟与重复评测 |
| [tasks.md](specs/002-commerce-after-sales-agent/tasks.md) / [quickstart.md](specs/002-commerce-after-sales-agent/quickstart.md) | 执行顺序与编码后的验收步骤 |

## 删除与保留

从当前开发树移除旧 001 研究任务、候选评分、重复 A–Q 最终规格、旧 83 项任务和未实测的“全部 PASS”报告。002 文档与接口已经整体重写，不并存两套实现标准。

首版删除向量检索/pgvector、独立 Trace/Eval 看板、完整工单运营、完整退款/退货生命周期和额外基础设施。保留有限重试、安全停止、审批、恢复、对照评测，不通过删安全约束制造“轻量”。

原始岗位表原样移至 [docs/evidence](docs/evidence/README.md)。`.agents` 和 `.specify` 工具保留，宪章升级至 2.0.0。旧内容仍可在 Git 历史/归档分支找回，不重写历史，也不把它们放在活跃目录干扰 coding。

## 验证记录

本轮仅做方案与接口静态检查：两份 YAML 可解析；JSON Schema 语法、内部引用、路径参数和 operationId 唯一性检查通过。未进行完整 OpenAPI 工具兼容认证或真实应用测试。

| Gate | 当前结果 |
|---|---|
| G0 模型/持久化/权限接入 | PENDING，下一步编码执行 |
| G1 首条真实退款申请链路 | PENDING |
| G2 退货/澄清/Agent-critical 对照 | PENDING |
| G3 审批/并发/重放 | PENDING |
| G4 政策引用/安全停止 | PENDING |
| G5 真实评测/演示/干净启动 | PENDING |

此处由编码阶段用实际命令与证据更新。60 个案例、30 个确定性安全测试与重复次数都是交付要求，当前没有生成或运行，不是既成成果。应用启动命令必须完成并验证后再加入本 README；[quickstart](specs/002-commerce-after-sales-agent/quickstart.md) 明确区分目前可执行的环境检查与未来目标命令。
