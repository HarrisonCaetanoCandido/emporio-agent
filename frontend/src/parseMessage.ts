// Parser mínimo e seguro das respostas da Bia: parágrafos, listas com "- " e **negrito**.
// Devolve uma estrutura (não HTML): o React cria os nós, então nada do modelo vira markup.

export type Inline = { kind: 'text' | 'bold'; text: string }
export type Block =
  | { kind: 'paragraph'; content: Inline[] }
  | { kind: 'list'; items: Inline[][] }

export function parseInline(text: string): Inline[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((part) => part !== '')
    .map((part): Inline =>
      part.length > 4 && part.startsWith('**') && part.endsWith('**')
        ? { kind: 'bold', text: part.slice(2, -2) }
        : { kind: 'text', text: part },
    )
}

export function parseMessage(text: string): Block[] {
  const blocks: Block[] = []
  let list: Inline[][] | null = null
  for (const line of text.split('\n')) {
    const item = line.match(/^\s*[-•*]\s+(.*)$/)
    if (item) {
      if (!list) {
        list = []
        blocks.push({ kind: 'list', items: list })
      }
      list.push(parseInline(item[1]))
    } else {
      list = null
      if (line.trim()) blocks.push({ kind: 'paragraph', content: parseInline(line) })
    }
  }
  return blocks
}
