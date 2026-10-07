# docs/ 索引

本目录只放三类东西：**地图**、**规则**、**记录**。规格放 `specs/`，进度放根目录的 `PROJECT_PROGRESS.md`。

| 文件 | 职责 | 什么时候读 |
|---|---|---|
| [`PROJECT_ARCHITECTURE.md`](PROJECT_ARCHITECTURE.md) | 全项目总图：Web / Agent Service / Java Backend / PostgreSQL / Docker / Eval 的关系，以及完整请求链路 | 需要判断"某个东西在总图的哪一层、连接谁"时 |
| [`LEARNING_PROTOCOL.md`](LEARNING_PROTOCOL.md) | Map-first 教学协议：定位卡、固定教学顺序、面试检查点、A/B-class | 要讲解、要实现、要调试之前 |
| [`devlog/README.md`](devlog/README.md) | devlog 的模板与记录原则 | 写当天记录之前 |
| `devlog/YYYY-MM-DD.md` | 当天真实发生的事：决策、踩的坑、验证证据、Git 证据 | 想复盘"当时为什么这么定"时 |

## 进度与规则在哪里

- **进度 / 当前任务 / 下一步**：唯一入口是 [`PROJECT_PROGRESS.md`](../PROJECT_PROGRESS.md)；
- **协作规则与文档纪律**（哪份文件负责什么、"能指不断言"、历史不回改）：[`AGENTS.md`](../AGENTS.md) §4；
- **任务清单与每条任务的验收证据**：[`tasks.md`](../specs/002-commerce-after-sales-agent/tasks.md)；
- **API / Tool / Error 契约**：[`contracts/`](../specs/002-commerce-after-sales-agent/contracts/)；
- **模块怎么跑**：[`agent-service/README.md`](../agent-service/README.md)、[`web/README.md`](../web/README.md)。

## 本目录的写法

- 文档纪律不在本文件重复，见 `AGENTS.md` §4；本文件只负责回答"**哪个字在哪个文件里**"。
- 新增长文之前先问一句：它属于**地图 / 规则 / 记录**里的哪一类？答不出来就先不要加。
- 需要引用现状时**指路**，不要把"当前是 T0xx"抄进来——抄一份就多一份会过期的真相。
