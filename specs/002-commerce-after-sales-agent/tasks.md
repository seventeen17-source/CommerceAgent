# Coding Tasks：只实现当前 MVP

Input：[spec.md](spec.md)、[plan.md](plan.md)、[research.md](research.md)、[data-model.md](data-model.md)、[contracts/runtime-contracts.md](contracts/runtime-contracts.md)、两份 OpenAPI、[evaluation.md](evaluation.md)。

本清单替换旧 83 项，不继承其完成状态。下面 44 项全部未实现。不要重新运行 001、生成新选题报告或预建延期功能。格式 `- [ ] Tnnn [USn]`；单人按顺序执行。相邻任务共用配置/图文件，未标 [P] 的不并行修改。测试先证明缺失行为再写实现。每项完成附实际命令/结果，不能仅凭创建文件勾选。

## M0 / Setup：先解除最高风险（G0）

- [ ] T001 检查 Java 21、Python 3.13、uv、Node 22.12+、Docker Compose 与模型凭据的可用性，在 README.md 的环境验证表记录实际版本/失败；不记录密钥。
- [ ] T002 用 Spring Initializr 创建 commerce-backend/，固定 Java 21/Spring Boot 3.5.16/Maven；保留 mvnw、mvnw.cmd、.mvn/；依赖 Web/Security/Validation/JPA/PostgreSQL/Flyway/Testcontainers，在 commerce-backend/pom.xml 锁定并跑空测试。
- [ ] T003 用 uv init 创建 agent-service/，在 agent-service/pyproject.toml 配置 FastAPI/Pydantic/httpx/OpenAI SDK/LangGraph/官方 PostgreSQL saver/pytest/ruff，保留 uv.lock；不手写伪 lockfile。
- [ ] T004 用 Vite React+TypeScript 生成 web/，锁 package-lock.json；只保留一个空页面并在 web/package.json 提供 build；不加入管理模板。
- [ ] T005 在 infra/compose.yaml、infra/db/、.env.example 实现 PostgreSQL 17、分角色 bootstrap、Flyway 自定义迁移任务与 checkpoint-init 分区初始化；用 agent-service/tests/smoke/test_db_privileges.py 证明 Python 账号不可读写 commerce，runtime 不可 DDL；重复初始化必须安全。
- [ ] T006 在 agent-service/app/llm/client.py 实现唯一 ModelAdapter；在 agent-service/tests/smoke/test_model_contract.py 用 6 个合成输入验证真实工具调用、单工具限制、schema、错误、usage 与预算；无真实接入证据不得勾选。
- [ ] T007 在 agent-service/tests/smoke/test_checkpoint_restart.py 验证官方 saver 在 checkpoint schema 建表、WAITING_USER/模拟审批 interrupt 后跨进程恢复；恢复前副作用重放用稳定键替身检查，JWT 不入持久化状态。
- [ ] T008 在 README.md 的 G0 验证区记录 T005–T007 的命令、通过/失败与锁定版本；接入失败只修该依赖，不扩展后续 feature。

## M1 / Foundation + US1：第一条退款申请闭环（G1）

- [ ] T009 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/security/、agent-service/app/security/ 和 infra/dev_identity/ 实现预置身份、RSA 公钥 JWT 验证、owner 检查；本地密钥不进 Git，两个服务不持签名私钥。
- [ ] T010 在 commerce-backend/src/main/resources/db/migration/ 建 users/orders/after_sales_requests/operation_records/audit_events 及 agent_runs/run_inputs/tool_executions；保留 order_id UNIQUE、金额整数分与用户+请求键唯一约束；审批 FK 随 M3 添加。
- [ ] T011 [US1] 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/order/ 与 commerce-backend/src/main/resources/rules/ 实现订单/物流只读接口、固定业务 Clock 和版本化资格规则；需要审批但尚未实现时只拒绝自动写，不临时放行。
- [ ] T012 [US1] 在 commerce-backend/src/test/java/com/seventeen17/commerceagent/aftersales/RefundInvariantTest.java 先写越权、错误动作、同键/异键并发、金额不可覆盖、提交后响应丢失的失败测试。
- [ ] T013 [US1] 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/aftersales/ 实现统一申请 POST、GET、operation 查询和事务去重；只支持 REFUND_ONLY；同事务更新订单/操作/审计，ABSENT 不当作旧请求不会提交的证明。
- [ ] T014 [US1] 在 agent-service/app/clients/commerce.py、agent-service/app/tools/ 建类型化工具及错误映射；principal/operationId/runId 由上下文注入，模型不能设金额/URL/身份；禁用 HTTP 库对写请求的隐式重试。
- [ ] T015 [US1] 在 agent-service/app/agent/state.py、graph.py、nodes/ 实现 evidence→eligibility→prepare_write→execute→verify；先 checkpoint 操作意图再发写请求；有限重试/无进展/SAFE_STOP 从首版就存在。
- [ ] T016 [US1] 在 agent-service/app/api/runs.py、app/trace/ 实现 run 创建/查询/continue/trace、clientRequestId 去重与 session advisory run 锁；提交后 checkpoint 前崩溃从原键恢复，响应断开不换 run。
- [ ] T017 [US1] 在 agent-service/app/agent/policies/base.py 和 llm_policy.py 接上真实模型的动作选择；只接受阶段白名单与严校验后的调用；冻结写参数不由模型生成。
- [ ] T018 [US1] 在 agent-service/app/agent/policies/fixed_policy.py 实现复用同一 NLU/tools/guard 的诚实固定策略；不复制后端/DB，不读取 oracle。
- [ ] T019 [US1] 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/common/eval/ 实现仅 test/eval profile 的 reset/clock/snapshot 与独立 X-Eval-Key；其他 profile 路由不存在，Agent 无钥匙也无工具。
- [ ] T020 [US1] 在 eval/runner/run_eval.py、eval/scorers/business_state.py、eval/datasets/v1/dev/ 创建 12 个 dev 案例与可跑 CLI；检查权威 snapshot，不只匹配回复；包含不可自动审批/非法状态/未知写结果。
- [ ] T021 [US1] 在 web/src/features/customer/ 增加输入、运行状态、申请结果和折叠轨迹；只用轮询/普通请求；“申请创建”不能写成“退款到账”。
- [ ] T022 [US1] 在 infra/compose.yaml、各应用 Dockerfile、.github/workflows/ci.yml 接上最小启动/健康检查/离线 Java+Python 测试和 Web build；运行 quickstart G1 并记录到 README.md；至少一条真实模型切片加一次故障验证。

## M2 / US2 + US3：分支与澄清（G2）

- [ ] T023 [US2] 在 commerce-backend/src/test/java/com/seventeen17/commerceagent/aftersales/ReturnInvariantTest.java 和 agent-service/tests/integration/test_return.py 先验证已签收只允许 RETURN_REFUND、超窗拒绝及重复申请不变。
- [ ] T024 [US2] 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/aftersales/、rules/ 和 agent-service/app/agent/ 扩统一申请的 RETURN_REFUND 路径；不新增整套退货履约服务。
- [ ] T025 [US3] 在 agent-service/tests/integration/test_clarification.py 写多订单零写、跨用户输入、无效候选、重复 inputId、重启恢复测试。
- [ ] T026 [US3] 在 agent-service/app/agent/nodes/clarify.py、app/api/runs.py 实现 WAITING_USER/输入收据/已应用 inputId 协调；从当前身份可访问的候选中确认，不能猜另一个订单。
- [ ] T027 [US3] 在 web/src/features/customer/ClarificationPanel.tsx 提供候选确认与必要文本补充；保持 runId/inputId 稳定，拒绝后展示真实原因。
- [ ] T028 [US3] 在 eval/datasets/v1/dev/ 增加至少 6 个 Agent-critical 场景，比较两种策略的取证路径；把 G2 实测与没有优势的情况同样记录在 eval/reports/。

## M3 / US4：审批、重放与未知结果（G3）

- [ ] T029 [US4] 在 commerce-backend/src/test/java/com/seventeen17/commerceagent/aftersales/ApprovalInvariantTest.java 先测试 owner/approver 权限、动作指纹、期限、消费、双击/冲突决定及申请重复。
- [ ] T030 [US4] 在 commerce-backend/src/main/resources/db/migration/ 添加 approval_requests 与申请 FK；在 commerce-backend/src/main/java/com/seventeen17/commerceagent/aftersales/ 实现审批创建、owner 可读 GET、approver 列表/决定；金额从 Java 派生，创建有 operationId。
- [ ] T031 [US4] 在 commerce-backend/src/main/java/com/seventeen17/commerceagent/aftersales/ 写入事务内锁定并核对审批 fingerprint/期限，原子消费；状态改变要求重新获取资格，不复用过期批准。
- [ ] T032 [US4] 在 agent-service/app/agent/nodes/approval.py、app/api/runs.py 接入 WAITING_APPROVAL 和 continue；客户 JWT 重新读 Java 单条审批，不借审批人 token，不直查 commerce。
- [ ] T033 [US4] 在 agent-service/tests/integration/test_recovery.py、commerce-backend/src/test/java/com/seventeen17/commerceagent/aftersales/RecoveryRaceTest.java 覆盖慢提交+ABSENT、提交后掉响应、提交后 checkpoint 前重启、两个 continue、不同键同订单、重复审批创建；保留真实故障位置记录。
- [ ] T034 [US4] 在 web/src/features/approvals/ 创建薄审批视图，显示动作/金额/订单/期限/证据摘要；支持通过/拒绝。客户页仅显示等待与继续，不自动冒用审批身份。
- [ ] T035 [US4] 在 eval/datasets/v1/dev/ 添加审批通过/拒绝/过期/跨绑定与恢复用例；完成 G3，任何非法/重复业务记录阻断后续交付。

## M4 / US5：政策引用，不做向量检索（G4）

- [ ] T036 [US5] 在 knowledge/policies/ 创建少量合成政策与 manifest；与 commerce-backend/src/main/resources/rules/ 的 code/version 对齐；明确非真实平台政策。
- [ ] T037 [US5] 在 agent-service/app/tools/policy.py、app/agent/nodes/finalize.py 实现白名单路径的精确版本直查与引用；缺失只说明无引用，金额/资格不受文本影响；不引入 pgvector/embedding。
- [ ] T038 [US5] 在 agent-service/tests/integration/test_policy.py 验证过期/不存在版本、恶意文本、路径注入与最终事实；补 SAFE_STOP 的“需联系人工、未创建工单”文案测试并完成 G4。

## M5 / 验收与交付（G5）

- [ ] T039 按 evaluation.md 在 commerce-backend/src/test/ 与 agent-service/tests/security/ 完成至少 30 个确定性安全/并发/恢复测试；对 DB 权限和 eval 接口隔离做负向检查。
- [ ] T040 在 eval/datasets/v1/manifest.yaml、dev/、test/ 完成 60 个案例配额与 family 级隔离，冻结文件哈希、Clock、规则/政策和澄清/审批脚本；先用替身验证 oracle。
- [ ] T041 在 eval/runner/、eval/scorers/ 完成配对重复、预算停止、usage/时延和三层安全计数；显式 live 后对 30 个 final 案例两策略各跑 3 次，保留原始 JSONL/配置与 infra failures；未运行不勾选。
- [ ] T042 在 agent-service/tests/contract/、commerce-backend/src/test/、.github/workflows/ci.yml 验证两个 OpenAPI 与实现一致、所有工具有端点/本地实现、owner 查询/恢复闭合；最终 CI 不依赖付费模型。
- [ ] T043 按 quickstart.md 在空数据库/干净克隆验证初始化、启动、演示、断电恢复与本地密钥流程；在 README.md 写真实命令、已通过范围、缺陷与约 90 秒演示脚本，绝不虚构支付集成。
- [ ] T044 将 eval/reports/ 原始记录与摘要、代码 SHA、环境版本对应起来，在 README.md 标注 G0–G5 实际结果；无增益也报告；完成所有安全 gate 才称 V1，否则明确为部分切片。

## 依赖与执行方式

T001→T002/T003/T004→T005→T006/T007→T008；M1 在 G0 后依次交付；M2 复用 M1；M3 复用相同事务与图，不另起系统；M4 可在 G1 后编写政策资源，但不得抢占 G3 修复；M5 的 runner/CI 已由 M1 建好，这里只是扩充与最终运行。

不同开发者可在接口冻结后并行写 T012 的 Java 测试与 T014 的 Python 合同测试，或 T029 的 Java 测试与 T032 的 Python 恢复测试；不要并行改相同 graph/lockfile/migration 编号。单人不追求假并行。

**下一条执行指令：先做 T001–T008；报告实际通过项。G0 通过后只推进 M1 到 G1。不要一次性生成全项目。**
