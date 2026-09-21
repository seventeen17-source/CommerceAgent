import { useMemo, useState } from 'react'
import './App.css'

type ScenarioId =
  | 'normal'
  | 'unknown-role'
  | 'logistics-timeout'
  | 'invalid-order'
  | 'unknown-action'
  | 'trace-mismatch'

type StepStatus = 'pending' | 'success' | 'warning' | 'blocked'

type FlowStep = {
  id: string
  title: string
  file: string
  action: string
  input: string
  work: string
  output: string
  status: StepStatus
  note?: string
}

type Scenario = {
  id: ScenarioId
  label: string
  summary: string
}

const scenarios: Scenario[] = [
  { id: 'normal', label: '正常流程', summary: '身份 → 订单 → 物流 → eligibility 全部通过' },
  { id: 'unknown-role', label: '未知角色', summary: 'Java 返回 Python 不认识的 role，identity.py fail closed' },
  { id: 'logistics-timeout', label: '物流 Timeout', summary: '读请求结果未知，但操作无副作用，可进入有限重试路径' },
  { id: 'invalid-order', label: '非法 orderId', summary: '模型输入试图改写 URL，客户端在发请求前拒绝' },
  { id: 'unknown-action', label: '未知 allowedAction', summary: 'Java 新增动作值，传输层接受，执行层必须 SAFE_STOP' },
  { id: 'trace-mismatch', label: 'traceId 不一致', summary: 'header 与 error envelope 不一致，使用已校验 correlation id' },
]

function statusLabel(status: StepStatus) {
  if (status === 'success') return '通过'
  if (status === 'warning') return '警告'
  if (status === 'blocked') return '停止'
  return '等待'
}

function statusIcon(status: StepStatus) {
  if (status === 'success') return '✓'
  if (status === 'warning') return '!'
  if (status === 'blocked') return '×'
  return '·'
}

function buildSteps(scenario: ScenarioId): FlowStep[] {
  const normal: FlowStep[] = [
    {
      id: 'auth',
      title: '包装调用凭据',
      file: 'app/clients/auth.py',
      action: 'AuthContext',
      input: 'Bearer eyJhbGciOi...',
      work: 'SecretStr 脱敏；拒绝空白、CR/LF 和控制字符；不携带 user_id / role。',
      output: 'AuthContext(token=**********)',
      status: 'success',
    },
    {
      id: 'principal',
      title: '向 Java 求证当前身份',
      file: 'app/clients/commerce_client.py + models.py',
      action: 'GET /api/v1/me',
      input: 'AuthContext + X-Trace-Id',
      work: 'CommerceClient 发起请求；CurrentPrincipal 校验 Java JSON 的 userId / role 结构。',
      output: 'CurrentPrincipal(user_id="customer-001", role="CUSTOMER")',
      status: 'success',
    },
    {
      id: 'identity',
      title: '把 wire role 转成可授权角色',
      file: 'app/clients/identity.py',
      action: 'resolve_principal()',
      input: 'CurrentPrincipal(role="CUSTOMER")',
      work: '只接受 Agent 已知角色；不猜、不大小写归一、不提供默认角色。',
      output: 'PrincipalContext(user_id="customer-001", role=CUSTOMER)',
      status: 'success',
    },
    {
      id: 'orders',
      title: '定位耳机订单',
      file: 'app/clients/commerce_client.py + models.py',
      action: 'GET /api/v1/orders?productQuery=耳机',
      input: 'AuthContext + product_query="耳机"',
      work: 'Java 基于认证用户做 ownership 查询；Python 把 JSON 数组校验成 OrderSummary[]。',
      output: 'order-001 / Sony 耳机 / SHIPPED',
      status: 'success',
    },
    {
      id: 'logistics',
      title: '求证物流是否停滞',
      file: 'app/clients/commerce_client.py + models.py',
      action: 'GET /api/v1/orders/order-001/logistics',
      input: 'AuthContext + order_id="order-001"',
      work: '先校验 path segment，再调用 Java；LogisticsSnapshot 校验返回结构。',
      output: 'IN_TRANSIT / stalled_hours=82 / signed=false',
      status: 'success',
    },
    {
      id: 'eligibility',
      title: '求证售后资格',
      file: 'app/clients/models.py + commerce_client.py',
      action: 'POST /api/v1/after-sales/eligibility',
      input: 'EligibilityRequest(order_id="order-001", reason_code="LOGISTICS_STALLED")',
      work: '这是无副作用评估。金额由 Java 规则计算，Agent 不能自己提交 maxRefundAmount。',
      output: 'eligible=true / allowedAction=REFUND_ONLY / maxRefundAmount=399.00',
      status: 'success',
    },
    {
      id: 'state',
      title: '形成已验证业务事实',
      file: 'app/agent/state.py',
      action: 'AgentState',
      input: 'PrincipalContext + Order + Logistics + Eligibility',
      work: '只保存派生身份和结构化业务证据，不保存 raw JWT。T017 才负责持久化。',
      output: '当前结论：物流停滞 82h，Java 规则允许进入退款候选路径。',
      status: 'success',
      note: '此页面只是 T016 mock 教学模拟器；真实 LangGraph/Tool/FastAPI 流转尚未在这里执行。',
    },
  ]

  if (scenario === 'normal') return normal

  if (scenario === 'unknown-role') {
    return normal.map((step) => {
      if (step.id === 'principal') {
        return { ...step, output: 'CurrentPrincipal(user_id="customer-001", role="OPS_ADMIN_V2")' }
      }
      if (step.id === 'identity') {
        return {
          ...step,
          input: 'CurrentPrincipal(role="OPS_ADMIN_V2")',
          work: 'identity.py 不认识该 Java wire role，不猜测权限，抛 UnknownPrincipalRoleError。',
          output: 'ACCESS_DENIED → SAFE_STOP / ESCALATED',
          status: 'blocked',
          note: '后续订单、物流、退款资格都不应继续调用。',
        }
      }
      if (['orders', 'logistics', 'eligibility', 'state'].includes(step.id)) {
        return { ...step, status: 'pending', output: '未执行：身份边界已 fail closed' }
      }
      return step
    })
  }

  if (scenario === 'logistics-timeout') {
    return normal.map((step) => {
      if (step.id === 'logistics') {
        return {
          ...step,
          work: 'Java 没有返回可信答案，CommerceClient 抛 CommerceTransportError。',
          output: 'outcome_unknown=true / request_was_safe=true',
          status: 'warning',
          note: '物流查询无副作用，因此 Tool 层可在有限 retry budget 内重试；client 自己不会偷偷重试。',
        }
      }
      if (['eligibility', 'state'].includes(step.id)) {
        return { ...step, status: 'pending', output: '等待物流事实后再继续' }
      }
      return step
    })
  }

  if (scenario === 'invalid-order') {
    return normal.map((step) => {
      if (step.id === 'orders') {
        return { ...step, output: '模型给出候选 order_id="../../admin/users"', status: 'warning' }
      }
      if (step.id === 'logistics') {
        return {
          ...step,
          input: 'order_id="../../admin/users"',
          work: '_safe_path_segment() 在 HTTP 请求发出前拒绝 /、?、#、空白等危险路径字符。',
          output: 'UnsafeRequestParameterError(error_code="INVALID_PARAMETER")',
          status: 'blocked',
          note: '没有请求离开 Python 进程，所以这是已知本地失败，不存在 unknown outcome。',
        }
      }
      if (['eligibility', 'state'].includes(step.id)) {
        return { ...step, status: 'pending', output: '未执行：非法参数已阻断' }
      }
      return step
    })
  }

  if (scenario === 'unknown-action') {
    return normal.map((step) => {
      if (step.id === 'eligibility') {
        return {
          ...step,
          output: 'eligible=true / allowedAction=EXCHANGE / ruleVersion=4',
          status: 'warning',
          note: 'models.py 故意把 Java-owned allowedAction 保持为开放 string，因此不会解析崩溃。',
        }
      }
      if (step.id === 'state') {
        return {
          ...step,
          work: '传输层已成功接收新值，但当前 Agent 不认识 EXCHANGE，不能猜测它等价于退款或退货。',
          output: 'SAFE_STOP：unknown allowedAction="EXCHANGE"',
          status: 'blocked',
          note: '“解析宽，授权严”：远程新增合法值可抵达决策层，但未知值不能解锁业务写操作。',
        }
      }
      return step
    })
  }

  return normal.map((step) => {
    if (step.id === 'eligibility') {
      return {
        ...step,
        work: '模拟 Java 错误响应：Header X-Trace-Id=java-trace-403，JSON envelope.traceId=other-trace。',
        output: 'CommerceApiError(trace_id="java-trace-403")',
        status: 'warning',
        note: 'T016 post-review 修复：错误路径也统一使用 _correlate() 已校验的 correlation id。',
      }
    }
    if (step.id === 'state') {
      return {
        ...step,
        output: '未来 T017 持久化 trace_id="java-trace-403"',
        status: 'success',
        note: '这样 Agent ToolExecution 的 traceId 才能真实对应 Java 日志中的请求。',
      }
    }
    return step
  })
}

function App() {
  const [scenario, setScenario] = useState<ScenarioId>('normal')
  const [started, setStarted] = useState(false)
  const [openStep, setOpenStep] = useState<string | null>('auth')

  const steps = useMemo(() => buildSteps(scenario), [scenario])
  const activeScenario = scenarios.find((item) => item.id === scenario)!

  const chooseScenario = (id: ScenarioId) => {
    setScenario(id)
    setStarted(false)
    setOpenStep('auth')
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">CommerceAgent · Visible Output</div>
          <h1>T016 Flow Playground</h1>
          <p className="subtitle">把 Python Agent → Java 权威业务接口的调用链做成可点、可看、可解释的小产出。</p>
        </div>
        <div className="mock-badge">MOCK · 教学模拟器</div>
      </header>

      <section className="case-card">
        <div>
          <span className="section-kicker">固定案例</span>
          <h2>“我的耳机物流好久没动了，能退款吗？”</h2>
          <p>
            这个页面不会假装真正 Agent 已经完成。它只把 T016 已有代码边界可视化：
            <code>auth.py</code>、<code>models.py</code>、<code>identity.py</code>、
            <code>commerce_client.py</code>、<code>errors.py</code>，以及 T015 的 <code>state.py</code>。
          </p>
        </div>
        <button className="primary-button" type="button" onClick={() => setStarted(true)}>
          {started ? '重新演示流转' : '开始流转'}
        </button>
      </section>

      <section className="scenario-section">
        <div className="section-heading">
          <div>
            <span className="section-kicker">故障注入</span>
            <h2>切换一个真实工程问题</h2>
          </div>
          <p>{activeScenario.summary}</p>
        </div>
        <div className="scenario-grid">
          {scenarios.map((item) => (
            <button
              className={item.id === scenario ? 'scenario-chip active' : 'scenario-chip'}
              type="button"
              key={item.id}
              onClick={() => chooseScenario(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className={started ? 'flow-layout visible' : 'flow-layout'}>
        <aside className="flow-rail">
          <div className="rail-title">调用链</div>
          {steps.map((step, index) => (
            <button
              type="button"
              key={step.id}
              className={openStep === step.id ? `rail-step ${step.status} selected` : `rail-step ${step.status}`}
              onClick={() => setOpenStep(step.id)}
            >
              <span className="step-index">{String(index + 1).padStart(2, '0')}</span>
              <span className="step-copy">
                <strong>{step.title}</strong>
                <small>{step.action}</small>
              </span>
              <span className="status-dot" aria-label={statusLabel(step.status)}>
                {statusIcon(step.status)}
              </span>
            </button>
          ))}
        </aside>

        <div className="detail-panel">
          {!started ? (
            <div className="empty-state">
              <div className="empty-icon">→</div>
              <h2>点击“开始流转”</h2>
              <p>然后逐步查看每个 Python 文件的输入、职责和输出。</p>
            </div>
          ) : (
            steps.map((step) =>
              openStep === step.id ? (
                <article key={step.id} className="step-detail">
                  <div className="detail-header">
                    <div>
                      <span className="section-kicker">STEP DETAIL</span>
                      <h2>{step.title}</h2>
                    </div>
                    <span className={`status-pill ${step.status}`}>
                      {statusIcon(step.status)} {statusLabel(step.status)}
                    </span>
                  </div>

                  <div className="file-strip">
                    <span>对应代码</span>
                    <code>{step.file}</code>
                  </div>

                  <div className="io-grid">
                    <div className="io-card">
                      <span className="io-label">输入</span>
                      <pre>{step.input}</pre>
                    </div>
                    <div className="io-card">
                      <span className="io-label">做了什么</span>
                      <p>{step.work}</p>
                    </div>
                    <div className="io-card output">
                      <span className="io-label">输出</span>
                      <pre>{step.output}</pre>
                    </div>
                  </div>

                  {step.note ? <div className="note-box">{step.note}</div> : null}
                </article>
              ) : null,
            )
          )}
        </div>
      </section>

      <section className="map-card">
        <span className="section-kicker">MAP FIRST</span>
        <div className="architecture-line">
          <span>用户意图</span><b>→</b><span>Agent 假设</span><b>→</b><span>Tool</span><b>→</b>
          <span className="focus-node">CommerceClient · T016</span><b>→</b><span>Java</span><b>→</b><span>PostgreSQL</span>
        </div>
        <p>Agent 决定“要问什么”，Java 决定“业务事实是什么”。T016 就是两者之间的可靠权威通道。</p>
      </section>
    </main>
  )
}

export default App
