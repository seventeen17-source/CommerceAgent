import { useMemo, useState } from 'react'

type ScenarioId =
  | 'normal'
  | 'unknown-role'
  | 'logistics-timeout'
  | 'invalid-order'
  | 'unknown-action'
  | 'trace-mismatch'

type StepStatus = 'pending' | 'success' | 'warning' | 'blocked'
type LiveStepId = 'read-logistics' | 'check-eligibility' | 'create-run' | 'read-run' | 'read-events'

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
  live?: LiveStepId
}

type Scenario = {
  id: ScenarioId
  label: string
  summary: string
}

type CallResult =
  | { kind: 'idle' }
  | { kind: 'pending'; step: LiveStepId }
  | { kind: 'ok'; step: LiveStepId; status: number; body: unknown }
  | { kind: 'error'; step: LiveStepId; status: number | null; detail: string }

type CompletedLiveSteps = Record<LiveStepId, boolean>

const AGENT_API = '/agent/runs'
const COMMERCE_API = '/commerce/orders'
const ELIGIBILITY_API = '/commerce/after-sales/eligibility'

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

function buildLiveSteps(completed: CompletedLiveSteps, failedStep: LiveStepId | null): FlowStep[] {
  const statusFor = (id: LiveStepId): StepStatus => {
    if (completed[id]) return 'success'
    if (failedStep === id) return 'warning'
    return 'pending'
  }

  return [
    {
      id: 'read-logistics',
      live: 'read-logistics',
      title: '读取真实物流事实',
      file: 'LogisticsController.java + LogisticsService.java',
      action: 'GET /api/v1/orders/{orderId}/logistics',
      input: 'Bearer token + orderId',
      work: 'T024 通过 Vite dev proxy 直连 Java :8080；Java 从 principal 校验 ownership，再返回权威物流快照和 stalledHours。',
      output: 'status / signed / lastMeaningfulEventAt / stalledHours',
      status: statusFor('read-logistics'),
      note: '这是 T024 的真实 Java API 页面验收，不经过 Agent Tool；真正 Web → Agent → Tool → Java 链路在 T029/T032 接入。',
    },
    {
      id: 'check-eligibility',
      live: 'check-eligibility',
      title: '读取真实售后资格',
      file: 'EligibilityController.java + EligibilityService.java',
      action: 'POST /api/v1/after-sales/eligibility',
      input: 'Bearer token + orderId + reasonCode',
      work: 'T025 把已由 T020 验证过的 deterministic EligibilityService 正式接入当前 US1 主链；页面经 Vite dev proxy 调 Java :8080，Java 使用认证 principal、订单、物流和规则事实返回权威 EligibilityDecision。reasonCode 只是描述性上下文，不参与规则选择或金额计算。',
      output: 'eligible / allowedAction / maxRefundAmount / approvalRequired / ruleCode / ruleVersion / reasonCodes',
      status: statusFor('check-eligibility'),
      note: '这是 T025 的页面级验收：验证 deterministic EligibilityDecision 能通过真实 HTTP 边界被消费；仍不冒充 T029/T030/T032 才会完成的 Agent Tool / LangGraph 主链。',
    },
    {
      id: 'create-run',
      live: 'create-run',
      title: '创建并持久化 Agent Run',
      file: 'app/api/runs.py + app/trace/store.py',
      action: 'POST /api/v1/agent/runs',
      input: 'Bearer token + 用户请求',
      work: 'T018 验证身份与 ownership；T017 在同一事务中写入 AgentRun 和 version=1 的首个 Checkpoint。',
      output: 'runId / RUNNING / currentNode=created / version=1',
      status: statusFor('create-run'),
      note: '这是用公开 API 验证 T017 持久化，不是另开一套 T018 页面。',
    },
    {
      id: 'read-run',
      live: 'read-run',
      title: '读取持久化 Run',
      file: 'app/api/runs.py + app/trace/store.py',
      action: 'GET /api/v1/agent/runs/{runId}',
      input: 'Bearer token + runId',
      work: 'owner userId 进入 SQL 查询条件；只能读取自己的 Run，并返回数据库当前版本。',
      output: 'Run 状态、节点、stepCount、version',
      status: statusFor('read-run'),
    },
    {
      id: 'read-events',
      live: 'read-events',
      title: '读取 Checkpoint 与 Trace',
      file: 'app/api/runs.py + app/trace/store.py',
      action: 'GET /api/v1/agent/runs/{runId}/events',
      input: 'Bearer token + runId',
      work: '按顺序读取持久化事件；当前新 Run 至少应包含 version=1 的创建 Checkpoint。',
      output: 'checkpoint timeline + structured tool traces',
      status: statusFor('read-events'),
      note: '当前还没有真正执行 Tool，所以创建后 tool trace 数量为 0 是正确结果。',
    },
  ]
}

export function T016FlowPlayground() {
  const [scenario, setScenario] = useState<ScenarioId>('normal')
  const [started, setStarted] = useState(false)
  const [openStep, setOpenStep] = useState<string | null>('auth')
  const [token, setToken] = useState('')
  const [message, setMessage] = useState('我的耳机物流很久没动了，能退款吗？')
  const [runId, setRunId] = useState('')
  const [orderId, setOrderId] = useState('order-001')
  const [reasonCode, setReasonCode] = useState('LOGISTICS_DELAY')
  const [result, setResult] = useState<CallResult>({ kind: 'idle' })
  const [completedLiveSteps, setCompletedLiveSteps] = useState<CompletedLiveSteps>({
    'read-logistics': false,
    'check-eligibility': false,
    'create-run': false,
    'read-run': false,
    'read-events': false,
  })

  const failedStep = result.kind === 'error' ? result.step : null
  const steps = useMemo(
    () => [...buildSteps(scenario), ...buildLiveSteps(completedLiveSteps, failedStep)],
    [scenario, completedLiveSteps, failedStep],
  )
  const activeScenario = scenarios.find((item) => item.id === scenario)!

  async function callLiveStep(step: LiveStepId): Promise<void> {
    if (!token.trim()) {
      setResult({
        kind: 'error',
        step,
        status: null,
        detail: '请先填写真实 Bearer token。输入框里的灰字只是格式示例。',
      })
      return
    }
    if ((step === 'read-logistics' || step === 'check-eligibility') && !orderId.trim()) {
      setResult({ kind: 'error', step, status: null, detail: '请先填写 orderId。' })
      return
    }
    if (step === 'check-eligibility' && !reasonCode.trim()) {
      setResult({ kind: 'error', step, status: null, detail: '请先填写 reasonCode。' })
      return
    }
    if (step === 'create-run' && !message.trim()) {
      setResult({ kind: 'error', step, status: null, detail: '请先填写用户请求。' })
      return
    }
    if (
      step !== 'read-logistics' &&
      step !== 'check-eligibility' &&
      step !== 'create-run' &&
      !runId.trim()
    ) {
      setResult({
        kind: 'error',
        step,
        status: null,
        detail: '请先执行步骤 10 创建 Run，或在 runId 输入框中填入已有 ID。',
      })
      return
    }

    const path =
      step === 'read-logistics'
        ? `${COMMERCE_API}/${encodeURIComponent(orderId.trim())}/logistics`
        : step === 'check-eligibility'
          ? ELIGIBILITY_API
          : step === 'create-run'
            ? AGENT_API
            : step === 'read-run'
              ? `${AGENT_API}/${runId.trim()}`
              : `${AGENT_API}/${runId.trim()}/events`
    const init: RequestInit =
      step === 'check-eligibility'
        ? {
            method: 'POST',
            body: JSON.stringify({
              orderId: orderId.trim(),
              reasonCode: reasonCode.trim(),
            }),
          }
        : step === 'create-run'
          ? { method: 'POST', body: JSON.stringify({ message: message.trim() }) }
          : { method: 'GET' }

    setResult({ kind: 'pending', step })
    try {
      const response = await fetch(path, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token.trim()}`,
        },
      })
      const text = await response.text()
      let body: unknown = text
      try {
        body = JSON.parse(text)
      } catch {
        // Keep non-JSON proxy/service responses visible for diagnosis.
      }

      if (!response.ok) {
        setResult({ kind: 'error', step, status: response.status, detail: text })
        return
      }

      if (body && typeof body === 'object' && 'runId' in body) {
        setRunId(String(body.runId))
      }
      setCompletedLiveSteps((current) => ({ ...current, [step]: true }))
      setResult({ kind: 'ok', step, status: response.status, body })
    } catch (error) {
      setResult({
        kind: 'error',
        step,
        status: null,
        detail: `${String(error)} - 对应服务（Agent :8000 / Java :8080）是否已启动？`,
      })
    }
  }

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
          <h1>CommerceAgent Flow Playground</h1>
          <p className="subtitle">同一条售后链路，从 T016 教学模拟逐步长成真实 Agent 调试器。</p>
        </div>
        <div className="capability-badges" aria-label="当前验证能力">
          <span className="capability-badge mock">T016 · MOCK FLOW</span>
          <span className="capability-badge persisted">T017 · PERSISTED</span>
          <span className="capability-badge live">T018 · LIVE API</span>
          <span className="capability-badge live">T024 · LIVE JAVA</span>
          <button
            type="button"
            className="capability-badge live"
            onClick={() => {
              setStarted(true)
              setOpenStep('check-eligibility')
            }}
          >
            T025 · LIVE ELIGIBILITY
          </button>
        </div>
      </header>

      <section className="case-card">
        <div>
          <span className="section-kicker">固定案例</span>
          <h2>“我的耳机物流好久没动了，能退款吗？”</h2>
          <p>
            前 7 步把 T016 已有代码边界可视化，后续步骤在同一条调用链中接入真实接口：
            <code>auth.py</code>、<code>models.py</code>、<code>identity.py</code>、
            <code>commerce_client.py</code>、<code>errors.py</code>、T015 的 <code>state.py</code>，
            以及 T017/T018 的 Run 与 Checkpoint API。
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
              openStep === step.id && step.live ? (
                <article key={step.id} className="step-detail live-step-detail">
                  <div className="detail-header">
                    <div>
                      <span className="section-kicker">
                        {step.live === 'read-logistics' || step.live === 'check-eligibility'
                          ? 'LIVE STEP · JAVA BUSINESS AUTHORITY'
                          : 'LIVE STEP · T017 PERSISTENCE VIA T018 API'}
                      </span>
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
                      <span className="io-label">预期输出</span>
                      <pre>{step.output}</pre>
                    </div>
                  </div>

                  <div className="live-step-console">
                    <div className="live-step-form">
                      <label htmlFor={`token-${step.live}`}>Bearer token</label>
                      <textarea
                        id={`token-${step.live}`}
                        value={token}
                        onChange={(event) => setToken(event.target.value)}
                        rows={3}
                        placeholder="这里需要粘贴真实 JWT；灰字不是已填写内容"
                        className="validation-token"
                      />

                      {step.live === 'read-logistics' ? (
                        <>
                          <label htmlFor="live-order-id">orderId</label>
                          <input
                            id="live-order-id"
                            value={orderId}
                            onChange={(event) => setOrderId(event.target.value)}
                            placeholder="例如 order-001"
                          />
                        </>
                      ) : step.live === 'check-eligibility' ? (
                        <>
                          <label htmlFor="live-eligibility-order-id">orderId</label>
                          <input
                            id="live-eligibility-order-id"
                            value={orderId}
                            onChange={(event) => setOrderId(event.target.value)}
                            placeholder="例如 order-001"
                          />
                          <label htmlFor="live-reason-code">reasonCode</label>
                          <input
                            id="live-reason-code"
                            value={reasonCode}
                            onChange={(event) => setReasonCode(event.target.value)}
                            placeholder="例如 LOGISTICS_DELAY"
                          />
                        </>
                      ) : step.live === 'create-run' ? (
                        <>
                          <label htmlFor="live-user-request">User request</label>
                          <textarea
                            id="live-user-request"
                            value={message}
                            onChange={(event) => setMessage(event.target.value)}
                            rows={2}
                          />
                        </>
                      ) : (
                        <>
                          <label htmlFor={`run-id-${step.live}`}>runId</label>
                          <input
                            id={`run-id-${step.live}`}
                            value={runId}
                            onChange={(event) => setRunId(event.target.value)}
                            placeholder="先执行步骤 10，或填入已有 runId"
                          />
                        </>
                      )}

                      <button
                        className="live-call-button"
                        type="button"
                        onClick={() => void callLiveStep(step.live!)}
                        disabled={result.kind === 'pending'}
                      >
                        {result.kind === 'pending' && result.step === step.live
                          ? '请求中...'
                          : step.action}
                      </button>
                    </div>

                    <div className="validation-result" aria-live="polite">
                      <span className="io-label">真实响应</span>
                      {result.kind === 'idle' && <p>填写输入后，亲手点击左侧当前接口。</p>}
                      {result.kind === 'pending' && result.step === step.live && <p>Loading...</p>}
                      {result.kind !== 'idle' && result.step !== step.live && (
                        <p>当前步骤还没有调用。上一步结果和 runId 已保留。</p>
                      )}
                      {result.kind === 'error' && result.step === step.live && (
                        <p className="validation-error">
                          {result.status ? `HTTP ${result.status}: ` : ''}
                          {result.detail}
                        </p>
                      )}
                      {result.kind === 'ok' && result.step === step.live && (
                        <>
                          <p className="validation-success">HTTP {result.status} · 已从真实服务返回</p>
                          <pre>{JSON.stringify(result.body, null, 2)}</pre>
                        </>
                      )}
                    </div>
                  </div>

                  {step.note ? <div className="note-box">{step.note}</div> : null}
                </article>
              ) : openStep === step.id ? (
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
          <span>用户意图</span><b>→</b><span>FastAPI · T018</span><b>→</b>
          <span className="focus-node">Run / Checkpoint · T017</span><b>→</b><span>Tool</span><b>→</b>
          <span>CommerceClient · T016</span><b>→</b><span>Java</span><b>→</b><span>PostgreSQL</span>
        </div>
        <p>
          T024/T025 现在可从页面直连 Java 验证物流事实与售后资格；T018 提供 Agent 入口，T017 保存可恢复状态和 Trace，
          T016 连接 Java 客户端。真正的 Web → Agent → Tool → CommerceClient → Java 链路将在 T029/T030/T032 接入。
        </p>
      </section>
    </main>
  )
}
