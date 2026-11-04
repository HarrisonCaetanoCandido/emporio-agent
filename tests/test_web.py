import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace as NS

import pytest

from emporio.agent import EmporioAgent
from emporio.store import ConversationStore
from emporio.web import create_server, history_for_ui


class Fake:
    def __init__(self, script):
        self.script = list(script)
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return NS(choices=[NS(message=item)])


def tool_call(name, args):
    return NS(id="c1", function=NS(name=name, arguments=json.dumps(args)))


@pytest.fixture
def server(tmp_path):
    made = []

    def start(script, static_dir=None):
        agent = EmporioAgent(client=Fake(script), model="x", store=ConversationStore(tmp_path / "w.db"))
        srv = create_server(agent, "127.0.0.1", 0, static_dir)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    for s in made:
        s.shutdown()
        s.server_close()


def call(url, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_static_e_seguranca(server, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Bia</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "segredo.txt").write_text("x")
    base = server([], dist)
    status, body, headers = call(base + "/")
    assert status == 200 and b"Bia" in body and "script-src 'self'" in headers["Content-Security-Policy"]
    assert call(base + "/assets/app.js")[0] == 200
    assert call(base + "/assets/../../segredo.txt")[0] == 404
    assert call(base + "/%2e%2e/segredo.txt")[0] == 404
    assert call(base + "/api/inexistente")[0] == 404


def test_sem_build_avisa(server, tmp_path):
    status, body, _ = call(server([], tmp_path / "vazio") + "/")
    assert status == 503 and b"npm run build" in body


def test_chat_com_ferramenta_e_historico(server):
    base = server([
        NS(content=None, tool_calls=[tool_call("obter_produto", {"produto": "Takamine GD20"})]),
        NS(content="O GD20 sai por R$ 2.199,00.", tool_calls=None),
    ])
    status, body, _ = call(base + "/api/chat", {"session_id": "sessao-123456", "message": "Quanto custa o GD20?"})
    out = json.loads(body)
    assert status == 200 and out["reply"].startswith("O GD20") and out["tools"] == ["catálogo"]
    status, body, _ = call(base + "/api/history?session_id=sessao-123456")
    msgs = json.loads(body)["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["tools"] == ["catálogo"]


def test_validacao_de_entrada(server):
    base = server([])
    assert call(base + "/api/chat", {"session_id": "x", "message": "oi"})[0] == 400          # id curto
    assert call(base + "/api/chat", {"session_id": "sessao-123456", "message": "  "})[0] == 400
    assert call(base + "/api/history?session_id=../../etc")[0] == 400
    req = urllib.request.Request(base + "/api/chat", data=b"{quebrado", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 400


def test_erro_do_modelo_nao_vaza_detalhes(server):
    base = server([RuntimeError("chave sk-secreta inválida")])
    status, body, _ = call(base + "/api/chat", {"session_id": "sessao-123456", "message": "oi"})
    assert status == 502 and b"sk-secreta" not in body and "reply" in json.loads(body)


def test_history_for_ui_ignora_mensagens_de_tool():
    msgs = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "consultar_politicas", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "{}"},
        {"role": "assistant", "content": "Resposta"},
    ]
    assert history_for_ui(msgs) == [{"role": "user", "text": "oi"}, {"role": "assistant", "text": "Resposta", "tools": ["políticas da loja"]}]
