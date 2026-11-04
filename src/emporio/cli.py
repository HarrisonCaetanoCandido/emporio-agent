"""CLI de conversa (fallback sem Node): python -m emporio.cli [--session ID]"""
from __future__ import annotations

import argparse
import uuid

from . import config
from .agent import EmporioAgent
from .store import ConversationStore


def main() -> None:
    config.load_env()
    ap = argparse.ArgumentParser(description="Conversa com a Bia, assistente da Empório da Música")
    ap.add_argument("--session", default=None, help="id da sessão (retoma o histórico se já existir)")
    ap.add_argument("--trace", action="store_true", help="mostra as chamadas de ferramenta")
    args = ap.parse_args()

    store = ConversationStore()
    agent = EmporioAgent(store=store)
    session = args.session or uuid.uuid4().hex[:8]
    trace = args.trace
    print(f"Sessão: {session} | modelo: {agent.model} | comandos: /novo /sessoes /trace /exportar /sair")
    while True:
        try:
            text = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/sair":
            break
        if text == "/novo":
            session = uuid.uuid4().hex[:8]
            print(f"Nova sessão: {session}")
            continue
        if text == "/sessoes":
            for s in store.sessions():
                print(f"  {s['session_id']}  {s['inicio']}  ({s['mensagens']} msgs)")
            continue
        if text == "/trace":
            trace = not trace
            print(f"trace: {'on' if trace else 'off'}")
            continue
        if text == "/exportar":
            print(store.export_markdown(session))
            continue
        try:
            reply = agent.reply(session, text)
        except Exception as exc:  # noqa: BLE001
            print(f"[erro ao falar com o modelo: {exc}]")
            continue
        if trace:
            for t in reply.tool_calls:
                print(f"  🔧 {t.name}({t.arguments})")
        print(f"\nBia: {reply.text}")


if __name__ == "__main__":
    main()
