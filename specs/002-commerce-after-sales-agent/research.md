# 关键技术决策（ADR 合集）

2026-09-15；所有安装/运行结果仍待 M0 验证。这里只记录实现所需裁决，不新增研究层。

## ADR-01：保留双语言，但压缩业务广度

Java 21 + Spring Boot 3.5.16 承担真实授权、事务、审批、去重；Python 3.13 + FastAPI 承担模型与图。退款/退货合并为一种申请实体，物流用订单上的合成快照，规则用版本化资源；不建设完整电商平台。Web 仅两处薄界面，轨迹内嵌。不是因为语言数量能加分，而是两侧各有不可省略职责。

## ADR-02：模型与决策接口

初始模型：`gpt-4.1-mini-2025-04-14`，通过官方 Python SDK `AsyncOpenAI` 调用 Chat Completions，使用原生工具调用。选择理由是支持工具调用、结构化输出和明确快照，不声称它是当前最强或最便宜。

配置：`LLM_BASE_URL`（仅部署配置可设）、`LLM_API_KEY`、`LLM_MODEL`、temperature=0、top_p=1、单次输出上限 512 tokens、关闭并行工具调用。支持性由 M0 探针验证；不支持参数时明确记录调整，不静默忽略。seed 仅在供应商支持时记录，不保证完全确定。

模型只看到经过裁剪的业务证据与当前允许工具 schema；身份、金额、operationId、JWT 均由程序注入，模型无权填写。Native tool_call.arguments 必须经过 Pydantic 严格解析；拒绝多工具、未知参数、任意 URL/SQL、未知订单标识。最多一次格式纠正，之后 SAFE_STOP。

允许动作包括工具调用、ASK_USER、DENY、SAFE_STOP。工具目录在 runtime-contracts.md；程序按阶段缩小白名单。证据收集需要什么由模型提议，是否足以执行写入由程序/Java 校验，不用模型“confidence”代替安全判断。

M0 用 6 个合成输入检查工具 schema、非法参数拦截、模型错误、usage 和预算；这是接入测试，不是业务成功率。密钥不可用时本地替身测试仍可进行，但 G0 的真实模型子项保持 BLOCKED，不虚构通过。更换模型须记录供应商、实际 model id、参数、模板哈希并重跑比较；不需要改业务 API。

## ADR-03：官方 checkpointer + 分区迁移

使用固定依赖的 `AsyncPostgresSaver`；它的 `.setup()` 只由一次性 checkpoint-init 任务调用，管理专用 `checkpoint` schema。Flyway 管自定义 commerce/agent 表。连接明确设置 search_path，并验证 current_schema 与实际表位置。运行账号只获必需 DML/sequence 权限；初始化账号不提供给常驻服务。

`thread_id = run_id`（UUID）；图状态由官方 checkpoint 保存。AgentRun 只存索引、所有者、展示状态/版本和配置，不复制 state_json 为第二恢复真相。恢复以 checkpoint 为准，更新展示投影。等待节点前的副作用可能重放：持久化操作意图、幂等 API、重放测试缺一不可。不要自建完整 checkpointer 或复制第三方 DDL。

依赖版本在 M0 成功后写入 uv.lock；升级时重新跑空库初始化、重复初始化、WAITING_USER/WAITING_APPROVAL 恢复和提交后崩溃测试。不根据包名猜测版本号。

## ADR-04：权限而非共享密码

PostgreSQL 17 一个实例；bootstrap 管角色/schema；app_migrator 管自定义 DDL；checkpoint_migrator 仅管 checkpoint；commerce_runtime 与 agent_runtime 仅管各自 DML。agent_runtime 不继承 commerce 权限，所有运行角色非 superuser、非 owner、无 CREATE/CREATEROLE/BYPASSRLS。关闭 public schema 的非必要 CREATE；新表的 default privileges 也要维护。使用运行账号实际执行越权 SQL 并断言 permission denied。

## ADR-05：身份与恢复

dev/eval 使用本地产生的 RSA 密钥和预置用户的短期 JWT。Java/Python 只持公钥并验证 alg=RS256、issuer、audience、exp、subject。私钥仅在本地生成令牌脚本使用，不进入镜像/Git。认证令牌仅为本次请求的运行时上下文，不保存到 prompt/checkpoint/log。

审批由独立 APPROVER 身份调用 Java；恢复由原客户触发，Java 提供所有者可读的单条审批查询。服务重启或 token 过期后，客户用新有效 token 继续，不借用审批人 token，也不引入完整身份平台。

## ADR-06：策略可替换，基线不复制系统

DecisionPolicy 有相同的 State 输入和 Action 输出。基线与 Agent 共享同一个意图/订单线索提取器、工具、安全执行器、图持久化和评分器。基线使用固定证据顺序及合理条件分支，也会澄清/审批/安全停止。Agent 才动态选择下一证据。两者不读取 oracle、case_id 或期望结果。模型与预算一致；额外调用成本单独报告。允许结果为没有优势。

## ADR-07：政策直查与结果措辞

使用 ruleCode/ruleVersion 对应的 policyCode/policyVersion 查询本地版本化文本；无向量 DB、嵌入、reranker 或检索召回率目标。政策文件只解释，不改变执行规则。缺少政策时说明无法引用，不因文案缺失猜规则。返回“申请创建/待审批/已拒绝/自动处理停止”，从不把申请说成到账或工单已接手。

## ADR-08：可复现的是条件与证据，不是逐字输出

业务时钟与 fixture 固定；JWT 用真实认证时钟。确定性测试不使用真实模型；真实模型 final test 每例初始 3 次，保留逐次数据、均值与波动及模型配置，关键不稳定案例增加次数。test 不能用于调 prompt；后续优化只看 dev，提前登记后再进行有限 final 比较。详见 evaluation.md。

## 主要来源（官方资料；访问 2026-09-15）

- Spring Boot 3.5 系统要求：https://docs.spring.io/spring-boot/3.5/system-requirements.html
- GPT-4.1 mini 能力与快照：https://developers.openai.com/api/docs/models/gpt-4.1-mini
- LangGraph persistence：https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- 官方 PostgreSQL checkpointer 包：https://pypi.org/project/langgraph-checkpoint-postgres/
- PostgreSQL schemas/privileges：https://www.postgresql.org/docs/current/ddl-schemas.html

这些资料支持接口行为，不等于已验证当前项目组合。M0 探针结果才是接入门的证据。
