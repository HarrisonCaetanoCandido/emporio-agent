import { useId, useState } from 'react'
import type { ToolActivity } from './api'

const MAX_PREVIEW = 160

/** Reduz um JSON (args ou resultado) a uma linha curta, sem chaves/aspas excessivas. */
function preview(json: string): string {
  let text = json
  try {
    const parsed = JSON.parse(json) as unknown
    if (parsed && typeof parsed === 'object') {
      text = Object.entries(parsed as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
        .join(', ')
    }
  } catch {
    /* não era JSON: usa o texto original */
  }
  text = text.replace(/\s+/g, ' ').trim()
  return text.length > MAX_PREVIEW ? `${text.slice(0, MAX_PREVIEW)}…` : text
}

/** Atividade da Bia num turno: colapsada por padrão, abre pra mostrar cada ferramenta chamada. */
export function Activity({ tools }: { tools: ToolActivity[] }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  if (tools.length === 0) return null

  const labels = [...new Set(tools.map((t) => t.label))]
  const summary = tools.length === 1 ? `Consultou ${labels[0]}` : `Consultou ${tools.length} fontes (${labels.join(', ')})`

  return (
    <div className="activity">
      <button
        type="button"
        className="activity-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <svg
          className={`chevron${open ? ' open' : ''}`}
          viewBox="0 0 24 24"
          width="12"
          height="12"
          aria-hidden="true"
        >
          <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="dot" aria-hidden="true" />
        {summary}
      </button>
      {open && (
        <div id={panelId} className="activity-panel">
          {tools.map((t, i) => (
            <div className="activity-item" key={`${t.name}-${i}`}>
              <code className="activity-call">
                {t.name}({preview(t.arguments)})
              </code>
              {t.result && <div className="activity-result">⎿ {preview(t.result)}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
