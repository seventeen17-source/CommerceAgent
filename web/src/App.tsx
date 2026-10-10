import { useState } from 'react'
import './App.css'
import { CustomerConsole } from './features/chat/CustomerConsole'
import { ApprovalCenter } from './features/approval/ApprovalCenter'
import { T016FlowPlayground } from './features/validation/T016FlowPlayground'

/**
 * Two surfaces, two audiences.
 *
 * The Flow Playground is the internal debugger (every step, raw responses, fault injection); the
 * customer console is the product surface (four things a customer understands). They are kept as a
 * switch rather than a router because neither has a URL worth sharing, and the playground stays the
 * default so nothing about the existing verification flow changes.
 */
type View = 'playground' | 'console' | 'approval'

const tab = (active: boolean): React.CSSProperties => ({
  padding: '6px 12px',
  borderRadius: 6,
  border: '1px solid #d8dee9',
  background: active ? '#1f6feb' : '#ffffff',
  color: active ? '#ffffff' : '#24292f',
  cursor: 'pointer',
})

function App() {
  const [view, setView] = useState<View>('playground')

  return (
    <div>
      <nav style={{ display: 'flex', gap: 8, padding: '8px 12px', borderBottom: '1px solid #d8dee9' }}>
        <button style={tab(view === 'playground')} onClick={() => setView('playground')}>
          Flow Playground（内部调试）
        </button>
        <button style={tab(view === 'console')} onClick={() => setView('console')}>
          售后助手（客户界面）
        </button>
        <button style={tab(view === 'approval')} onClick={() => setView('approval')}>
          Approval Center（审批员）
        </button>
      </nav>
      {view === 'playground' ? (
        <T016FlowPlayground />
      ) : view === 'console' ? (
        <CustomerConsole />
      ) : (
        <ApprovalCenter />
      )}
    </div>
  )
}

export default App
