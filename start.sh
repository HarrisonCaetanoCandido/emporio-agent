#!/usr/bin/env bash
# Sobe tudo com um comando: venv, dependências, .env, build do frontend e o chat em http://127.0.0.1:8000
# Uso: ./start.sh            (Linux/macOS/WSL)
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Falta '$1'. Instale e rode de novo: $2"; exit 1; }; }
need python3 "https://www.python.org/downloads/ (3.10+)"
need node "https://nodejs.org (20+)"
need npm "vem junto com o Node"

python3 - <<'EOF' || { echo "Precisa de Python 3.10 ou mais novo."; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

# 1) Python
if [ ! -d .venv ]; then
  echo "==> Criando ambiente virtual (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> Instalando dependências Python"
pip install -q -e ".[dev]"

# 2) Chave do OpenRouter
if [ ! -f .env ]; then
  cp .env.example .env
fi
if ! grep -Eq '^OPENROUTER_API_KEY=sk-or-[A-Za-z0-9_-]{10,}' .env; then
  echo
  read -r -s -p "Cole sua OPENROUTER_API_KEY (não aparece enquanto digita): " KEY
  echo
  [ -n "$KEY" ] || { echo "Sem chave não dá para continuar."; exit 1; }
  # grava sem passar a chave por argumento de comando nem por sed (evita problema com caracteres especiais)
  KEY="$KEY" python3 - <<'EOF'
import os, re, pathlib
p = pathlib.Path(".env")
txt = p.read_text()
line = "OPENROUTER_API_KEY=" + os.environ["KEY"]
txt = re.sub(r"(?m)^OPENROUTER_API_KEY=.*$", lambda _: line, txt) if re.search(r"(?m)^OPENROUTER_API_KEY=", txt) else line + "\n" + txt
p.write_text(txt)
p.chmod(0o600)
EOF
  unset KEY
fi

# 3) Confere chave e modelo (só avisa se falhar; o chat sobe mesmo assim)
echo "==> Conferindo chave e modelo no OpenRouter"
python scripts/check_openrouter.py || echo "AVISO: não consegui confirmar o modelo (veja a mensagem acima). Ajuste OPENROUTER_MODEL no .env se precisar."

# 4) Frontend
echo "==> Compilando o frontend (Vite + React)"
(cd frontend && npm install --no-audit --no-fund --silent && npm run build --silent)

# 5) Servidor
[ "${NO_RUN:-0}" = "1" ] && { echo "NO_RUN=1: tudo pronto, não vou subir o servidor."; exit 0; }
echo "==> Abra http://127.0.0.1:8000  (Ctrl+C para parar)"
exec python -m emporio.web
