"""Histórico de conversa em SQLite (stdlib). Uma linha por mensagem no formato da API (role/content/tool_calls...)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from . import config


class ConversationStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else config.STATE_DIR / "conversas.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c, c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
                "payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def append(self, session_id: str, message: dict) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "INSERT INTO messages(session_id, payload, created_at) VALUES (?,?,?)",
                (session_id, json.dumps(message, ensure_ascii=False), config.now().isoformat(timespec="seconds")),
            )

    def history(self, session_id: str) -> list[dict]:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT payload FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def sessions(self) -> list[dict]:
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT session_id, MIN(created_at), COUNT(*) FROM messages GROUP BY session_id ORDER BY MAX(id) DESC"
            ).fetchall()
        return [{"session_id": r[0], "inicio": r[1], "mensagens": r[2]} for r in rows]

    def export_markdown(self, session_id: str, title: str | None = None) -> str:
        lines = [f"# {title or 'Conversa ' + session_id}", ""]
        for m in self.history(session_id):
            role = m.get("role")
            if role == "user":
                lines += [f"**Cliente:** {m['content']}", ""]
            elif role == "assistant":
                for tc in m.get("tool_calls") or []:
                    fn = tc["function"]
                    lines.append(f"> 🔧 `{fn['name']}({fn['arguments']})`")
                if m.get("tool_calls"):
                    lines.append("")
                if m.get("content"):
                    lines += [f"**Bia:** {m['content']}", ""]
            elif role == "tool":
                content = m.get("content", "")
                lines += [f"> ↳ resultado: `{content[:300]}{'…' if len(content) > 300 else ''}`", ""]
        return "\n".join(lines).rstrip() + "\n"
