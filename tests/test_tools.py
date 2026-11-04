import json

from emporio import tools
from emporio.data import get_db


def test_data_and_quality():
    db = get_db()
    assert len(db.products) == 65
    assert set(db.active_promo) == {127, 121, 90, 94}
    assert db.products[96].situacao == "sem_estoque"
    assert db.products[113].situacao == "descontinuado"
    assert db.products[130].situacao == "em_breve"
    assert any("e-mail repetido" in i for i in db.quality_issues())


def test_violoes_ate_1000_apenas_disponiveis():
    r = tools.buscar_produtos(categoria="violões", preco_max=1000, limite=15)
    assert r["total_encontrado"] == 12
    assert all(p["categoria"] == "Violões" and p["preco_atual"] <= 1000 for p in r["produtos"])
    assert 96 not in [p["id"] for p in r["produtos"]]
    assert r["indisponiveis_omitidos"] == 2


def test_preco_pix_e_promocao_nao_cumulativos():
    gd20 = tools.obter_produto("Takamine GD20")["produto"]
    assert gd20["preco_atual_fmt"] == "R$ 2.199,00" and gd20["preco_pix_fmt"] == "R$ 2.089,05"
    taylor = tools.simular_pagamento(produto="Taylor 110e")
    assert taylor["pix"]["aplicavel"] is False and taylor["total_fmt"] == "R$ 5.519,08"


def test_parcelamento_regras():
    assert tools.simular_pagamento(produto="Shelby SU-21S")["credito_max_parcelas"] == 3  # R$ 159,90
    assert tools.simular_pagamento(valor_total=1200)["credito_max_parcelas"] == 12
    assert tools.simular_pagamento(valor_total=300)["credito_max_parcelas"] == 3
    assert tools.simular_pagamento(valor_total=600)["credito_max_parcelas"] == 6


def test_sem_estoque_traz_alternativas():
    r = tools.obter_produto("Giannini GF-3D")
    assert r["produto"]["situacao"].startswith("Temporariamente")
    assert r["alternativas_disponiveis"] and all("unidades_em_estoque" in a for a in r["alternativas_disponiveis"])


def test_nome_inexistente_e_ambiguo():
    assert "erro" in tools.obter_produto("Fender Jazzmaster Xyz 999")
    assert tools.obter_produto("Yamaha")  # ambíguo ou erro, nunca exceção


def test_pedido_validacao_e_prazos():
    c = get_db().customers[14]  # pedido 7 -> cliente 14
    ok = tools.consultar_pedido(7, c.email.upper())
    assert ok["status_codigo"] == "delivered"
    assert ok["prazos_para_troca_e_devolucao"]["arrependimento_7_dias"]["dentro_do_prazo"] is True  # hoje=20/02, entrega 17/02
    assert tools.consultar_pedido(7, c.telefone)["pedido"] == 7


def test_pedido_falha_generica_e_rate_limit():
    msgs = {json.dumps(tools.consultar_pedido(7, "errado@x.com")) for _ in range(2)}
    msgs.add(json.dumps(tools.consultar_pedido(9999, "errado@x.com")))
    assert len(msgs) == 1  # mesma resposta p/ pedido inexistente e dado errado
    for _ in range(5):
        tools.consultar_pedido(7, "errado@x.com")
    c = get_db().customers[14]
    assert "Muitas tentativas" in tools.consultar_pedido(7, c.email)["erro"]


def test_pedido_cancelado_mostra_motivo():
    o = get_db().orders[19]
    c = get_db().customers[o.customer_id]
    assert "Pagamento" in tools.consultar_pedido(19, c.email)["observacoes"]


def test_politicas():
    top = lambda q: tools.consultar_politicas(q)["trechos"][0]["secao"]
    assert top("me arrependi, posso devolver?").startswith("4.1")
    assert top("qual o endereço da loja?").split()[0] in {"0", "1.2"}
    assert top("vocês aceitam pix? e parcelar?").startswith("3")
    assert top("vendem corda de violão?").split()[0] in {"1", "7.1"}
    assert top("quanto é o frete para Dourados?").startswith("5")


def test_horario():
    assert tools.horario_atendimento("2026-02-17T10:00:00")["aberto_agora"] is True  # terça
    assert tools.horario_atendimento("2026-02-22T10:00:00")["aberto_agora"] is False  # domingo
    sab = tools.horario_atendimento("2026-02-21T14:00:00")
    assert sab["aberto_agora"] is False and "segunda" in sab["proxima_abertura"]
    feriado = tools.horario_atendimento("2026-09-07T10:00:00")  # Independência (segunda)
    assert feriado["aberto_agora"] is False and "feriado" in feriado["motivo_se_fechado"]


def test_encaminhar_atendente():
    r = tools.encaminhar_atendente("defeito", "violão chegou com trinca", "defeito_garantia", "(67) 99999-0000")
    assert r["protocolo"] == "EM-20260220-0001" and "24 horas" in r["prazo_de_retorno"]
    assert tools.encaminhar_atendente("x", "y")["protocolo"].endswith("0002")


def test_execute_robusto():
    assert "desconhecida" in tools.execute("nao_existe", {})["erro"]
    assert "JSON" in tools.execute("obter_produto", "{quebrado")["erro"]
    assert "inválidos" in tools.execute("obter_produto", {"foo": 1})["erro"]
