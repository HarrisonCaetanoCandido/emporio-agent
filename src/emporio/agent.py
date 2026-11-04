"""Loop de agente com function calling sobre a API OpenAI-compatible do OpenRouter.

É um loop ReAct nativo: o modelo escolhe ferramentas (tool_calls), executamos, devolvemos o resultado
e repetimos até ele responder em texto (limite de `max_steps` para evitar laços).
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from . import config
from .prompts import SYSTEM_PROMPT
from .store import ConversationStore
from .tools import execute, openai_tools

FALLBACK_TEXT = "Poxa, tive um problema aqui para concluir sua consulta. Pode repetir a pergunta? Se preferir, a equipe da loja te atende pelo WhatsApp."
MAX_HISTORY_MESSAGES = 40
MAX_PARALLEL_TOOL_CALLS = 4
# Ferramentas com efeito colateral ou estado (arquivo de encaminhamentos, rate limit de pedidos):
# se aparecerem num passo, o passo inteiro roda em série, na ordem pedida pelo modelo.
EXCLUSIVE_TOOLS = frozenset({"encaminhar_atendente", "consultar_pedido"})


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
        # Prefixo estável: mesmas definições de tools, byte a byte, em todos os passos (ajuda o cache do provedor).
        self._tools = openai_tools()

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

    @staticmethod
    def _run_one(call: Any) -> dict:
        try:
            return execute(call.function.name, call.function.arguments or "{}")
        except Exception as exc:  # noqa: BLE001 - toda chamada recebe um resultado, mesmo em falha inesperada
            return {"erro": f"Falha ao executar {call.function.name}: {type(exc).__name__}"}

    def _run_tools(self, calls: list[Any]) -> list[dict]:
        """Um resultado por chamada, na ordem pedida. Leituras independentes rodam em paralelo."""
        if len(calls) == 1 or any(c.function.name in EXCLUSIVE_TOOLS for c in calls):
            return [self._run_one(c) for c in calls]
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_TOOL_CALLS, len(calls))) as pool:
            return list(pool.map(self._run_one, calls))

    def reply(self, session_id: str, user_text: str) -> AgentReply:
        self.store.append(session_id, {"role": "user", "content": user_text})
        history = _window(self.store.history(session_id))
        convo = [{"role": "system", "content": self.system_prompt}, *history]

        traces: list[ToolTrace] = []
        for step in range(1, self.max_steps + 1):
            kwargs: dict[str, Any] = dict(model=self.model, messages=convo, tools=self._tools, tool_choice="auto", temperature=self.temperature)
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
            results = self._run_tools(calls)
            tool_msgs = []
            for c, result in zip(calls, results):
                args = c.function.arguments or "{}"
                traces.append(ToolTrace(c.function.name, args, result))
                tool_msgs.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, ensure_ascii=False)})
            # Grava a chamada e todos os resultados juntos: o histórico nunca guarda tool_calls sem resposta.
            for m in (assistant, *tool_msgs):
                convo.append(m)
                self.store.append(session_id, m)

        self.store.append(session_id, {"role": "assistant", "content": FALLBACK_TEXT})
        return AgentReply(text=FALLBACK_TEXT, tool_calls=traces, steps=self.max_steps)
