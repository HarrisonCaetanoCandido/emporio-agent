"""Chat web simples (stdlib): python -m emporio.web [--port 8000]

Rotas:
  GET  /                    chat (build do Vite/React em frontend/dist: `cd frontend && npm run build`)
  GET  /assets/<arquivo>    js/css gerados pelo build
  GET  /api/history?session_id=...   mensagens da sessão (texto) + ferramentas consultadas
  POST /api/chat            {"session_id": "...", "message": "..."} -> {"reply": "...", "tools": [...]}

Sem dependências extras. Escuta só em 127.0.0.1 por padrão (protótipo, sem autenticação).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config
from .agent import FALLBACK_TEXT, EmporioAgent

log = logging.getLogger("emporio.web")

DIST = config.ROOT / "frontend" / "dist"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json", ".ico": "image/x-icon"}
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
MAX_MESSAGE = 2000
MAX_BODY = 16_384

TOOL_LABELS = {
    "buscar_produtos": "catálogo",
    "obter_produto": "catálogo",
    "simular_pagamento": "simulação de pagamento",
    "consultar_pedido": "pedidos",
    "consultar_politicas": "políticas da loja",
    "horario_atendimento": "horário de atendimento",
    "encaminhar_atendente": "atendente humano",
}


def _labels(tool_names: list[str]) -> list[str]:
    seen: list[str] = []
    for n in tool_names:
        label = TOOL_LABELS.get(n, n)
        if label not in seen:
            seen.append(label)
    return seen


def history_for_ui(messages: list[dict]) -> list[dict]:
    """Só texto visível ao cliente; as ferramentas usadas viram rótulos na resposta seguinte."""
    out: list[dict] = []
    pending: list[str] = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            pending = []
            out.append({"role": "user", "text": m.get("content") or ""})
        elif role == "assistant":
            pending += [tc["function"]["name"] for tc in m.get("tool_calls") or []]
            if m.get("content") and not m.get("tool_calls"):
                out.append({"role": "assistant", "text": m["content"], "tools": _labels(pending)})
                pending = []
    return out


def make_handler(agent: EmporioAgent, static_dir: Path | None = None):
    root = Path(static_dir or DIST)
    locks: dict[str, threading.Lock] = {}
    locks_guard = threading.Lock()

    def lock_for(session_id: str) -> threading.Lock:
        with locks_guard:
            return locks.setdefault(session_id, threading.Lock())

    class Handler(BaseHTTPRequestHandler):
        server_version = "EmporioChat/0.1"

        def log_message(self, fmt, *args):  # silencia o log padrão (evita vazar texto de clientes no terminal)
            pass

        # -- helpers ------------------------------------------------------------------------
        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        # -- rotas --------------------------------------------------------------------------
        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._serve("index.html")
            if url.path == "/api/history":
                sid = (parse_qs(url.query).get("session_id") or [""])[0]
                if not SESSION_RE.match(sid):
                    return self._json(400, {"error": "session_id inválido"})
                return self._json(200, {"messages": history_for_ui(agent.store.history(sid))})
            if url.path.startswith("/api/"):
                return self._json(404, {"error": "não encontrado"})
            self._serve(unquote(url.path).lstrip("/"))

        def _serve(self, name: str) -> None:
            if name == "index.html" and not (root / "index.html").is_file():
                msg = "Frontend não compilado. Rode: cd frontend && npm install && npm run build".encode()
                return self._send(503, msg, "text/plain; charset=utf-8")
            path = (root / name).resolve()
            if root.resolve() not in path.parents or not path.is_file():  # bloqueia ../
                return self._json(404, {"error": "não encontrado"})
            self._send(200, path.read_bytes(), CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

        def do_POST(self):
            if urlparse(self.path).path != "/api/chat":
                return self._json(404, {"error": "não encontrado"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size <= 0 or size > MAX_BODY:
                    return self._json(413 if size > MAX_BODY else 400, {"error": "corpo inválido"})
                data = json.loads(self.rfile.read(size))
                sid, text = str(data.get("session_id", "")), str(data.get("message", "")).strip()
            except (ValueError, TypeError):
                return self._json(400, {"error": "JSON inválido"})
            if not SESSION_RE.match(sid):
                return self._json(400, {"error": "session_id inválido"})
            if not text:
                return self._json(400, {"error": "mensagem vazia"})
            text = text[:MAX_MESSAGE]
            try:
                with lock_for(sid):  # uma mensagem por vez por conversa (mantém a ordem do histórico)
                    reply = agent.reply(sid, text)
            except Exception:  # noqa: BLE001 - não vaza stack/chave para o navegador
                log.exception("falha ao responder")
                return self._json(502, {"error": "model_error", "reply": FALLBACK_TEXT})
            self._json(200, {"reply": reply.text, "tools": _labels([t.name for t in reply.tool_calls])})

    return Handler


def create_server(
    agent: EmporioAgent, host: str = "127.0.0.1", port: int = 8000, static_dir: Path | None = None
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(agent, static_dir))


def main() -> None:
    config.load_env()
    ap = argparse.ArgumentParser(description="Chat web da Bia (Empório da Música)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    agent = EmporioAgent()
    server = create_server(agent, args.host, args.port)
    print(f"Bia no ar: http://{args.host}:{args.port}  (modelo: {agent.model}) — Ctrl+C para sair")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
