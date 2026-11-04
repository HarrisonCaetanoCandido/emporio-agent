"""Configuração central: caminhos, fuso e relógio (que pode ser fixado para demos/testes)."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("EMPORIO_DATA_DIR", ROOT / "data"))
STATE_DIR = Path(os.getenv("EMPORIO_STATE_DIR", ROOT / "var"))  # histórico (SQLite) e encaminhamentos
TZ = ZoneInfo("America/Campo_Grande")

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_MODEL = "~deepseek/deepseek-v4-flash-latest"


def model_name() -> str:
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)


def now() -> datetime:
    """'Agora' na loja. Se EMPORIO_NOW (ISO 8601) estiver definido, ele vence o relógio real."""
    forced = os.getenv("EMPORIO_NOW", "").strip()
    if forced:
        dt = datetime.fromisoformat(forced)
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
    return datetime.now(TZ)


def load_env() -> None:
    """Carrega .env (KEY=VALUE) da raiz do projeto e do diretório atual, sem sobrescrever o ambiente."""
    for base in (ROOT, Path.cwd()):
        env_file = base / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
