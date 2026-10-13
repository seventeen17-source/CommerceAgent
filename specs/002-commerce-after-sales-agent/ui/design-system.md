# UI-1.0 视觉系统与通用UX

## 图片中的语义修订（布局保持）

1. Customer删除58%进度；节点数不代表剩余时间。POST未返回且无Run ID时只显示“正在处理请求”，不得模拟节点推进。
2. 提交成功后原表单变只读请求摘要，撤掉提交按钮；删除保存草稿、帮助中心等未定义能力。进度页不能再次发起同一请求。
3. Workspace底部只显示当前验证状态，不同时显示Pending与预期成功。演示场景切换可对比两个状态，不能混入Live。
4. Dashboard未经历审批时Handoff显示“不适用”，不能整条绿勾。Safe Stop用中性盾牌；红色表示实际失败，未执行不是调用失败。
5. Permission写“审批通过且重新校验后可执行”。白名单允许不等于此刻获准写入。
6. 阈值300元、240小时、指标326、负责人、健康灯均是示例；无来源不渲染事实值。Refund Created是申请创建，不是到账；Confirmed不能替换后端业务状态枚举。
7. SAFE_STOP不保证此前零写入；未知结果应写“已停止继续执行，已有写入结果待确认”。终态停止不能画成可恢复暂停。
8. 人工接管入口本期打开已有工单/停止上下文只读详情，不伪造接单操作；用户取消按钮没有生产契约前不提供。
9. 参考图里的 DEMO-003 是**越界样例**（订单金额 ≥ 该条规则的审批阈值），不是默认样例。README、演示视频与对外截图默认使用**未越界**路径；越界等待只作为对照。三张图里的 326 / 91.4% / 21 / 7 / ¥300 全部是示例值，不得作为事实渲染。
10. 不存在“自动审批”。审批只在越界时发生且必须由人做决定；未越界是**直接执行**。界面与材料一律写“未越界直接执行”或“免人工完成并核验”，不写“自动审批”“AI 自动批准”。

## 设计值

| Token | 值 |
|---|---|
| background/surface | #F5F8FC / #FFFFFF |
| sidebar/text/muted | #102744 / #10213F / #526581 |
| primary/tint | #0057E5 / #EDF4FF |
| border/divider | #DCE5F1 / #EAF0F6 |
| verified foreground/background | #087443 / #EAF8EF |
| waiting foreground/background | #8A4B00 / #FFF5E4 |
| failure foreground/background | #B42318 / #FFF0EE |
| neutral foreground/background | #526581 / #EFF3F8 |
| font | Inter(仅有本地资源时), Segoe UI, PingFang SC, Microsoft YaHei, sans-serif |
| identifiers | ui-monospace, Consolas, monospace；允许换行、复制 |
| type/line height | H1 24/32 600；H2 18/26 600；正文14/22；辅助12/18；指标30/38 |
| spacing | 4/8/12/16/24/32；卡片padding20；页面padding24 |
| radius | 卡片12；按钮8；徽标6 |
| controls | 桌面高40，移动44；左右padding16 |
| icons | 单一线性图标集，20px，禁止机器人头像/emoji混用 |
| shadow | 卡片无；浮层0 8px 28px rgba(16,39,68,.12) |
| animation | hover120ms，抽屉160ms；reduced-motion关闭；不模拟运行 |

这些是实施标准值，不声称从图片精确测量。状态始终带图标和文字。对比度实测达到普通文本4.5:1，焦点与大字3:1；浅背景上的状态文字用表中深色。

## 外壳/响应式

- 基准1600×1000；侧栏224px；内容宽=viewport-224-48；gap16；头部最小112px。1280–1439侧栏192、padding16、gap12。
- 1024–1279侧栏72px图标轨，有tooltip/aria-label；Workspace右栏变上下文抽屉。小于1024导航抽屉，Workspace“任务/执行/依据”三tab；移动390×844单栏，不整体缩放桌面。
- 页面自然纵向滚动；队列超过8条可局部滚动。Verification随内容，不固定遮挡操作。禁止为了首屏齐全缩小正文。
- **导航与路由见 [console-ia.md](console-ia.md)**（UI-1.1 Console IA 冻结，T104）。导航名固定为：Mission Center / Run Replay / Case Context / Human Collaboration / Safety Center / Enterprise Dashboard；Customer Portal 为独立入口（`#/portal`），Flow Playground 仅开发环境。会话入口放侧栏底部。
- 路由只存ID/筛选，不能放token、请求原文、授权金额、幂等键。深链接先认证再授权读取。返回列表恢复筛选/滚动。账号切换立即清空任务/缓存，旧响应按identity generation丢弃。

## 组件合同

| 组件 | 内容 | UX |
|---|---|---|
| RunHeader | runId、状态、请求来源、订单、负责人来源 | 复制ID；缺原文显示不可用，不让模型补写；业务Owner≠操作负责人 |
| RunListItem | ID、任务摘要、状态、更新时间 | Enter/点击切换当前Run；三栏同步；返回保留位置 |
| TraceNode | stableId、阶段、状态、Tool、输入/输出摘要 | 点击更新右栏；展开详情；重复调用逐次保留；未发生灰色 |
| EvidenceCard | 事实、来源、观测时间、历史/当前 | 点来源打开抽屉；无观测时间不编造；不是每次GET都刷新历史证据 |
| BoundaryCard | 提议动作、约束、可退金额、审批阈值、当前可执行性 | 只解释确定性规则结果；同一组件两态，差异只来自事实：**未越界→直接执行** / **金额≥阈值→越界，已暂停等待审批**；阈值无权威来源时只写“业务规则要求人工审批”，不填示例数字 |
| VerificationCard | 状态、动作、资源、确认强度、时间 | 工单创建响应确认≠独立权威回读 |
| OrderCard | 摘要、订单号、状态、时间、金额/币种可空 | 无图片时不留图片洞；订单归属仍服务端校验 |
| Dialog | 动作、绑定对象、金额、确认/取消 | 480px/max(100%-32)；默认焦点取消；focus trap；关闭回原按钮 |
| Drawer | 标题、结构化明细、来源 | 桌面440px，移动全屏；Escape关闭；不默认输出raw JSON |
| FeedbackPanel | loading/empty/error/forbidden/retained/stale | 保持区域尺寸；失败不当空数据；重读与重发分开 |

按钮：Idle→Submitting→Confirmed/Unknown/Error；写未知不自动重试、不乐观更新。读请求可重试。焦点环2px蓝+2px间隔；字段错误关联aria-describedby；结果使用polite live region。弹窗外关闭不能取消已经发出的写请求。

## 全局状态文案

加载：正在读取；空：说明范围和下一步；未知：暂无法确认；回收：详细记录已按保留策略回收；无权限/不存在：记录不存在或无法访问；过期：上次获取于…，刷新失败。保留旧数据只能标stale，切身份必须清除。

客户等待态用“等待你确认订单/等待人工审核”，企业可同时展示原始枚举。COMPLETED只说明Run结束；必须核验成功且资源匹配才说申请已创建。失败不自动承诺零写入。审批通过不等于退款完成。

## 呈现约束（智能可见性）

1. 每个“智能”元素背后必须有一个**已存在、可追溯**的字段；没有字段就登记任务，不画、不动效、不造进度。禁止为了显得智能而模拟推理、模拟实时或伪造百分比。
2. 只呈现**已发生的事实与确定性规则结果**（证据、规则码/版本、阈值比对、写入与核验状态、耗时、重试），不呈现模型隐藏推理。不确定必须显式，不用绿色表示。
3. 智能的默认叙事是**有边界的自主**：默认自主完成，越界才暂停。界面上“未越界直接执行”的路径必须是默认画面；等待审批是对照，不是首页印象。
4. 术语：禁用“自动审批”“AI 自动批准”。A（免人工完成并核验）与 H（人工介入）计数口径见 P07；引用示例值时必须同时展示 Demo 标识或真实来源。
