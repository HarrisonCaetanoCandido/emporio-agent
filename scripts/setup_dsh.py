#!/usr/bin/env python3
"""Gera o overlay do DeepSeek Harness (dsh) para rodar a Bia na Web UI.

O que o overlay faz (ver README, seção "UI com DeepSeek Harness"):
  1. cria o preset de agente `emporio`: persona completa (prompts.SYSTEM_PROMPT) + compactação de contexto
     + servidor MCP da loja (python -m emporio.mcp_server). Sem shell, sem arquivos, sem web: o agente só
     enxerga as 7 ferramentas da loja;
  2. desliga os presets padrão do harness (standard, ptc, minimal, cordis), que são de agente de código;
  3. aponta o modelo padrão para o OpenRouter (API OpenAI-compatível), lendo a chave de OPENROUTER_API_KEY.

Uso:  python scripts/setup_dsh.py [--model SLUG] [--out dsh-home/emporio.cordis.yml]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emporio import config  # noqa: E402
from emporio.prompts import SYSTEM_PROMPT  # noqa: E402

PROVIDER_ID = "openrouter-emporio"


def q(value: str) -> str:
    """Escalar YAML seguro (JSON é YAML válido). Também protege contra '{{' virar template do harness."""
    return json.dumps(value, ensure_ascii=False)


def render(model: str, python: str, root: Path, state_dir: Path, now: str) -> str:
    if "{{" in SYSTEM_PROMPT:
        raise SystemExit("SYSTEM_PROMPT contém '{{': o harness trata isso como template estrito.")
    env = {"EMPORIO_STATE_DIR": str(state_dir)}
    if now:
        env["EMPORIO_NOW"] = now
    env_yaml = "\n".join(f"            {k}: {q(v)}" for k, v in env.items())
    return f"""\
# GERADO por scripts/setup_dsh.py — não edite à mão (rode o script de novo).
# Overlay do DeepSeek Harness: agente de atendimento da Empório da Música.

# 1) Desliga os presets de agente de código do harness.
- id: preset-standard
  disabled: true
- id: preset-ptc
  disabled: true
- id: preset-minimal
  disabled: true
- id: preset-cordis
  disabled: true

# 2) O preset da loja é o padrão.
- id: agent-preset-registry
  config:
    default: emporio

# 3) Modelo via OpenRouter (OpenAI Chat Completions). A chave vem do ambiente: OPENROUTER_API_KEY.
- id: llm-pi-ai
  config:
    providers:
      {PROVIDER_ID}:
        apiKeyEnv: OPENROUTER_API_KEY
        api: openai-completions
        baseURL: {q(config.OPENROUTER_BASE_URL)}
        models:
          - id: {q(model)}
            name: {q("DeepSeek (OpenRouter)")}
- id: agent-default-model
  config:
    provider: {PROVIDER_ID}
    model: {q(model)}

- insert:
    - id: preset-emporio
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: emporio
        name: {q("Bia — Empório da Música")}
        description: {q("Atendimento ao cliente: catálogo, pedidos e políticas da loja.")}
        order: 1
        plugins:
          - id: persona
            name: '@deepseek-ai/dsh-persona'
            config:
              prefix: {q(SYSTEM_PROMPT)}
              complete: true
              includeRuntimeContext: false
          - id: compaction
            name: cordis:group
            group: true
            isolate:
              compaction: true
            config:
              - id: compaction-basic
                name: '@deepseek-ai/dsh-compaction-basic'
          - id: emporio-store
            name: '@deepseek-ai/dsh-mcp-client'
            config:
              serverName: emporio
              transport: stdio
              command: {q(python)}
              args: ["-m", "emporio.mcp_server"]
              cwd: {q(str(root))}
              env:
{env_yaml}
"""


def main() -> None:
    config.load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=config.model_name(), help="slug do modelo no OpenRouter (padrão: OPENROUTER_MODEL)")
    ap.add_argument("--python", default=sys.executable, help="interpretador que roda o servidor MCP")
    ap.add_argument("--out", default=str(ROOT / "dsh-home" / "emporio.cordis.yml"))
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    state = (ROOT / "var").resolve()
    state.mkdir(exist_ok=True)
    out.write_text(render(args.model, args.python, ROOT, state, os.getenv("EMPORIO_NOW", "")), encoding="utf-8")
    (ROOT / "dsh-workspace").mkdir(exist_ok=True)
    print(f"overlay gerado: {out}\nmodelo: {args.model}\npython do MCP: {args.python}")


if __name__ == "__main__":
    main()
