# Bia — agente de atendimento da Empório da Música

Protótipo do desafio técnico de AI Engineer (Artefact): um agente de mensagens para a loja fictícia de instrumentos
**Empório da Música** (Campo Grande/MS). A persona é a **Bia**: informal, acolhedora e que só afirma o que consultou.

- **Linguagem:** Python 3.10+.
- **Modelo:** DeepSeek via **OpenRouter** (API OpenAI-compatível).
- **Interfaces:** chat web (**Vite + React**, servido pela API Python), CLI em Python e, opcionalmente, a Web UI do DeepSeek Harness (`dsh`).

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # preencha OPENROUTER_API_KEY
python scripts/check_openrouter.py   # lista modelos DeepSeek com tool calling e confere OPENROUTER_MODEL
pytest -q                       # testes do backend: não usam rede nem chave
```

**Chat web** (Python 3.10+ e Node 20+):

```bash
cd frontend && npm install && npm run build && cd ..   # gera frontend/dist
python -m emporio.web                                  # http://127.0.0.1:8000
# desenvolvimento do front: python -m emporio.web  +  (cd frontend && npm run dev)  -> http://localhost:5173 (proxy /api)
# testes do front: (cd frontend && npm test)
```

A API serve o build e expõe `POST /api/chat` e `GET /api/history`. Escuta só em 127.0.0.1 e não tem autenticação (protótipo).

**CLI** (mais simples, só Python):

```bash
python -m emporio.cli --trace   # --trace mostra as ferramentas chamadas; comandos: /novo /sessoes /trace /exportar /sair
```

**Web UI com DeepSeek Harness** (requer Node 20+):

```bash
./scripts/run_ui.sh             # gera o overlay, sobe http://127.0.0.1:3080 (a URL com token é impressa no terminal)
```

Na primeira vez, na UI: **Choose workspace** → adicione a pasta `dsh-workspace/` (criada pelo script). O agente selecionado
já é o preset "Bia — Empório da Música". A chave vem de `OPENROUTER_API_KEY`; nada é gravado em `~/.dsh` (o script usa `dsh-home/`).

**Conversas de exemplo** (rodam cenários reais contra o modelo e gravam as transcrições em `examples/`):

```bash
python scripts/generate_examples.py
```

> Os dados de exemplo terminam em mar/2026, então os prazos de devolução dependem da data. `EMPORIO_NOW=2026-02-20T10:00:00`
> fixa o "agora" (o gerador de exemplos já faz isso).

## Arquitetura

```
cliente ─► LLM (DeepSeek/OpenRouter) ──tool calls──► 7 ferramentas (Python, determinísticas)
              ▲                                          │ CSVs tratados · manual de políticas (BM25) · SQLite · JSONL
              └──────────── resultados JSON ◄────────────┘
```

A mesma lista de ferramentas (`src/emporio/tools.py`) é usada de duas formas, sem duplicar lógica:

1. **Loop em Python** (`agent.py`): function calling nativo, até 6 passos por mensagem (um passo = uma ida ao modelo).
2. **Servidor MCP stdio** (`mcp_server.py`): é como o DeepSeek Harness enxerga a loja.

| Ferramenta | Para quê |
|---|---|
| `buscar_produtos` | opções por categoria/faixa de preço/termos; só itens vendáveis por padrão |
| `obter_produto` | preço, promoção, estoque, specs; alternativas se indisponível |
| `simular_pagamento` | PIX, parcelas válidas, frete e combinação de pagamentos |
| `consultar_pedido` | status/rastreio/prazos (exige nº do pedido + e-mail ou telefone) |
| `consultar_politicas` | busca no manual, devolve a seção como fonte |
| `horario_atendimento` | aberto agora? considera sábado, domingo e feriados de MS |
| `encaminhar_atendente` | registra o caso e devolve protocolo + prazo (24 h úteis) |

## Decisões técnicas e justificativas

- **Function calling (ReAct nativo) em vez de RAG puro ou text-to-SQL.** Os dados são pequenos e estruturados; consultas
  parametrizadas são mais seguras e auditáveis que SQL gerado por LLM, e o modelo decide *quando* consultar dados vs. políticas
  (requisito do desafio). Preço, estoque, prazo e conta saem de código, não do modelo.
- **Políticas: chunking por seção + BM25 lexical**, com normalização PT-BR e pequena lista de sinônimos
  ("me arrependi" → arrependimento/devolução). O manual tem ~8 páginas com seções autocontidas; embeddings adicionariam
  dependência e não-determinismo sem ganho claro. O PDF foi convertido para `data/politicas_da_loja.md` (cada trecho citado
  carrega o número da seção). Limite conhecido: sinônimos manuais não escalam para um manual grande — aí valeria híbrido com embeddings.
- **Robustez do loop.** Cada chamada de ferramenta sempre recebe um resultado (erro genérico, sem vazar a exceção) e a chamada do
  assistente só é gravada junto com todos os resultados, então o histórico nunca fica com `tool_calls` sem resposta. Ferramentas de
  leitura pedidas no mesmo passo rodam em paralelo; `consultar_pedido` e `encaminhar_atendente` (estado/efeito colateral) forçam
  execução em série. Definições de ferramentas e prompt são idênticos em todos os passos (prefixo estável, bom para cache do provedor).
  Esses pontos foram inspirados na descrição pública do loop do DeepSeek Harness (`@deepseek-ai/dsh-agent-loop`, MIT);
  é uma reimplementação independente em Python, sem código copiado.
- **Modelo: DeepSeek via OpenRouter.** Custo baixo, bom suporte a tool calling e uma chave só para trocar de modelo (`OPENROUTER_MODEL`).
  O loop desliga o *reasoning* por padrão (`EMPORIO_REASONING=default` reativa) porque não reenvia `reasoning_details` entre chamadas
  de ferramenta. *Não consegui validar o slug exato do modelo sem a chave: use `scripts/check_openrouter.py`.*
- **Interface: chat web (React) + CLI + DeepSeek Harness opcional.** O `dsh` é um harness de agente de código; para atendimento, o overlay
  (`scripts/setup_dsh.py`) cria um preset só com persona + MCP da loja, **sem shell, arquivos ou web**, e desliga os presets padrão.
- **Histórico:** SQLite (stdlib), uma linha por mensagem no formato da API; retoma por `--session`, com janela das últimas 40 mensagens
  (sem cortar no meio de um par tool_call/tool). No harness, o histórico é o das sessões dele.
- **Segurança/privacidade:** pedidos só abrem com nº + e-mail/telefone; falha de validação devolve sempre a mesma mensagem (não revela se o
  pedido existe) e há limite de 5 falhas/10 min; o prompt trata mensagens e resultados de ferramentas como dados (não comandos).

### Tratamento dos dados (`data.py`)

| Problema encontrado | Tratamento |
|---|---|
| `active` com estoque 0 (Giannini GF-3D) | `sem_estoque`: não vendável, sugere alternativas |
| `discontinued`/`coming_soon` com estoque > 0 | nunca vendáveis, independente do estoque |
| Promoções com `is_active=0` (a maioria) | ignoradas; só `is_active=1` vale; se houver mais de uma, a maior |
| PIX (5%) × promoção | **não cumulativos** (manual 6.2): item promocional não tem preço PIX |
| `specs` em JSON-texto; `electronics` yes/no | parseados; traduzidos para sim/não |
| E-mail repetido entre clientes | detectado em `quality_issues()` (validação por pedido+contato continua segura) |
| Preços | `Decimal`, nunca `float` |

### Suposições e ambiguidades do material

- **Dois telefones no manual** (3341-4444 na ficha da empresa; 3321-4500 no WhatsApp): o prompt manda apresentar ambos com contexto
  e oferecer confirmação, em vez de escolher um.
- **E-mail** com acento na seção 1.2 do PDF (`empóriodamusica`): usei a grafia sem acento da capa.
- **Parcelamento "até 3x sem mínimo (exceto abaixo de R$ 50)":** interpretado como piso de R$ 50 por parcela.
- **Data de recebimento** não existe nos dados; uso a `estimated_delivery` de pedidos entregues e aviso que a equipe confirma a elegibilidade.
- **Manual diz "300+ instrumentos"**, o CSV tem 65: o agente só fala do que as ferramentas retornam.
- **Frete:** o manual diz "acima de R$ 500" para frete grátis; trato exatamente R$ 500,00 como pago.
- **Lojas parceiras** (manual 7.1): sem lista, o agente sugere "uma loja especializada" sem citar nomes.

## Limitações conhecidas e próximos passos

- **Não testei com um modelo real** (o ambiente de desenvolvimento não alcançava o OpenRouter). O chat React foi verificado no navegador
  (Chrome headless) contra um servidor OpenAI-compatível falso, e a Web UI do harness não foi aberta no navegador. Validei: testes unitários, o
  servidor MCP por stdio, e o harness real (perfil `headless`) contra um servidor OpenAI-compatível falso, confirmando persona, ferramentas
  expostas e o ciclo tool_call → resultado. Já o preset da Web UI foi validado só até a composição do config e a subida do servidor.
  `examples/` é gerado por `scripts/generate_examples.py` na primeira execução com chave.
- O harness é *developer preview*: o formato do overlay pode quebrar entre versões (testado com `@deepseek-ai/dsh` 0.2.1-rc.5).
  Sobraram no agente helpers de recursos MCP e `exit_plan_mode`, inofensivos mas desnecessários.
- Sem avaliação automática de qualidade das respostas (próximo passo: conjunto de cenários com checagens de tool calls e de fatos).
- Sem fechamento de venda/reserva, sem integração real com WhatsApp, `encaminhar_atendente` grava em arquivo (`var/encaminhamentos.jsonl`).
- Busca de políticas com sinônimos manuais; busca de produtos lexical (sem tolerância a erros de digitação além de plural).

## Uso de assistentes de código

O projeto foi desenvolvido com o **Claude (Anthropic)** em modo agente: ele leu o enunciado e os dados, propôs a arquitetura, escreveu o código e
os testes, e executou os testes e a validação com o harness. As decisões de produto (escolha do harness com UI, DeepSeek via OpenRouter) e a revisão
são do autor. Commits feitos sob a identidade do autor.
