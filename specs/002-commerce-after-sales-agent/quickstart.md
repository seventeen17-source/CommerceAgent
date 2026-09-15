# 编码入口与验收手册

状态：**这是实施验收计划，不是已经可运行应用的安装教程。** 当前未生成应用源码；下面的目标命令由对应任务实现后才可执行。不要将命令存在误认为测试通过。

## 现在就做

检出 `002-commerce-after-sales-agent` 分支，阅读根目录 AGENTS.md，然后执行 tasks.md 的 T001–T008。保留已有 Spec Kit 工具，不运行历史 001 的研究任务；不要重新生成另一个总方案。

Windows 基础检查（已安装的工具可直接执行）：

```powershell
git status --short
java -version
python --version
uv --version
node --version
npm --version
docker version
docker compose version
```

有未提交本地改动先保留，不使用 reset --hard 或 git clean 清空。M0 记录可用环境和阻塞，不编造安装版本。

## 编码后必须提供的启动契约

以下是目标接口，不是现在已经存在的脚本：

```powershell
# 复制 .env.example 为本地 .env；生成本地 RSA 密钥与测试令牌，不提交
# 具体命令由 T009 写入 README，禁止在聊天/日志输出私钥
docker compose -f infra/compose.yaml up --build
# 首次必须按 bootstrap -> flyway -> checkpoint-init -> runtime 顺序
# README 必须说明正常重启与仅限测试的销毁数据方式
```

默认只绑定 localhost；Web 5173、Agent 8000、Java 8080，数据库仅内部网络或显式 localhost dev 端口。启动完成时 bootstrap/migrate 正常退出，三个应用健康；运行账户没有迁移凭据。没有 LLM 密钥可运行离线测试，不可演示为真实模型成功。

## G0：解除技术风险

成功：真实模型返回经过 schema 验证的单工具请求，非法参数被阻断；saver 在 checkpoint schema 初始化，可重复启动；进程重启能恢复等待；agent_runtime 访问 commerce 被拒绝。仅模拟测试成功时 G0 的 live 子项仍未通过。

## G1：退款申请切片

预置 customer-001（实际 UUID 由 fixture 固定）；只有一个相关订单，SHIPPED，停滞 120 小时以上，金额 19900 分，STANDARD。
请求“我的耳机一直没收到，不想要了”。验证一个 REFUND_ONLY CREATED 申请，order_id 正确、金额 19900，operation 查询成功；trace 存在，最终文本只说申请创建。重复同 clientRequestId/operationId 与模拟写后超时，再查询申请数量仍为一。

## G2：退货、澄清和 Agent 价值

同类请求放在 DELIVERED 三天的订单上应是 RETURN_REFUND；两个耳机订单时 WAITING_USER、零申请。客户选定订单后恢复；无效/他人输入不成功。
对 6 个以上 Agent-critical dev 案例和诚实基线比较：记录证据选择、成功/失败、额外调用和成本。不要求 Agent 必然获胜；四个不同 if 分支不算已证明模型价值。

## G3：审批与恢复

订单金额 150000 分触发审批。customer 只能创建/查询自己的审批；approver 能决定；等待时申请数量零。重启 Python 后用客户有效 token 调 continue，重新查询权威批准并完成唯一申请。检查批准金额/动作/用户/order/run/版本与期限绑定。

必须另外测试：拒绝、过期、跨绑定、已消费、两个并发 continue、重复创建审批、写提交后但 checkpoint 前重启。查看 Java 的权威 snapshot，不能只相信页面成功提示。

## G4：安全停止和政策

物流持续失败/质量自报/不支持类别：不写申请，DENIED 或 SAFE_STOP，说明需要人工联系且没有创建工单。政策直查使用后端指定 code/version；缺失时不编引用；带注入的文本不影响鉴权、工具或规则。

## G5：交付证据

目标命令须由编码阶段实现并在真实 README 校验：

```text
Java: commerce-backend/mvnw verify (Windows 使用 mvnw.cmd)
Python: cd agent-service; uv run pytest
Web: cd web; npm ci; npm run build
Eval offline: CLI runner + dev fixtures + deterministic policy/model doubles
Eval live: 明确 --live、模型配置、final split、3 repeats 和调用/token预算
```

交付 60 个案例清单、30 个确定性安全测试、两策略重复真实模型报告及原始 JSONL，说明哪些指标 unknown/partial。检查新克隆空库启动、迁移重复执行、无 secrets、接口合同验证。演示约 90 秒：正常申请 + 澄清或审批 + 一项失败/恢复；轨迹内嵌，不需独立看板。

## 退出条件

GitHub/README 仅标记实际通过的 G；测试未运行或失败必须保留。达到 G1 但未达到 G5 是可运行切片，不是完整 V1；不写普遍安全、真实支付或保证提效的宣传。
