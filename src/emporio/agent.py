"""Loop de agente com function calling sobre a API OpenAI-compatible do OpenRouter.

É um loop ReAct nativo: o modelo escolhe ferramentas (tool_calls), executamos, devolvemos o resultado
e repetimos até ele responder em texto (limite de `max_steps` para evitar laços).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from . import config
from .prompts import SYSTEM_PROMPT
from .store import ConversationStore
from .tools import execute, openai_tools

FALLBACK_TEXT = "Poxa, tive um problema aqui para concluir sua consulta. Pode repetir a pergunta? Se preferir, a equipe da loja te atende pelo WhatsApp."
MAX_HISTORY_MESSAGES = 40


@dataclass
class ToolTrace:
    name: str
    arguments: str
    result: dict


@dataclass
class AgentReply:
    text: str
    tool_calls: list[ToolTrace] = field(default_factory=list)
    steps: int = 0


def make_client():
    from openai import OpenAI

    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("Defina OPENROUTER_API_KEY (veja .env.example).")
    return OpenAI(
        api_key=key,
        base_url=config.OPENROUTER_BASE_URL,
        timeout=90,
        default_headers={"HTTP-Referer": "https://github.com/emporio-agent", "X-Title": "Emporio da Musica - agente de atendimento"},
    )


def _window(messages: list[dict], limit: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Últimas `limit` mensagens, sempre começando em uma mensagem do usuário (não corta no meio de tool_calls)."""
    msgs = messages[-limit:]
    while msgs and msgs[0].get("role") != "user":
        msgs = msgs[1:]
    return msgs


class EmporioAgent:
    def __init__(
        self,
        client: Any = None,
        model: str | None = None,
        store: ConversationStore | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        max_steps: int = 6,
        temperature: float = 0.2,
    ) -> None:
        self._client = client
        self.model = model or config.model_name()
        self.store = store or ConversationStore()
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.temperature = temperature

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def _extra_body(self) -> dict | None:
        # Sem "thinking": o loop não reenvia reasoning_details entre chamadas de ferramenta.
        # EMPORIO_REASONING=default deixa o provedor decidir.
        if os.getenv("EMPORIO_REASONING", "off").lower() == "default":
            return None
        return {"reasoning": {"enabled": False}}

    def reply(self, session_id: str, user_text: str) -> AgentReply:
        self.store.append(session_id, {"role": "user", "content": user_text})
        history = _window(self.store.history(session_id))
        convo = [{"role": "system", "content": self.system_prompt}, *history]

        traces: list[ToolTrace] = []
        for step in range(1, self.max_steps + 1):
            kwargs: dict[str, Any] = dict(model=self.model, messages=convo, tools=openai_tools(), tool_choice="auto", temperature=self.temperature)
            extra = self._extra_body()
            if extra:
                kwargs["extra_body"] = extra
            resp = self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            calls = list(getattr(msg, "tool_calls", None) or [])

            if not calls:
                text = (msg.content or "").strip() or FALLBACK_TEXT
                self.store.append(session_id, {"role": "assistant", "content": text})
                return AgentReply(text=text, tool_calls=traces, steps=step)

            assistant = {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                    for c in calls
                ],
            }
            convo.append(assistant)
            self.store.append(session_id, assistant)
            for c in calls:
                result = execute(c.function.name, c.function.arguments or "{}")
                traces.append(ToolTrace(c.function.name, c.function.arguments or "{}", result))
                tool_msg = {"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, ensure_ascii=False)}
                convo.append(tool_msg)
                self.store.append(session_id, tool_msg)

        self.store.append(session_id, {"role": "assistant", "content": FALLBACK_TEXT})
        return AgentReply(text=FALLBACK_TEXT, tool_calls=traces, steps=self.max_steps)
