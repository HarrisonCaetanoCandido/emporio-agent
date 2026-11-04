import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  fetchHistory,
  loadSessionId,
  newSessionId,
  saveSessionId,
  sendMessage,
  type ChatMessage,
} from './api'
import { MessageText } from './MessageText'

const GREETING =
  'Oi! Eu sou a Bia, da Empório da Música. Posso ajudar com produtos, preços, formas de pagamento, pedidos, trocas e horários da loja. Como posso te ajudar?'

const SUGGESTIONS = [
  'Violões até R$ 1.000',
  'Quanto custa o Takamine GD20?',
  'Qual o endereço da loja?',
  'Quero devolver um pedido',
]

let counter = 0
const nextId = () => `m${Date.now().toString(36)}${counter++}`

export default function App() {
  const [sessionId, setSessionId] = useState(loadSessionId)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const areaRef = useRef<HTMLTextAreaElement>(null)

  // Restaura o histórico da sessão salva no navegador.
  useEffect(() => {
    let cancelled = false
    fetchHistory(sessionId)
      .then((items) => {
        if (cancelled) return
        setMessages(items.map((m) => ({ id: nextId(), role: m.role, text: m.text, tools: m.tools })))
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  // Textarea cresce com o conteúdo (via CSSOM, compatível com a CSP sem inline style).
  useEffect(() => {
    const el = areaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [input])

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text || busy) return
      setInput('')
      setBusy(true)
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', text }])
      const result = await sendMessage(sessionId, text)
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'assistant', text: result.reply, tools: result.tools, error: !result.ok },
      ])
      setBusy(false)
      areaRef.current?.focus()
    },
    [busy, sessionId],
  )

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    }
  }

  const reset = () => {
    if (busy) return
    setMessages([])
    setSessionId(saveSessionId(newSessionId()))
  }

  const empty = messages.length === 0

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="22" height="22">
              <path d="M10 21V11l12-2v10" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="9" cy="21" r="2.4" fill="currentColor" />
              <circle cx="21" cy="19" r="2.4" fill="currentColor" />
            </svg>
          </span>
          <div className="brand-text">
            <strong>Empório da Música</strong>
            <span>Bia · atendimento virtual</span>
          </div>
        </div>
        <button type="button" className="ghost" onClick={reset} disabled={busy}>
          Nova conversa
        </button>
      </header>

      <main className="chat" aria-live="polite">
        <div className="thread">
          <div className="msg bot">
            <div className="bubble">
              <p>{GREETING}</p>
            </div>
          </div>

          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role === 'user' ? 'user' : 'bot'}`}>
              <div className={`bubble${m.error ? ' error' : ''}`}>
                <MessageText text={m.text} />
              </div>
              {m.role === 'assistant' && m.tools && m.tools.length > 0 && (
                <div className="trace">
                  <span className="dot" aria-hidden="true" />
                  Consultou: {m.tools.join(', ')}
                </div>
              )}
            </div>
          ))}

          {busy && (
            <div className="msg bot">
              <div className="bubble typing" aria-label="Bia está digitando">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}

          {empty && !busy && (
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chip" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </main>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          ref={areaRef}
          value={input}
          rows={1}
          maxLength={2000}
          placeholder="Escreva sua mensagem…"
          aria-label="Mensagem"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="send" disabled={busy || !input.trim()} aria-label="Enviar">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path d="M5 12h13M12 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </div>
  )
}
