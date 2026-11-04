#!/usr/bin/env bash
# Sobe a Web UI do DeepSeek Harness com a Bia (http://127.0.0.1:3080).
# Requisitos: Node 20+ e o venv do projeto ativo (python com `pip install -e .`).
# A chave do OpenRouter vem de OPENROUTER_API_KEY (exportada ou em .env).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${OPENROUTER_API_KEY:?Defina OPENROUTER_API_KEY (veja .env.example)}"

python scripts/setup_dsh.py "$@"

# Harness isolado do ~/.dsh do usuário; workspace vazio (o agente não tem ferramentas de arquivo).
export DSH_HOME="$PWD/dsh-home"
cd dsh-workspace
exec npx -y @deepseek-ai/dsh --profile web --patch "$DSH_HOME/emporio.cordis.yml"
