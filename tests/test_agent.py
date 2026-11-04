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


def test_tools_de_leitura_rodam_em_paralelo_e_mantem_ordem(tmp_path, monkeypatch):
    import threading
    import time

    from emporio import agent as agent_mod

    seen = set()
    barrier = threading.Barrier(2, timeout=3)

    def fake_execute(name, args):
        seen.add(threading.get_ident())
        barrier.wait()  # só passa se as duas chamadas estiverem em andamento ao mesmo tempo
        time.sleep(0.05 if name == "buscar_produtos" else 0)
        return {"nome": name}

    monkeypatch.setattr(agent_mod, "execute", fake_execute)
    client = FakeClient([
        NS(content=None, tool_calls=[tc("buscar_produtos", {}, "a"), tc("consultar_politicas", {}, "b")]),
        NS(content="pronto", tool_calls=None),
    ])
    agent = EmporioAgent(client=client, model="x", store=ConversationStore(tmp_path / "c.db"))
    r = agent.reply("s", "oi")
    assert len(seen) == 2
    assert [t.name for t in r.tool_calls] == ["buscar_produtos", "consultar_politicas"]  # ordem do modelo
    tool_ids = [m["tool_call_id"] for m in client.calls[-1]["messages"] if m["role"] == "tool"]
    assert tool_ids == ["a", "b"]


def test_ferramenta_exclusiva_forca_execucao_em_serie(tmp_path, monkeypatch):
    from emporio import agent as agent_mod

    order = []
    monkeypatch.setattr(agent_mod, "execute", lambda name, args: order.append(name) or {"ok": True})
    client = FakeClient([
        NS(content=None, tool_calls=[tc("consultar_pedido", {}, "a"), tc("buscar_produtos", {}, "b")]),
        NS(content="ok", tool_calls=None),
    ])
    agent = EmporioAgent(client=client, model="x", store=ConversationStore(tmp_path / "c.db"))
    agent.reply("s", "oi")
    assert order == ["consultar_pedido", "buscar_produtos"]


def test_falha_inesperada_em_tool_gera_resultado_e_historico_pareado(tmp_path, monkeypatch):
    from emporio import agent as agent_mod

    def boom(name, args):
        raise RuntimeError("segredo interno")

    monkeypatch.setattr(agent_mod, "execute", boom)
    client = FakeClient([
        NS(content=None, tool_calls=[tc("buscar_produtos", {}, "a"), tc("horario_atendimento", {}, "b")]),
        NS(content="Não consegui consultar agora.", tool_calls=None),
    ])
    store = ConversationStore(tmp_path / "c.db")
    r = EmporioAgent(client=client, model="x", store=store).reply("s", "oi")
    assert r.text.startswith("Não consegui")
    hist = store.history("s")
    assert [m["role"] for m in hist] == ["user", "assistant", "tool", "tool", "assistant"]
    assert all("segredo" not in m["content"] for m in hist if m["role"] == "tool")  # sem vazar a exceção
    assert {m["tool_call_id"] for m in hist if m["role"] == "tool"} == {"a", "b"}


def test_prefixo_de_tools_estavel_entre_passos(tmp_path):
    client = FakeClient([
        NS(content=None, tool_calls=[tc("horario_atendimento", {}, "a")]),
        NS(content="ok", tool_calls=None),
    ])
    EmporioAgent(client=client, model="x", store=ConversationStore(tmp_path / "c.db")).reply("s", "oi")
    a, b = client.calls
    assert a["tools"] is b["tools"] or json.dumps(a["tools"]) == json.dumps(b["tools"])
    assert a["messages"][0] == b["messages"][0]  # system prompt idêntico
