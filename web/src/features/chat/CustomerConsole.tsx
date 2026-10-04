/**
 * The customer-facing console: four things a customer can understand, and nothing else.
 *
 * What it deliberately does NOT show
 * ----------------------------------
 * `currentNode`, `stepCount`, `version`, `verificationStatus`, `write.status` -- all of it lives in
 * the Flow Playground, which is the internal debugger. This page is the product surface, so the only
 * vocabulary on it is a customer's: what I asked, whether it is still working, what the result is,
 * and what I need to supply next.
 *
 * That constraint is why the page can render a run at all without a debug view: everything it needs
 * arrives in one response. `POST /agent/runs` drives the graph before it answers, so the create call
 * already comes back with a terminal state or a clarification request -- there is no polling here,
 * and no spinner that lies about progress.
 *
 * Why inline styles: the playground owns App.css, and a product page quietly competing with the
 * debugger's stylesheet is how "one visual language" becomes two. Keeping this component
 * self-contained means adding it cannot move a single pixel of the page that was already verified.
 */

import { useState } from 'react'

/** The subset of the run response a customer page is allowed to depend on. */
type RunView = {
  runId: string
  status: string
  finalMessage?: string | null
  resolvedOrderId?: string | null
  errorCode?: string | null
  clarification?: {
    kind: 'INTENT_UNKNOWN' | 'ORDER_AMBIGUOUS'
    candidateOrderIds?: string[]
  } | null
}

type Turn =
  | { role: 'customer'; text: string }
  | {
      role: 'agent'
      text: string
      orders?: string[]
      needsClarification?: boolean
      /** Kept per turn on purpose: one conversation can ask twice, and the second question's
       *  candidates must not appear on the first question's card. */
      candidates?: string[]
    }

const AGENT = '/agent'

/** Status is a state, not a label: map it to words a customer would use, never print the enum. */
function headlineFor(view: RunView): string {
  if (view.status === 'WAITING_USER') {
    return '需要你补充一点信息'
  }
  if (view.status === 'WAITING_APPROVAL') {
    // Waiting on an approver is not something the customer can act on, so it must not read like a
    // request for more information -- that would send them looking for something to supply.
    return '已提交人工审核，请等待结果'
  }
  if (view.status === 'RUNNING') {
    // The create call drives the graph, so this should not happen; saying so honestly beats a
    // spinner that never resolves.
    return '还在处理中，请稍后刷新页面查看结果'
  }
  if (view.status === 'SAFE_STOP' || view.status === 'ESCALATED') {
    return '已转人工处理'
  }
  if (view.status === 'FAILED') {
    return '处理失败'
  }
  return '处理完成'
}

const card: React.CSSProperties = {
  border: '1px solid #d8dee9',
  borderRadius: 10,
  padding: '10px 12px',
  margin: '8px 0',
  maxWidth: 520,
  lineHeight: 1.5,
}

export function CustomerConsole() {
  const [token, setToken] = useState('')
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  function appendAgent(view: RunView) {
    const needsClarification = Boolean(view.clarification)
    setActiveRunId(needsClarification ? view.runId : null)
    setTurns((prev) => [
      ...prev,
      {
        role: 'agent',
        text: needsClarification
          ? view.clarification?.kind === 'ORDER_AMBIGUOUS'
            ? '你名下有好几笔订单，请告诉我是哪一笔。'
            : '我还不太确定你的诉求，能再说明一下吗？'
          : (view.finalMessage ?? headlineFor(view)),
        orders: view.resolvedOrderId ? [view.resolvedOrderId] : undefined,
        needsClarification,
        candidates: view.clarification?.candidateOrderIds ?? [],
      },
    ])
  }

  async function call(path: string, body: unknown) {
    setBusy(true)
    try {
      const response = await fetch(`${AGENT}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.trim()}` },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const friendly =
          response.status === 401
            ? '凭证无效或已过期，请重新获取。'
            : response.status === 503
              ? '服务暂时不可用，请稍后再试。'
              : '刚才那次请求没有成功，请重试。'
        setTurns((prev) => [...prev, { role: 'agent', text: friendly }])
        return
      }
      appendAgent((await response.json()) as RunView)
    } catch {
      setTurns((prev) => [...prev, { role: 'agent', text: '网络异常，请稍后再试。' }])
    } finally {
      setBusy(false)
    }
  }

  function send() {
    const text = draft.trim()
    if (!text || busy) return
    setTurns((prev) => [...prev, { role: 'customer', text }])
    setDraft('')
    // If the run is already waiting for an answer, this text IS the answer: it has to continue that
    // run rather than start a second one. Otherwise the customer's reply would silently abandon the
    // waiting run and lose everything the first walk had already established.
    if (activeRunId) {
      void call(`/runs/${activeRunId}/input`, { message: text })
    } else {
      void call('/runs', { message: text })
    }
  }

  function choose(orderId: string) {
    if (busy || !activeRunId) return
    const text = `是这一单：${orderId}`
    setTurns((prev) => [...prev, { role: 'customer', text }])
    void call(`/runs/${activeRunId}/input`, { message: text })
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: 16, fontFamily: 'system-ui' }}>
      <h1 style={{ fontSize: 20, margin: '4px 0 2px' }}>售后助手</h1>
      <p style={{ color: '#5b6472', margin: '0 0 14px', fontSize: 13 }}>
        用一句话说明你的问题，例如："我的包裹物流三天没动了，我要退款"
      </p>

      <label style={{ display: 'block', fontSize: 12, color: '#5b6472', marginBottom: 4 }}>
        访问凭证（仅保存在当前页面，不写入本地存储）
      </label>
      <input
        type="password"
        value={token}
        onChange={(event) => setToken(event.target.value)}
        placeholder="粘贴 Bearer token"
        style={{ width: '100%', padding: 8, marginBottom: 16, boxSizing: 'border-box' }}
      />

      <div>
        {turns.map((turn, index) =>
          turn.role === 'customer' ? (
            <div key={index} style={{ ...card, marginLeft: 'auto', background: '#eef4ff' }}>
              {turn.text}
            </div>
          ) : (
            <div key={index} style={{ ...card, background: '#ffffff' }}>
              <div>{turn.text}</div>
              {turn.orders?.map((orderId) => (
                <div key={orderId} style={{ fontSize: 13, color: '#5b6472', marginTop: 6 }}>
                  订单：{orderId}
                </div>
              ))}
              {turn.needsClarification && (turn.candidates?.length ?? 0) > 0 ? (
                <div style={{ marginTop: 8 }}>
                  {turn.candidates?.map((orderId) => (
                    <button
                      key={orderId}
                      onClick={() => choose(orderId)}
                      disabled={busy}
                      style={{ marginRight: 8, padding: '6px 10px' }}
                    >
                      {orderId}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ),
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') send()
          }}
          placeholder="说说你的问题…"
          style={{ flex: 1, padding: 10 }}
        />
        <button onClick={send} disabled={busy} style={{ padding: '10px 18px' }}>
          {busy ? '处理中…' : '发送'}
        </button>
      </div>
    </div>
  )
}
