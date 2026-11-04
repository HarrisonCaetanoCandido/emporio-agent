#!/usr/bin/env python3
"""Lista modelos DeepSeek do OpenRouter que suportam tool calling, e testa a chave.

Uso:  python scripts/check_openrouter.py [filtro]      (padrão: deepseek)
Requer OPENROUTER_API_KEY no ambiente ou no .env. Use o slug escolhido em OPENROUTER_MODEL.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emporio import config  # noqa: E402


def main() -> None:
    config.load_env()
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Defina OPENROUTER_API_KEY (veja .env.example).")
    needle = (sys.argv[1] if len(sys.argv) > 1 else "deepseek").lower()
    req = urllib.request.Request(f"{config.OPENROUTER_BASE_URL}/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        models = json.load(resp)["data"]
    rows = []
    for m in models:
        if needle not in m["id"].lower():
            continue
        tools = "tools" in (m.get("supported_parameters") or [])
        price = m.get("pricing", {})
        rows.append((m["id"], tools, m.get("context_length"), price.get("prompt"), price.get("completion")))
    rows.sort()
    print(f"{'modelo':55} tools  contexto  $/token (in/out)")
    for mid, tools, ctx, pin, pout in rows:
        print(f"{mid:55} {'sim' if tools else 'NÃO':5}  {ctx or '-':>8}  {pin}/{pout}")
    current = config.model_name()
    ids = {r[0]: r[1] for r in rows}
    print(f"\nmodelo configurado: {current} ->", "ok" if ids.get(current) else "NÃO encontrado/sem tools nesta lista (confira o slug)")


if __name__ == "__main__":
    main()
