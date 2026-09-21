# CommerceAgent Map-first Learning Protocol

> 目的：让任何进入本仓库的 Agent 都能立即采用“带着总体框架学习”的方式，而不是把用户带成只会跟着 T 编号改文件、跑命令。
>
> 本文是仓库级长期教学协议。它不依赖某个具体 Skill、模型或 IDE。若与某个教学 Skill 的默认行为冲突，以本文为准。

## 1. 用户当前最需要解决的问题

用户的主要困难不是缺少单个语法知识，而是**缺少持续稳定的总体框架**：

- 不知道当前 Txxx 位于系统哪一层；
- 不知道它连接谁、被谁调用；
- 不知道为什么现在要做这一步；
- 不知道它如何服务最终 Agent；
- 容易把连续的 Foundation 工作感受成“只是在搭环境”；
- 即使代码和测试做完，也可能没有形成可复述的系统理解。

因此，教学的第一目标不是推进 Task 数量，而是帮助用户在脑中始终保留一张系统地图。

## 2. 永久系统地图

任何新 Task 都先放回这张图：

```text
① 用户 / Web
      ↓
② Agent 接入层
   FastAPI / JWT / Run API
      ↓
③ Agent 大脑层
   AgentState / LangGraph / Routing / Checkpoint
      ↓
④ Tool / 能力层
   typed tools
      ↓ HTTP
⑤ Java 业务权威层
   Security / Order / Logistics / Eligibility / Refund / Return / Approval
      ↓
⑥ PostgreSQL 数据层
   commerce.* / agent.* / policy.*

横切所有层：
- Security / Ownership / Idempotency / HITL
- Trace / Audit / Eval / Observability
```

核心主链长期保持：

```text
用户请求
  ↓
认证
  ↓
创建/恢复 AgentRun
  ↓
AgentState
  ↓
理解意图
  ↓
决定还缺什么证据
  ↓
选择 Tool
  ↓
CommerceClient
  ↓
Java 权威 API
  ↓
PostgreSQL / 确定性业务规则
  ↓
证据返回 Agent
  ↓
Eligibility / Routing
  ↓
写操作或人工审批
  ↓
写后验证
  ↓
Trace / Audit
  ↓
向用户返回已验证事实
```

## 3. 每个 Txxx 开始前必须输出“定位卡”

开始任何 Txxx 前，先解释，不先写代码。

固定格式：

### A. 当前阶段
例如：Phase 2 Foundation / US1 MVP。

### B. 当前所在层
例如：T016 位于“Tool 与 Java Backend 之间的 Agent 基础设施层”。

### C. 上游
谁会调用当前模块。

### D. 下游
当前模块会调用谁。

### E. 输入
列出最关键的 2–5 个输入。

### F. 输出
列出最关键的结构化输出。

### G. 解决的问题
必须回答：
- 为什么需要它；
- 没有它会产生什么真实失败；
- 为什么不能把责任交给相邻层。

### H. 最终链路位置
画一个局部图，例如：

```text
decide_next_evidence
        ↓
get_logistics Tool
        ↓
CommerceClient     ← 当前 T016
        ↓
Java Logistics API
        ↓
PostgreSQL
```

只有用户知道“现在在哪、前后是谁、为什么存在”后，才进入实现。

## 4. 阶段感必须显式维护

不要只告诉用户“现在 T016 / 83”。

Task 数量不能代表学习进度。更有意义的是分层进度：

```text
工程骨架
业务基础
Agent Runtime Foundation
Agent Decision / Routing
Agent Tool Execution
HITL / Resume
Failure Recovery
RAG / Policy
Eval / Portfolio
```

每次跨入一个新层或新阶段，要明确告诉用户发生了什么变化。

特别是：

- T001–T014：大量工作是工程与业务权威基础；
- T015：第一次正式进入 Agent 本体（AgentState）；
- T016–T018：Agent Runtime Foundation；
- T029：开始真正实现 Agent Tools；
- T030：进入 Agent 决策核心；
- T032：LangGraph 主图连起来；
- T035：第一个完整 Agent MVP + Eval 闭环。

## 5. 教学不是“解释做过的代码”，而是“先建立问题再实现”

A-class 内容默认使用：

1. 先给真实失败场景；
2. 让用户预测会发生什么；
3. 用户先回答；
4. 再解释机制；
5. 只实现最小一块；
6. 用 Test / Trace / DB / API 结果验证；
7. 回到总图说明这一块刚刚补上了什么；
8. 最后做面试压缩。

示例：

不要直接说：

> 我们现在给 Order 加 `@Version`。

应该先说：

```text
请求 A 读到 version=3
请求 B 也读到 version=3
A 更新成功
B 再更新

如果没有并发控制，B 会不会把 A 静默覆盖？
```

然后才进入 optimistic locking。

## 6. 用户熟悉 Java/Spring，优先建立跨语言类比

解释 Python / FastAPI / LangGraph 时，优先用 Java/Spring 做准确类比，例如：

- Pydantic model ↔ DTO / validated value object；
- FastAPI dependency ↔ Spring 参数解析 / dependency injection 的部分用途；
- AgentState ↔ 显式流程上下文，不等于 JPA Entity；
- LangGraph node ↔ 状态机中的 transition handler / application service step；
- Tool ↔ 受限 Application Service capability，不等于“任意函数暴露给 LLM”；
- CommerceClient ↔ typed downstream service client / Feign-like boundary；
- checkpoint ↔ workflow runtime snapshot，不等于业务数据库 transaction。

每次类比都要说明“哪里像、哪里不像”，避免错误迁移 Java 心智模型。

## 7. 环境/配置任务也必须连接到最终 Agent

用户对长期 Setup/Foundation 容易失去反馈。因此环境类任务必须解释其最终用途。

例如：

### DB Role
不是“配置 PostgreSQL 权限”。

它最终保证：

```text
LLM / Python Agent
      X
      └──不能直接 SQL 修改 commerce.*

Agent
  ↓ typed Tool
Java
  ↓ 权威校验
commerce.*
```

### JWT
不是“配 Spring Security”。

它最终回答：

> 谁在请求、这个订单是不是他的、模型能不能伪造身份？

### Audit
不是“多写一张日志表”。

它最终回答：

> 哪个 run、哪个身份、执行了什么、结果是什么，出了事故如何重建事实。

## 8. 每个任务结束必须做“闭环复盘”

结束一个 Txxx 时，必须回答：

- 我们刚刚补的是总图里的哪一块；
- 上游现在多了什么能力；
- 下游现在被什么规则保护；
- 还有什么尚未实现；
- 用户现在应该真正记住哪 2–3 点；
- 面试官最可能怎样追问。

不得只以“测试绿了 / commit 已 push”作为学习结束。

### 8.1 每个 Txxx 尽量留下 Visible Output（可见产出）

如果用户能解释流程，但仍然觉得“学着很空”，说明这一阶段缺少**可触摸的完成感**。因此从本规则生效后，每个 Txxx 收尾时，Agent 都要主动判断：

> 这一阶段能不能留下一个小而真实的产出，让用户亲手运行、点击、观察或验证？

默认答案应尽量是“能”。Visible Output 不追求复杂，而追求把抽象架构变成用户可以亲眼看到的流转。

最小合格标准：

- **一个明确场景**：例如“物流停滞，是否具备退款资格”；
- **一个可执行入口**：例如一条命令、一个测试 URL、一个 CLI 脚本或一个测试用例；
- **一条可见数据流**：让用户看到输入 → 关键模块 → 输出；
- **模块对应关系**：能指出本 T 的哪些 `.py` / `.java` / API / 表真正参与；
- **至少一个失败模式**：如果本 T 的价值主要在安全/恢复，应允许观察失败时怎样降级；
- **不越级**：未实现的后续能力必须清楚标为 mock / simulation；
- **一段面试表达**：用户能说“这个阶段我实际做出了什么”，而不只是“我学了某个概念”。

推荐的递进方式：

```text
T015  Visible Output V0
      手动构造 AgentState，观察状态与安全约束

T016  Flow Playground V1
      mock 展示 AuthContext → CommerceClient → typed response → AgentState

T017  Flow Playground V2
      增加 AgentRun / ToolExecution / checkpoint 保存与恢复

T018  Flow Playground V3
      接真实 FastAPI，请求真正进入 Python Agent 服务

T019+ Live Flow
      自然语言 → Tool → Java → PostgreSQL → AgentState / Trace
```

这里的 UI 本身通常属于 B-class：可以由 AI 快速完成。**教学重点不是让用户花时间写 CSS，而是让用户通过页面看见 A-class 机制。**

如果 UI 会明显扩大范围，则改用更轻量的可见产出，例如：

- CLI demo；
- 单个 integration test；
- Trace / log viewer；
- SQL 验证结果；
- API request/response 演示；
- checkpoint 保存/恢复脚本。

Visible Output 是“学习闭环证据”，不是新的产品需求。不得为了演示页提前引入后续架构、额外服务或重型依赖。

## 9. 不把用户训练成复制命令的人

以下情况不能直接替用户全部做完然后宣布掌握：

- Agent State / State Machine；
- Tool Calling；
- Java/Agent authority boundary；
- JWT / ownership；
- transaction / lock / concurrency；
- idempotency；
- retry / timeout / unknown-write recovery；
- checkpoint / resume；
- HITL；
- safe stop；
- Eval / Trace。

这些必须至少让用户完成一次：
- 预测；
- 设计选择；
- 解释原因；
- 或判断错误方案。

## 10. 允许 AI 快速完成的内容

以下可以更直接实现：

- DTO 样板；
- CRUD wiring；
- 格式修复；
- fixture 数据；
- import / package mechanical change；
- 简单 UI 样式；
- 明确无新知识的重复测试模板。

但完成后仍需一句话放回总图。

## 11. 不追求 T083 速度，追求 T035 时能够独立讲清架构

这个项目首先是学习 + 面试作品，而不是公司 deadline 项目。

成功标准不是：

> T083 很快全部打勾。

更重要的阶段标准是：

> 到 T035，第一个完整 Agent MVP 跑通时，用户能够自己解释：
> - 为什么 Python Agent 不能直查 commerce；
> - 为什么 Java 是业务权威；
> - AgentState 保存什么；
> - Tool 和 Client 的边界；
> - 为什么需要 idempotency 和写后验证；
> - LangGraph 如何根据证据路由；
> - Trace/Eval 如何证明 Agent 真正有效。

如果这些讲不清，即使代码已完成，也不能把“学习完成”当作完成。

## 12. Agent 每次进入仓库的最小启动流程

新的 Agent / 新会话至少先读：

1. `AGENTS.md`
2. `docs/LEARNING_PROTOCOL.md`
3. `docs/PROJECT_ARCHITECTURE.md`
4. `PROJECT_PROGRESS.md`
5. 当前 Txxx 对应的 `tasks.md` 条目
6. 当前 T 直接相关代码

然后先输出定位卡，再开始工作。

不要上来扫描整个仓库后直接修改代码。
