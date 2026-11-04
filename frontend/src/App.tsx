import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  fetchHistory,
  loadSessionId,
  newSessionId,
  saveSessionId,
  sendMessage,
  type ChatMessage,
} from './api'
import { Activity } from './Activity'
import { MessageMeta } from './MessageMeta'
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
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const areaRef = useRef<HTMLTextAreaElement>(null)
  const chatRef = useRef<HTMLElement>(null)
  const atBottomRef = useRef(true)

  // Restaura o histórico da sessão salva no navegador.
  useEffect(() => {
    let cancelled = false
    fetchHistory(sessionId)
      .then((items) => {
        if (cancelled) return
        setMessages(items.map((m) => ({ id: nextId(), role: m.role, text: m.text, tools: m.tools, ts: m.ts })))
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  // Só acompanha o fim da conversa automaticamente se o usuário já estava lá; senão, mostra o botão de "ir para o fim".
  useEffect(() => {
    if (atBottomRef.current) {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    } else {
      setShowScrollBtn(true)
    }
  }, [messages, busy])

  const onChatScroll = useCallback(() => {
    const el = chatRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 96
    atBottomRef.current = atBottom
    setShowScrollBtn(!atBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    atBottomRef.current = true
    setShowScrollBtn(false)
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

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
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', text, ts: new Date().toISOString() }])
      const result = await sendMessage(sessionId, text)
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: 'assistant', text: result.reply, tools: result.tools, error: !result.ok, ts: result.ts },
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
            <svg viewBox="0 0 32 32" width="30" height="30">
              <defs>
                <linearGradient id="holo" x1="2" y1="29" x2="30" y2="3" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#1890d7" />
                  <stop offset="0.5" stopColor="#8b5cf6" />
                  <stop offset="1" stopColor="#ff0066" />
                </linearGradient>
                <radialGradient id="gloss" cx="0.5" cy="0.5" r="0.5">
                  <stop offset="0" stopColor="#ffffff" stopOpacity="0.95" />
                  <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
                </radialGradient>
              </defs>
              <path
                d="M13 24.5V8.8a1 1 0 0 1 0.78-0.98l11-2.4a1 1 0 0 1 1.22 0.98V19"
                fill="none"
                stroke="url(#holo)"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="10" cy="24.5" r="4" fill="url(#holo)" />
              <circle cx="23" cy="19" r="4" fill="url(#holo)" />
              <ellipse cx="8.4" cy="22.6" rx="1.7" ry="1" fill="url(#gloss)" transform="rotate(-25 8.4 22.6)" />
              <ellipse cx="21.4" cy="17.1" rx="1.7" ry="1" fill="url(#gloss)" transform="rotate(-25 21.4 17.1)" />
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

      <main className="chat" aria-live="polite" ref={chatRef} onScroll={onChatScroll}>
        <div className="thread">
          <div className="msg bot">
            <div className="bubble">
              <p>{GREETING}</p>
            </div>
          </div>

          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role === 'user' ? 'user' : 'bot'}`}>
              {m.role === 'assistant' && m.tools && m.tools.length > 0 && <Activity tools={m.tools} />}
              <div className={`bubble${m.error ? ' error' : ''}`}>
                <MessageText text={m.text} />
              </div>
              <MessageMeta text={m.text} ts={m.ts} />
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

      {showScrollBtn && (
        <button type="button" className="scroll-down" onClick={scrollToBottom} aria-label="Ir para o fim da conversa">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 5v14M5 12l7 7 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}

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
