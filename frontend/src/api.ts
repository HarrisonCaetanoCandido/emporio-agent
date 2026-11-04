export type Role = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: Role
  text: string
  tools?: string[]
  error?: boolean
}

interface HistoryItem {
  role: Role
  text: string
  tools?: string[]
}

const SESSION_KEY = 'emporio_session'

export function newSessionId(): string {
  const bytes = new Uint8Array(9)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function loadSessionId(): string {
  try {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) return saved
  } catch {
    /* storage indisponível: segue com id em memória */
  }
  return saveSessionId(newSessionId())
}

export function saveSessionId(id: string): string {
  try {
    localStorage.setItem(SESSION_KEY, id)
  } catch {
    /* ignora */
  }
  return id
}

export async function fetchHistory(sessionId: string): Promise<HistoryItem[]> {
  const res = await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`)
  if (!res.ok) return []
  const data = (await res.json()) as { messages: HistoryItem[] }
  return data.messages
}

export interface ChatResult {
  ok: boolean
  reply: string
  tools: string[]
}

export async function sendMessage(sessionId: string, message: string): Promise<ChatResult> {
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    })
    const data = (await res.json().catch(() => ({}))) as { reply?: string; tools?: string[] }
    if (res.ok) return { ok: true, reply: data.reply ?? '', tools: data.tools ?? [] }
    return {
      ok: false,
      reply: data.reply ?? 'Não consegui responder agora. Tente de novo em instantes.',
      tools: [],
    }
  } catch {
    return {
      ok: false,
      reply: 'Sem conexão com o servidor. Verifique se ele está rodando e tente de novo.',
      tools: [],
    }
  }
}
