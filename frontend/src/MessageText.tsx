import { parseMessage, type Inline } from './parseMessage'

function Inlines({ content }: { content: Inline[] }) {
  return (
    <>
      {content.map((part, i) =>
        part.kind === 'bold' ? <strong key={i}>{part.text}</strong> : <span key={i}>{part.text}</span>,
      )}
    </>
  )
}

export function MessageText({ text }: { text: string }) {
  return (
    <>
      {parseMessage(text).map((block, i) =>
        block.kind === 'list' ? (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>
                <Inlines content={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Inlines content={block.content} />
          </p>
        ),
      )}
    </>
  )
}
