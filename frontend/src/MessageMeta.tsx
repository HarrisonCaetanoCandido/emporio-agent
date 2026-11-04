import { useState } from 'react'

function formatTime(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(d)
}

/** Horário da mensagem + botão de copiar (com confirmação visual breve). */
export function MessageMeta({ text, ts }: { text: string; ts?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard indisponível (ex.: contexto não seguro): ignora */
    }
  }

  return (
    <div className="msg-meta">
      <button type="button" className="copy-btn" onClick={() => void copy()} aria-label={copied ? 'Copiado' : 'Copiar mensagem'}>
        {copied ? (
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path d="M5 12l5 5 9-10" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <rect x="8" y="8" width="12" height="12" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
        {copied ? 'Copiado' : 'Copiar'}
      </button>
      {ts && <time dateTime={ts}>{formatTime(ts)}</time>}
    </div>
  )
}
