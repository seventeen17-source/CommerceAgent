/**
 * T055: Approver-only presentation of Java's authoritative approval records.
 * The page owns no approval state machine and invents no evidence: every decision is POSTed to Java,
 * and every displayed result comes from a fresh Java response. Tokens live in component memory only.
 */
import { useState } from 'react'

export type ApprovalRecord = {
  approvalRequestId: string
  runId: string
  orderId: string
  actionType: string
  amount: number | null
  riskReason: string
  status: string
  decidedBy: string | null
  decidedAt: string | null
  requestedAt: string
  expiresAt: string
}

type Decision = 'APPROVE' | 'DENY'

export function approvalError(status: number): string {
  if (status === 401) return '审批凭证无效或已过期，请重新生成 APPROVER Token。'
  if (status === 403) return '当前身份没有审批权限，请使用 APPROVER 身份。'
  if (status === 404) return '审批记录不存在或不可访问。'
  if (status === 409) return '审批状态已变化或请求冲突，请刷新列表核对权威状态。'
  if (status >= 500) return 'Java 审批服务暂时不可用，请稍后重查状态。'
  return '请求未成功，请核对凭证与审批状态。'
}

const panel: React.CSSProperties = {
  border: '1px solid #d8dee9',
  borderRadius: 10,
  padding: 18,
  background: '#ffffff',
}
const small: React.CSSProperties = { fontSize: 13, color: '#5b6472', overflowWrap: 'anywhere' }

function formatAmount(amount: number | null) {
  return amount === null ? '不涉及退款金额' : amount.toFixed(2)
}
function formatTime(timestamp: string | null) {
  return timestamp ? new Date(timestamp).toLocaleString('zh-CN') : '—'
}

export function ApprovalCenter() {
  const [token, setToken] = useState('')
  const [records, setRecords] = useState<ApprovalRecord[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [deciding, setDeciding] = useState(false)
  const [message, setMessage] = useState('')
  const [confirm, setConfirm] = useState<Decision | null>(null)
  const [requiresRefresh, setRequiresRefresh] = useState(false)
  const selected = records.find((record) => record.approvalRequestId === selectedId) ?? null

  async function readPending() {
    if (!token.trim() || loading || deciding) return
    setLoading(true)
    setMessage('')
    setConfirm(null)
    setRequiresRefresh(false)
    try {
      // Java controls the APPROVER role and which records may be listed.
      const response = await fetch('/commerce/approvals?status=PENDING', {
        headers: { Authorization: `Bearer ${token.trim()}` },
      })
      if (!response.ok) {
        setRecords([])
        setSelectedId(null)
        setMessage(approvalError(response.status))
        return
      }
      const items = (await response.json()) as ApprovalRecord[]
      setRecords(items)
      setSelectedId((previous) =>
        items.some((item) => item.approvalRequestId === previous)
          ? previous
          : (items[0]?.approvalRequestId ?? null),
      )
      setMessage(items.length ? '' : '当前没有待审批申请。')
    } catch {
      setMessage('网络请求未能确认结果，请检查 Java 服务。')
    } finally {
      setLoading(false)
    }
  }

  async function decide(decision: Decision) {
    if (!selected || selected.status !== 'PENDING' || !token.trim() || deciding || requiresRefresh) return
    setConfirm(null)
    setDeciding(true)
    setMessage('')
    try {
      const response = await fetch(
        `/commerce/approvals/${encodeURIComponent(selected.approvalRequestId)}/decision`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token.trim()}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ decision }),
        },
      )
      if (!response.ok) {
        setRequiresRefresh(true)
        setMessage(approvalError(response.status))
        return
      }
      const updated = (await response.json()) as ApprovalRecord
      // Only Java's response may establish the decision. Do not optimistically flip status.
      setRecords((previous) =>
        previous.map((record) =>
          record.approvalRequestId === updated.approvalRequestId ? updated : record,
        ),
      )
      setMessage(`Java 已确认：${updated.status}；请刷新待审批列表。`)
    } catch {
      // Timeout after commit is unknown: never blindly repeat an approval decision.
      setRequiresRefresh(true)
      setMessage('审批请求的结果未知。请先刷新列表核对 Java 状态，不要直接重复提交。')
    } finally {
      setDeciding(false)
    }
  }

  return (
    <main style={{ textAlign: 'left', padding: '24px 28px', width: '100%', boxSizing: 'border-box' }}>
      <h1 style={{ fontSize: 26, margin: '0 0 8px' }}>Approval Center · 人工审批中心</h1>
      <p style={{ ...small, marginBottom: 18 }}>
        仅供 APPROVER 使用。所有申请、权限和决策都以 Java 业务服务为准。
      </p>
      <section style={{ ...panel, display: 'grid', gap: 9, marginBottom: 20 }}>
        <label htmlFor="approval-token" style={small}>审批员 Token（仅在页面内存中使用）</label>
        <input
          id="approval-token"
          type="password"
          value={token}
          onChange={(event) => {
            setToken(event.target.value)
            setRecords([])
            setSelectedId(null)
            setConfirm(null)
            setMessage('')
            setRequiresRefresh(false)
          }}
          placeholder="粘贴 approver-001 的 Bearer Token"
          autoComplete="off"
          style={{ padding: 10, width: '100%', boxSizing: 'border-box' }}
        />
        <div>
          <button onClick={() => void readPending()} disabled={!token.trim() || loading || deciding}>
            {loading ? '读取中…' : '刷新待审批申请'}
          </button>
        </div>
      </section>
      {message ? <p role="status" style={{ ...small, marginBottom: 18 }}>{message}</p> : null}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(0, 1.7fr)', gap: 16 }}>
        <section style={panel} aria-label="待审批列表">
          <h2 style={{ fontSize: 17, marginTop: 0 }}>待审批列表 ({records.filter((r) => r.status === 'PENDING').length})</h2>
          {records.length === 0 ? <p style={small}>读取后显示 Java 返回的待审批记录。</p> : null}
          {records.map((record) => (
            <button
              key={record.approvalRequestId}
              onClick={() => { setSelectedId(record.approvalRequestId); setConfirm(null) }}
              aria-pressed={selectedId === record.approvalRequestId}
              style={{
                display: 'block', width: '100%', textAlign: 'left', marginBottom: 8,
                borderColor: selectedId === record.approvalRequestId ? '#35607d' : '#d8dee9',
                background: selectedId === record.approvalRequestId ? '#eef5f8' : '#fff',
                overflowWrap: 'anywhere',
              }}
            >
              <strong>{record.orderId}</strong> · {record.status}
              <div style={small}>{record.actionType} · {formatAmount(record.amount)}</div>
            </button>
          ))}
        </section>
        <section style={panel} aria-label="审批详情">
          {!selected ? (
            <p style={small}>选择一笔 Java 审批申请，查看完整授权绑定信息。</p>
          ) : (
            <>
              <h2 style={{ fontSize: 17, marginTop: 0 }}>审批详情</h2>
              <dl style={{ display: 'grid', gridTemplateColumns: '130px minmax(0,1fr)', gap: '10px 12px', overflowWrap: 'anywhere', fontSize: 14 }}>
                <dt>订单</dt><dd style={{ margin: 0 }}>{selected.orderId}</dd>
                <dt>审批动作</dt><dd style={{ margin: 0 }}>{selected.actionType}</dd>
                <dt>金额</dt><dd style={{ margin: 0 }}>{formatAmount(selected.amount)}</dd>
                <dt>风险原因</dt><dd style={{ margin: 0 }}>{selected.riskReason}</dd>
                <dt>证据</dt><dd style={{ margin: 0 }}>当前 Approval API 未提供独立证据明细；请核对权威订单及物流记录，不要仅据此页面推断。</dd>
                <dt>状态</dt><dd style={{ margin: 0 }}>{selected.status}</dd>
                <dt>审批 ID</dt><dd style={{ margin: 0 }}>{selected.approvalRequestId}</dd>
                <dt>Run ID</dt><dd style={{ margin: 0 }}>{selected.runId}</dd>
                <dt>申请时间</dt><dd style={{ margin: 0 }}>{formatTime(selected.requestedAt)}</dd>
                <dt>过期时间</dt><dd style={{ margin: 0 }}>{formatTime(selected.expiresAt)}</dd>
                {selected.decidedBy ? <><dt>审批人</dt><dd style={{ margin: 0 }}>{selected.decidedBy}</dd></> : null}
              </dl>
              {selected.status === 'PENDING' && !requiresRefresh ? (
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
                  <button disabled={deciding || loading} onClick={() => setConfirm('APPROVE')}>Approve · 批准</button>
                  <button disabled={deciding || loading} onClick={() => setConfirm('DENY')}>Deny · 拒绝</button>
                </div>
              ) : null}
              {confirm && !requiresRefresh ? (
                <div role="group" aria-label="确认审批决定" style={{ border: '1px solid #b99e73', borderRadius: 8, padding: 12, marginTop: 14 }}>
                  <p style={{ ...small, marginBottom: 10 }}>
                    确认对订单 {selected.orderId} 的 {selected.actionType}（{formatAmount(selected.amount)}）执行 {confirm}？该操作会提交至 Java 审批服务。
                  </p>
                  <button disabled={deciding} onClick={() => void decide(confirm)}>
                    {deciding ? '提交中…' : `确认 ${confirm}`}
                  </button>
                  <button disabled={deciding} onClick={() => setConfirm(null)} style={{ marginLeft: 8 }}>取消</button>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </main>
  )
}
