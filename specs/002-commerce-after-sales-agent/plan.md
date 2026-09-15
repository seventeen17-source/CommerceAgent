# 实施计划：先交付切片，再扩大覆盖

唯一业务规格：[spec.md](spec.md)。执行清单：[tasks.md](tasks.md)。本计划不声称应用已运行。

## 最小架构

Web（客户页 + 薄审批页；轨迹内嵌） → Python FastAPI/LangGraph → Java Spring Boot → PostgreSQL。
Python 同时使用受限数据库账号访问自己的 run/trace 和官方 checkpoint。Java 不调用 LLM。基线只替换 Python 的 DecisionPolicy；不复制服务。Web 首版使用请求/轮询，不做 SSE/WebSocket、独立看板或通用管理后台。

| 层 | 选型/责任 |
|---|---|
| Java | Java 21、Spring Boot 3.5.16、Maven Wrapper、Security/JPA/Flyway；订单读取、规则、售后申请、审批、操作去重、审计 |
| Python | Python 3.13、uv、FastAPI、Pydantic、httpx、LangGraph、官方 PostgreSQL checkpointer；模型适配、状态、工具、恢复、评测 |
| Web | React + TypeScript/Vite；Node 22.12+，脚手架实际可用版本锁入 lockfile |
| DB | PostgreSQL 17；commerce / agent / checkpoint；无 pgvector |
| 模型 | 初始 gpt-4.1-mini-2025-04-14，官方 SDK 的 Chat Completions tool calling；替换必须重新执行模型合同测试并记录配置 |
| 验证 | JUnit/Testcontainers、pytest、前端 build；OpenAPI 静态与实现合同检查；CLI 评测 |

上述是实现选择，不是已验证的安装组合。M0 必须实测解析依赖、锁版本、模型可访问性和恢复；不得静默换大版本。官方生成器无目标版本时记录失败并调整一项 ADR，不手工编造“已生成”的 wrapper/lockfile。

## 计划目录（由编码任务创建；当前不是已有应用）

```text
commerce-backend/
  src/main/java/com/seventeen17/commerceagent/
    security/ order/ aftersales/ audit/ common/
  src/main/resources/db/migration/
  src/main/resources/rules/
  src/test/
agent-service/
  app/api/ app/security/ app/clients/
  app/agent/                     # state / graph / policies / nodes
  app/tools/ app/llm/ app/trace/
  tests/
web/src/features/customer/       # 内嵌 trace / clarification
web/src/features/approvals/
knowledge/policies/              # 代码/版本精确匹配
infra/                          # compose、一次性迁移、dev key 生成
eval/
  datasets/v1/ runner/ scorers/ reports/
```

## 已裁决的复杂度

**Java 收缩**：订单与单包裹物流字段在订单模型中，不做商品/物流管理；规则为版本化资源文件，不做通用引擎；退款/退货共用 after_sales_requests 表与服务，actionType 区分。保留审批、操作记录、事务和审计，不做完整履约系统。

**运行方式**：一个 Python worker；每次 create/input/continue 请求推进图到完成或等待状态，不加后台队列。run 级 PostgreSQL session advisory lock 防止并发推进；数据库事务不得跨 LLM 网络调用。服务崩溃后锁释放，所有者以新有效 JWT 调用 continue 恢复。HTTP 断开不证明图失败；用稳定 clientRequestId 查询/重试。

**执行与展现**：官方 checkpoint 是图恢复真相；agent_runs 状态是可重建投影。inputId 记录与 checkpoint 中的已应用 inputId 去重，不能在重放时重复注入消息。生成 operationId 的 prepare_write 节点和外部写节点分开，先持久化写意图再执行。

**迁移**：基础初始化任务建立 schema/角色；Flyway 仅迁移自定义表；官方 checkpointer 仅迁移 checkpoint schema；之后分别授予 runtime DML 权限。初始化能重复执行，应用启动不持有迁移权限。

**安全降级**：US1 即包含有限重试、拒绝、SAFE_STOP 和权威查询；延后的是工单运营，不是安全退出。审批完成前的 M1 对需要审批的订单直接 SAFE_STOP，不放行。

## 里程碑与预算

目标窗口 6–8 周只在每周约 20–25 小时且 M0/G1 顺利时使用，不保证固定日期。建议总预算 160 小时：核心 120 + 缓冲 40；M0 8、M1 32、M2 16、M3 24、M4 8、M5 32 小时为规划额度而非工时事实。每周只有 15 小时时，不承诺同范围 8 周完成。

| 里程碑 | 可运行产物 | 停止条件 |
|---|---|---|
| M0 | 可调用模型工具合同、断电恢复小测试、DB 角色隔离 | 任何关键依赖未通过，不扩功能 |
| M1 | 唯一订单退款申请、验证、错误路径、12 个 dev 案例；最小基线和 CLI 评分 | 切片不能重复演示，先修，不建完整前端 |
| M2 | 退货分支、澄清恢复、Agent-critical 案例 | 禁止以四个 if 分支宣称 Agent 优势 |
| M3 | 高风险审批、重启继续、并发/未知写恢复 | 任何非法/重复业务写入，阻断交付 |
| M4 | 政策直查引用、有限人工联系提示 | 不添加 embedding/向量检索 |
| M5 | 60 例、冻结比较、30 个确定性安全测试、演示与复现 | 没有原始报告，不写数字成果 |

G1 后记录实际耗时与错误，再更新剩余预算。超预算先删视觉美化、额外文案、可选优化实验；不删权限、幂等、审批校验和实测报告。没有时间扩充时交付已完成切片并明确未完成范围，不把部分功能包装成完整 V1。

## 验证顺序

CI、Compose 最小启动、eval runner 与基线接口在 M1 出现；后面只扩充案例。单个任务完成须附命令、结果和失败说明。最终只保留一套 002 规格和契约；原 001 的规划循环不再执行。
