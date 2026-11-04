import json
from types import SimpleNamespace as NS

from emporio.agent import EmporioAgent
from emporio.store import ConversationStore


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return NS(choices=[NS(message=self.script.pop(0))])


def tc(name, args, id="c1"):
    return NS(id=id, function=NS(name=name, arguments=json.dumps(args)))


def test_loop_executa_ferramenta_e_persiste(tmp_path):
    client = FakeClient([
        NS(content=None, tool_calls=[tc("obter_produto", {"produto": "Takamine GD20"})]),
        NS(content="O GD20 sai por R$ 2.199,00.", tool_calls=None),
    ])
    store = ConversationStore(tmp_path / "c.db")
    agent = EmporioAgent(client=client, model="x", store=store)
    r = agent.reply("s1", "Quanto custa o Takamine GD20?")
    assert r.text.startswith("O GD20") and r.tool_calls[0].name == "obter_produto"
    assert "2.199,00" in json.dumps(r.tool_calls[0].result, ensure_ascii=False)
    assert [m["role"] for m in store.history("s1")] == ["user", "assistant", "tool", "assistant"]
    # segunda mensagem reaproveita o histórico
    client.script.append(NS(content="ok", tool_calls=None))
    agent.reply("s1", "e em quantas vezes?")
    assert len(client.calls[-1]["messages"]) == 1 + 5  # system + 4 anteriores + novo user
    assert client.calls[0]["tools"]


def test_limite_de_passos(tmp_path):
    client = FakeClient([NS(content=None, tool_calls=[tc("horario_atendimento", {}, f"c{i}")]) for i in range(3)])
    agent = EmporioAgent(client=client, model="x", store=ConversationStore(tmp_path / "c.db"), max_steps=3)
    r = agent.reply("s", "oi")
    assert "problema" in r.text and r.steps == 3
