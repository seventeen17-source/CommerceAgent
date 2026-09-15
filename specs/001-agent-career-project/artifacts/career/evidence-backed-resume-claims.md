# CommerceAgent Evidence-backed Resume Claims

Only `approved` claims may be written as achieved outcomes. Until implementation/evaluation exists, claims remain `target`.

| claim_id | text | status | evaluation_run_refs | dataset_version | metric_definition | limitations | reviewed_at |
|---|---|---|---|---|---|---|---|
| C001 | 构建企业电商售后执行 Agent，完成订单、物流、规则、退款/退货与工单系统的多步 Tool Calling 闭环 | target | | | qualitative scope | 尚未实现；当前为设计目标 | |
| C002 | 通过 Java 后端将权限、退款资格、金额、状态机和幂等与 LLM 决策隔离 | target | | | architecture property | 尚未通过代码/测试验证 | |
| C003 | 在版本化离线测试集上达到任务成功率 [待实测] | target | required when measured | required | successful_cases / total_cases | 需披露模型、工具权限、数据规模 | |
| C004 | Tool Selection Accuracy 达到 [待实测] | target | required when measured | required | acceptable tool-path cases / evaluated cases | 多轨迹场景需使用谓词而非唯一序列 | |
| C005 | Unsafe Action Rate 为 [待实测] | target | required when measured | required | unsafe writes or forbidden actions / safety cases | 目标可为 0，但不得提前写成结果 | |
| C006 | Duplicate Write Rate 为 [待实测] | target | required when measured | required | logical actions producing duplicate write / write-retry cases | 需覆盖超时后的模糊完成状态 | |
| C007 | 通过 Prompt Injection、越权订单访问和高风险审批测试 [待实测] | target | required when measured | required | safety-suite pass definition | 需列出具体攻击集 | |
| C008 | Baseline → V1 → Optimized 的任务成功率/成本/延迟变化为 [待实测] | target | required when measured | required | same-dataset comparable run | 环境或模型变化时必须重跑或标不可比 | |

## Approval rules

To change a claim from `target` to `measured`:
- implementation exists;
- an evaluation run id exists;
- dataset version exists;
- metric formula is fixed;
- raw result is reproducible;
- limitation is documented.

To change from `measured` to `approved`:
- result is independently reviewed against the run/dataset/config;
- no test leakage/cherry-picking issue remains;
- wording accurately reflects synthetic/local integration boundaries;
- `reviewed_at` is filled.

## Forbidden claims before evidence

Do not write:
- “成功率提升 X%”;
- “延迟降低 X%”;
- “实现零越权/零重复退款”;
- “接入真实电商/支付生产系统”;
- “支持百万级并发”;

unless the exact claim is actually tested and evidenced.