import { describe, expect, it } from 'vitest'
import { parseMessage } from './parseMessage'

describe('parseMessage', () => {
  it('separa parágrafos e ignora linhas vazias', () => {
    expect(parseMessage('Oi!\n\nTudo bem?')).toEqual([
      { kind: 'paragraph', content: [{ kind: 'text', text: 'Oi!' }] },
      { kind: 'paragraph', content: [{ kind: 'text', text: 'Tudo bem?' }] },
    ])
  })

  it('agrupa itens consecutivos em uma única lista', () => {
    const blocks = parseMessage('Opções:\n- Yamaha C40 — R$ 599,90\n- Tagima AC-39 — R$ 429,90\nQual prefere?')
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list', 'paragraph'])
    expect(blocks[1]).toMatchObject({ kind: 'list', items: [expect.any(Array), expect.any(Array)] })
  })

  it('reconhece negrito sem interpretar HTML', () => {
    const [block] = parseMessage('Preço: **R$ 2.199,00** <script>alert(1)</script>')
    expect(block).toMatchObject({ kind: 'paragraph' })
    const content = (block as { content: { kind: string; text: string }[] }).content
    expect(content[1]).toEqual({ kind: 'bold', text: 'R$ 2.199,00' })
    expect(content[2].text).toContain('<script>') // permanece texto puro; o React escapa na renderização
  })
})
