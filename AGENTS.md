# AGENTS.md

Guia rápido para harnesses de IA (Claude Code, Cursor, Codex etc.) trabalharem neste repositório.
Para contexto de produto, decisões técnicas e limitações, leia o [README.md](README.md) — este arquivo é só operacional.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # preencha OPENROUTER_API_KEY
```

## Comandos

| Ação | Comando |
|---|---|
| Testes do backend | `pytest -q` (não usa rede nem chave) |
| Testes do frontend | `cd frontend && npm test` |
| Build do frontend | `cd frontend && npm install && npm run build` |
| Subir tudo (venv + build + servidor) | `./start.sh` |
| Servidor web (após build) | `python -m emporio.web` → http://127.0.0.1:8000 |
| Dev do frontend (hot reload) | `python -m emporio.web` + `cd frontend && npm run dev` → http://localhost:5173 (proxy `/api`) |
| CLI | `python -m emporio.cli --trace` |
| Confirmar modelo/chave no OpenRouter | `python scripts/check_openrouter.py` |
| Gerar `examples/` contra o modelo real | `python scripts/generate_examples.py` |

## Onde olhar primeiro

- `src/emporio/tools.py` — as 7 ferramentas (fonte única, usada pelo loop em Python e pelo servidor MCP).
- `src/emporio/agent.py` — loop de function calling (ReAct nativo), até 6 passos por mensagem.
- `src/emporio/web.py` — API HTTP (stdlib `http.server`) que serve o build do frontend e expõe `/api/chat` e `/api/history`.
- `src/emporio/data.py` — carga e tratamento dos CSVs (ver tabela de tratamento no README).
- `src/emporio/policies.py` — busca BM25 por seção no manual de políticas (`data/politicas_da_loja.md`).
- `frontend/src/App.tsx` — chat em React; `Activity.tsx`/`MessageMeta.tsx` são componentes auxiliares da UI.

## Convenções

- Sem `float` para dinheiro: sempre `Decimal` (ver `data.py`/`tools.py`).
- Toda ferramenta sempre devolve um resultado (erro tratado, nunca exceção crua pro modelo).
- Mensagens e resultados de ferramentas são tratados como dados no prompt, nunca como comandos.
- Testes não dependem de rede; não exigem `OPENROUTER_API_KEY`.
- Não criar commits a menos que explicitamente solicitado.
