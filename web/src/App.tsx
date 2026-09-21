import { useState } from 'react'
import './App.css'

/**
 * T018 end-to-end validation page: 5173 → Vite proxy → FastAPI → Java → PostgreSQL.
 *
 * Deliberately not a product UI. It exists to prove one specific thing that no unit test can: that a
 * *browser* can drive the whole chain, across three processes and two languages. T034 builds the real
 * console; building it here would mean debugging UI and plumbing at the same time.
 *
 * What it demonstrates end to end:
 *   1. the Vite dev proxy forwards `/agent/...` to FastAPI without any CORS configuration;
 *   2. FastAPI verifies the JWT locally, then asks Java `GET /api/v1/me` who it belongs to;
 *   3. the run is created with that authoritative principal and persisted to `agent.agent_runs`;
 *   4. reading it back goes through the owner-scoped query, so a second user's token cannot see it.
 *
 * The token is held in component state only -- never localStorage. Persisting a credential across
 * reloads is how a dev token ends up in a screenshot, and this service's whole design is about not
 * keeping credentials around.
 */

type RunView = {
  runId: string
  status: string
  intent: string | null
  resolvedOrderId: string | null
  currentNode: string | null
  stepCount: number
  version: number
  errorCode: string | null
}

type CallResult =
  | { kind: 'idle' }
  | { kind: 'pending' }
  | { kind: 'ok'; status: number; body: unknown }
  | { kind: 'error'; status: number | null; detail: string }

const API = '/agent/runs'

function App() {
  const [token, setToken] = useState('')
  const [message, setMessage] = useState('My shipment has not moved for days. Can I get a refund?')
  const [runId, setRunId] = useState('')
  const [result, setResult] = useState<CallResult>({ kind: 'idle' })

  async function call(path: string, init: RequestInit): Promise<void> {
    setResult({ kind: 'pending' })
    try {
      const response = await fetch(path, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          // The credential is forwarded, never asserted: this header is the only place identity
          // enters the chain. There is no user id in any request body, by design.
          Authorization: `Bearer ${token.trim()}`,
          ...(init.headers ?? {}),
        },
      })
      const text = await response.text()
      let body: unknown = text
      try {
        body = JSON.parse(text)
      } catch {
        // Non-JSON body: keep the raw text so a proxy error is visible instead of "undefined".
      }
      setResult(
        response.ok
          ? { kind: 'ok', status: response.status, body }
          : { kind: 'error', status: response.status, detail: text },
      )
      if (response.ok && body && typeof body === 'object' && 'runId' in body) {
        setRunId(String((body as RunView).runId))
      }
    } catch (error) {
      // A network-level failure here usually means FastAPI is not running; saying so beats a
      // silent "failed to fetch".
      setResult({
        kind: 'error',
        status: null,
        detail: `${String(error)} — is the Agent API running on :8000?`,
      })
    }
  }

  const created = result.kind === 'ok' ? (result.body as RunView) : null

  return (
    <main style={{ maxWidth: 860, margin: '0 auto', padding: 24, textAlign: 'left' }}>
      <h1>T018 chain check</h1>
      <p>
        Browser (:5173) → Vite proxy → FastAPI (:8000) → Java (:8080) → PostgreSQL
      </p>

      <ol style={{ lineHeight: 1.8 }}>
        <li>
          Mint a token in <code>agent-service/</code>:{' '}
          <code>uv run python scripts/mint_dev_token.py customer-001</code>
        </li>
        <li>Paste it below and create a run.</li>
        <li>
          Then open <code>GET /agent/runs/&lt;runId&gt;</code> to prove the owner-scoped read works.
        </li>
      </ol>

      <section style={{ marginBottom: 16 }}>
        <label htmlFor="token">Bearer token</label>
        <textarea
          id="token"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          rows={4}
          style={{ width: '100%', fontFamily: 'monospace' }}
          placeholder="eyJhbGciOiJIUzI1NiJ9..."
        />
      </section>

      <section style={{ marginBottom: 16 }}>
        <label htmlFor="message">User request (untrusted natural language)</label>
        <textarea
          id="message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={3}
          style={{ width: '100%' }}
        />
      </section>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          disabled={!token.trim() || !message.trim()}
          onClick={() =>
            void call(API, { method: 'POST', body: JSON.stringify({ message }) })
          }
        >
          POST /agent/runs
        </button>
        <button
          type="button"
          disabled={!token.trim() || !runId}
          onClick={() => void call(`${API}/${runId}`, { method: 'GET' })}
        >
          GET /agent/runs/{runId ? `${runId.slice(0, 8)}…` : '<runId>'}
        </button>
        <button
          type="button"
          disabled={!token.trim() || !runId}
          onClick={() => void call(`${API}/${runId}/events`, { method: 'GET' })}
        >
          GET /events
        </button>
      </div>

      <section style={{ marginTop: 24 }}>
        <strong>Result</strong>
        {result.kind === 'pending' && <p>…</p>}
        {result.kind === 'idle' && <p>No call made yet.</p>}
        {result.kind === 'error' && (
          <p style={{ color: '#b00' }}>
            HTTP {result.status ?? 'network error'}: <code>{result.detail}</code>
          </p>
        )}
        {created && (
          <p style={{ color: '#060' }}>
            HTTP {result.kind === 'ok' ? result.status : ''} — runId={created.runId} status=
            {created.status} stepCount={created.stepCount} version={created.version}
          </p>
        )}
        {result.kind === 'ok' && (
          <pre style={{ background: '#f4f4f4', padding: 12, overflowX: 'auto' }}>
            {JSON.stringify(result.body, null, 2)}
          </pre>
        )}
      </section>
    </main>
  )
}

export default App
