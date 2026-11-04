"""Ferramentas do agente (única fonte de verdade — usadas pelo loop em Python e pelo servidor MCP).

Princípio: tudo que é fato (preço, estoque, prazo, conta) sai de código determinístico, não do LLM.
O modelo decide *quando* chamar cada ferramenta e *como* explicar o resultado ao cliente.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Callable

from . import config, policies
from .data import PIX_DISCOUNT, SITUACAO_PRODUTO, STATUS_PEDIDO, Product, get_db
from .util import STOPWORDS, brl, fold, q2, stem_pt, words

log = logging.getLogger("emporio.tools")

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
HORARIOS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}  # domingo/feriado: fechado
GENERICAS_CATEGORIA = {"instrumento", "musical", "musica"}


# ---------------------------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _haystack(product_id: int) -> tuple[frozenset[str], str]:
    p = get_db().products[product_id]
    text = " ".join([p.nome, p.categoria, p.descricao, *[str(v) for v in p.specs.values()]])
    toks = frozenset(stem_pt(w) for w in words(text))
    return toks, fold(text)


def _query_tokens(text: str) -> list[str]:
    return [stem_pt(w) for w in words(text) if w not in STOPWORDS]


def _match_categories(text: str) -> set[int]:
    qs = {t for t in _query_tokens(text) if t not in GENERICAS_CATEGORIA}
    if not qs:
        return set()
    out = set()
    for cid, name in get_db().categories.items():
        if qs & {stem_pt(w) for w in words(name)}:
            out.add(cid)
    return out


def _money(v: Decimal) -> str:
    return brl(v)


def _item(p: Product, detalhado: bool = False) -> dict:
    db = get_db()
    info = db.preco_info(p)
    d: dict[str, Any] = {
        "id": p.id,
        "nome": p.nome,
        "categoria": p.categoria,
        "situacao": SITUACAO_PRODUTO[p.situacao],
        "preco_atual": float(info["atual"]),
        "preco_atual_fmt": _money(info["atual"]),
    }
    if info["promo"]:
        d["promocao_ativa"] = {
            "nome": info["promo"].descricao,
            "desconto_percentual": float(info["promo"].percent),
            "preco_original_fmt": _money(info["tabela"]),
            "preco_promocional_fmt": _money(info["atual"]),
        }
        d["preco_pix_fmt"] = None
        d["pix_observacao"] = "Produto em promoção: o desconto de PIX não é cumulativo."
    else:
        d["preco_pix_fmt"] = _money(info["pix"])
        d["pix_observacao"] = "5% de desconto à vista no PIX sobre o preço de tabela."
    if p.vendavel:
        d["unidades_em_estoque"] = p.estoque
    spec_txt = ", ".join(f"{k}: {v}" for k, v in p.specs.items())
    if detalhado:
        d["descricao"] = p.descricao
        d["especificacoes"] = p.specs
    else:
        d["resumo"] = f"{p.descricao.split('.')[0]}. ({spec_txt})"
    return d


def buscar_produtos(
    consulta: str = "",
    categoria: str = "",
    preco_min: float | None = None,
    preco_max: float | None = None,
    apenas_disponiveis: bool = True,
    limite: int = 8,
) -> dict:
    db = get_db()
    limite = max(1, min(int(limite or 8), 15))
    cat_ids: set[int] | None = None
    if categoria:
        cat_ids = _match_categories(categoria)
        if not cat_ids:
            return {
                "erro": f"Não existe categoria parecida com '{categoria}' no catálogo.",
                "categorias_do_catalogo": sorted({p.categoria for p in db.products.values()}),
            }

    qtok = _query_tokens(consulta)
    pool = [p for p in db.products.values() if cat_ids is None or p.categoria_id in cat_ids]

    scored: list[tuple[int, Product]] = []
    for p in pool:
        toks, text = _haystack(p.id)
        hits = sum(1 for t in qtok if t in toks or (len(t) >= 4 and t in text))
        scored.append((hits, p))

    partial = False
    if qtok:
        full = [(h, p) for h, p in scored if h == len(qtok)]
        if full:
            scored = full
        else:
            scored = [(h, p) for h, p in scored if h > 0]
            partial = bool(scored)

    def preco(p: Product) -> Decimal:
        return db.preco_info(p)["atual"]

    if preco_min is not None:
        scored = [(h, p) for h, p in scored if preco(p) >= q2(preco_min)]
    if preco_max is not None:
        scored = [(h, p) for h, p in scored if preco(p) <= q2(preco_max)]

    omitidos = 0
    if apenas_disponiveis:
        omitidos = sum(1 for _, p in scored if not p.vendavel)
        scored = [(h, p) for h, p in scored if p.vendavel]

    scored.sort(key=lambda hp: (-hp[0], preco(hp[1]), hp[1].nome))
    result: dict[str, Any] = {
        "total_encontrado": len(scored),
        "mostrando": min(len(scored), limite),
        "produtos": [_item(p) for _, p in scored[:limite]],
        "criterio_de_preco": "O filtro de preço usa o preço atual (já com promoção ativa, se houver).",
    }
    if omitidos:
        result["indisponiveis_omitidos"] = omitidos
    if partial:
        result["correspondencia_parcial"] = "Nenhum produto atende a todos os termos; mostrando os que atendem a parte deles."
    if not scored:
        result["observacao"] = (
            "Nada encontrado com esses critérios. Diga isso ao cliente e, se fizer sentido, sugira relaxar "
            "o preço ou a categoria. Não invente produtos."
        )
        result["categorias_do_catalogo"] = sorted({p.categoria for p in db.products.values()})
    return result


def _find_product(ref: str) -> tuple[Product | None, list[Product]]:
    db = get_db()
    ref = (ref or "").strip()
    if ref.isdigit() and int(ref) in db.products:
        return db.products[int(ref)], []
    qtok = _query_tokens(ref)
    if not qtok:
        return None, []
    collapsed_q = "".join(words(ref))
    scored: list[tuple[float, float, Product]] = []
    for p in db.products.values():
        name_toks = {stem_pt(w) for w in words(p.nome)} | {stem_pt(w) for w in words(p.categoria)}
        hits = sum(1 for t in qtok if t in name_toks)
        collapsed_name = "".join(words(p.nome))
        score = hits / len(qtok)
        if len(collapsed_q) >= 4 and collapsed_q in collapsed_name:
            score = max(score, 1.0)
        ratio = SequenceMatcher(None, fold(ref), fold(p.nome)).ratio()
        if score > 0:
            scored.append((score, ratio, p))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    if not scored:
        return None, []
    top = scored[0]
    if top[0] >= 0.99 and (len(scored) == 1 or scored[1][0] < 0.99 or top[1] - scored[1][1] > 0.15):
        return top[2], []
    return None, [p for s, _, p in scored[:5] if s >= 0.5]


def _alternativas(p: Product) -> list[Product]:
    db = get_db()
    base = db.preco_info(p)["atual"]
    same = [q for q in db.products.values() if q.categoria_id == p.categoria_id and q.vendavel and q.id != p.id]
    near = [q for q in same if abs(db.preco_info(q)["atual"] - base) <= base * Decimal("0.35")]
    pool = near or same
    pool.sort(key=lambda q: abs(db.preco_info(q)["atual"] - base))
    return pool[:3]


def obter_produto(produto: str) -> dict:
    p, candidatos = _find_product(produto)
    if p is None:
        if candidatos:
            return {
                "ambiguo": True,
                "observacao": "Mais de um produto parece corresponder. Pergunte ao cliente qual deles.",
                "candidatos": [{"id": c.id, "nome": c.nome, "preco_atual_fmt": _money(get_db().preco_info(c)["atual"])} for c in candidatos],
            }
        return {"erro": f"Não encontrei nenhum produto parecido com '{produto}' no catálogo.", "dica": "Use buscar_produtos para explorar o catálogo."}
    out = {"produto": _item(p, detalhado=True)}
    if not p.vendavel:
        out["alternativas_disponiveis"] = [_item(a) for a in _alternativas(p)]
        out["observacao"] = {
            "sem_estoque": "Sem estoque agora: não confirme disponibilidade; sugira as alternativas.",
            "descontinuado": "Fora do catálogo: ofereça equivalentes/sucessores (alternativas).",
            "em_breve": "Ainda não está à venda: não prometa data nem estoque; sugira as alternativas.",
        }[p.situacao]
    return out


# ---------------------------------------------------------------------------------------------
# Pagamento
# ---------------------------------------------------------------------------------------------
def _parcela_minima(n: int) -> Decimal | None:
    if n == 1:
        return None
    if n <= 3:
        return Decimal(50)  # manual 3.1: "sem valor mínimo (exceto abaixo de R$ 50,00)" -> interpretado como piso de R$ 50
    if n <= 6:
        return Decimal(80)
    return Decimal(100)


def simular_pagamento(produto: str = "", quantidade: int = 1, valor_total: float | None = None) -> dict:
    quantidade = max(1, int(quantidade or 1))
    em_promocao = False
    nome = None
    situacao = None
    if produto:
        p, cands = _find_product(produto)
        if p is None:
            return {"erro": "Produto não identificado.", "candidatos": [c.nome for c in cands] or None}
        info = get_db().preco_info(p)
        base = q2(info["atual"] * quantidade)
        em_promocao = info["promo"] is not None
        nome = p.nome
        situacao = SITUACAO_PRODUTO[p.situacao]
    elif valor_total is not None and float(valor_total) > 0:
        base = q2(valor_total)
    else:
        return {"erro": "Informe 'produto' (nome ou id) ou 'valor_total'."}

    out: dict[str, Any] = {"produto": nome, "quantidade": quantidade if nome else None, "total_fmt": _money(base)}
    if situacao and situacao != SITUACAO_PRODUTO["disponivel"]:
        out["aviso"] = f"Produto não está disponível para compra agora ({situacao})."
    if em_promocao:
        out["pix"] = {"aplicavel": False, "motivo": "Produto em promoção — PIX não é cumulativo com promoção."}
    else:
        pix = q2(base * (1 - PIX_DISCOUNT))
        out["pix"] = {"aplicavel": True, "valor_fmt": _money(pix), "economia_fmt": _money(base - pix)}
        if not nome:
            out["pix"]["observacao"] = "Vale para preço de tabela; se algum item estiver em promoção, o PIX não cumula."
    out["debito_ou_boleto_a_vista_fmt"] = _money(base)

    opcoes = []
    for n in range(1, 13):
        parcela = q2(base / n)
        minimo = _parcela_minima(n)
        if minimo is None or parcela >= minimo:
            opcoes.append({"parcelas": n, "texto": f"{n}x de {_money(parcela)} sem juros"})
    out["credito_sem_juros"] = opcoes
    out["credito_max_parcelas"] = opcoes[-1]["parcelas"]
    out["regras_parcelamento"] = "Até 3x: parcela ≥ R$ 50 · 4x a 6x: parcela ≥ R$ 80 · 7x a 12x: parcela ≥ R$ 100 (manual, seção 3.1)."
    out["frete_campo_grande_e_regiao"] = "Grátis" if base > 500 else "R$ 35,00 (taxa fixa)"
    out["pode_combinar_formas_de_pagamento"] = base > 2000
    out["observacao"] = "Valores de parcela arredondados ao centavo; a última parcela pode ter diferença de centavos."
    return out


# ---------------------------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------------------------
_MAX_FALHAS, _JANELA_S = 5, 600
_falhas: list[float] = []
_falhas_lock = threading.Lock()


def reset_rate_limit() -> None:
    with _falhas_lock:
        _falhas.clear()


def _bloqueado() -> bool:
    agora = time.monotonic()
    with _falhas_lock:
        _falhas[:] = [t for t in _falhas if agora - t < _JANELA_S]
        return len(_falhas) >= _MAX_FALHAS


def _registrar_falha() -> None:
    with _falhas_lock:
        _falhas.append(time.monotonic())


def _identidade_ok(customer, contato: str) -> bool:
    contato = (contato or "").strip()
    if "@" in contato:
        return contato.lower() == customer.email
    digits = re.sub(r"\D", "", contato)
    if len(digits) < 10:
        return False
    return customer.telefone_digitos.endswith(digits[-11:])


def consultar_pedido(numero_pedido: int, email_ou_telefone: str) -> dict:
    if _bloqueado():
        return {
            "erro": "Muitas tentativas de validação. Por segurança, não consigo consultar pedidos agora.",
            "acao": "Ofereça encaminhar a um atendente (encaminhar_atendente).",
        }
    db = get_db()
    try:
        order = db.orders.get(int(numero_pedido))
    except (TypeError, ValueError):
        order = None
    customer = db.customers.get(order.customer_id) if order else None
    if not order or not customer or not _identidade_ok(customer, email_ou_telefone):
        _registrar_falha()
        # mesma mensagem para "pedido não existe" e "dado não confere": evita enumeração de pedidos
        return {"erro": "Não consegui validar esse pedido com os dados informados.", "acao": "Peça ao cliente para conferir o número do pedido e o e-mail/telefone do cadastro."}

    hoje = config.now().date()
    out: dict[str, Any] = {
        "pedido": order.id,
        "cliente_primeiro_nome": customer.nome.split()[0],
        "status": STATUS_PEDIDO[order.status],
        "status_codigo": order.status,
        "data_do_pedido": order.data.strftime("%d/%m/%Y"),
        "itens": [
            {"produto": db.products[i.product_id].nome if i.product_id in db.products else f"produto {i.product_id}", "quantidade": i.quantidade}
            for i in order.itens
        ],
        "total_fmt": _money(order.total),
        "forma_de_pagamento": order.pagamento_label,
    }
    if order.rastreio:
        out["codigo_de_rastreio"] = order.rastreio
        out["rastreio_onde_consultar"] = "Site dos Correios ou da Jadlog."
    if order.previsao_entrega:
        out["previsao_de_entrega" if order.status != "delivered" else "entrega_registrada_para"] = order.previsao_entrega.strftime("%d/%m/%Y")
    if order.observacoes:
        out["observacoes"] = order.observacoes

    if order.status == "delivered" and order.previsao_entrega:
        receb = order.previsao_entrega  # o sistema não guarda a data real de recebimento: usamos a data de entrega registrada
        arrep = receb + timedelta(days=7)
        out["prazos_para_troca_e_devolucao"] = {
            "hoje": hoje.strftime("%d/%m/%Y"),
            "recebimento_considerado": receb.strftime("%d/%m/%Y"),
            "dias_desde_o_recebimento": (hoje - receb).days,
            "arrependimento_7_dias": {"ate": arrep.strftime("%d/%m/%Y"), "dentro_do_prazo": hoje <= arrep},
            "troca_por_defeito_30_dias_da_compra": {
                "ate": (order.data + timedelta(days=30)).strftime("%d/%m/%Y"),
                "dentro_do_prazo": hoje <= order.data + timedelta(days=30),
            },
            "garantia_legal_90_dias_do_recebimento": {
                "ate": (receb + timedelta(days=90)).strftime("%d/%m/%Y"),
                "dentro_do_prazo": hoje <= receb + timedelta(days=90),
            },
            "aviso": "A data real de recebimento não consta no sistema (usamos a data de entrega registrada). "
            "Diga ao cliente que a equipe confirma a elegibilidade final, e consulte consultar_politicas para as condições.",
        }
    return out


# ---------------------------------------------------------------------------------------------
# Políticas, horário e encaminhamento
# ---------------------------------------------------------------------------------------------
def consultar_politicas(pergunta: str) -> dict:
    if not (pergunta or "").strip():
        return {"erro": "Informe a pergunta/assunto a consultar."}
    return policies.consultar(pergunta)


@lru_cache(maxsize=8)
def _feriados(ano: int) -> dict[date, str]:
    try:
        import holidays

        return dict(holidays.country_holidays("BR", subdiv="MS", years=ano))
    except Exception:  # biblioteca ausente: segue sem feriados (e avisa)
        return {}


def horario_atendimento(data_hora: str = "") -> dict:
    try:
        dt = datetime.fromisoformat(data_hora) if data_hora else config.now()
    except ValueError:
        return {"erro": "data_hora deve estar em formato ISO 8601, ex.: 2026-03-14T10:30:00"}
    dt = dt if dt.tzinfo else dt.replace(tzinfo=config.TZ)
    dt = dt.astimezone(config.TZ)
    feriados = _feriados(dt.year)

    def aberto_em(d: datetime) -> tuple[bool, str | None]:
        if d.date() in feriados:
            return False, f"feriado ({feriados[d.date()]})"
        faixa = HORARIOS.get(d.weekday())
        if not faixa:
            return False, "domingo"
        if not (faixa[0] <= d.hour + d.minute / 60 < faixa[1]):
            return False, "fora do expediente"
        return True, None

    aberto, motivo = aberto_em(dt)
    proxima = None
    if not aberto:
        for i in range(0, 14):
            dia = (dt + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            faixa = HORARIOS.get(dia.weekday())
            if not faixa or dia.date() in feriados:
                continue
            abre = dia.replace(hour=faixa[0])
            if abre > dt:
                proxima = f"{DIAS[abre.weekday()]}, {abre:%d/%m} às {abre:%H:%M}"
                break
    return {
        "agora": f"{DIAS[dt.weekday()]}, {dt:%d/%m/%Y} {dt:%H:%M} (horário de Campo Grande)",
        "aberto_agora": aberto,
        "motivo_se_fechado": motivo,
        "proxima_abertura": proxima,
        "horario_de_funcionamento": {"segunda a sexta": "09:00 às 18:00", "sábado": "09:00 às 13:00", "domingo e feriados": "fechado"},
        "feriados_verificados": bool(feriados),
        "observacao": "Datas especiais (Black Friday, aniversário, Natal) podem ter horário estendido, divulgado nas redes sociais.",
    }


def encaminhar_atendente(motivo: str, resumo: str, tipo: str = "outro", contato: str = "") -> dict:
    tipos = {"reclamacao", "troca_devolucao", "defeito_garantia", "duvida_politica", "pedido_especial", "outro"}
    if not (motivo or "").strip() or not (resumo or "").strip():
        return {"erro": "Informe 'motivo' e 'resumo' do caso."}
    tipo = tipo if tipo in tipos else "outro"
    agora = config.now()
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.STATE_DIR / "encaminhamentos.jsonl"
    seq = 1
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            seq = sum(1 for _ in fh) + 1
    protocolo = f"EM-{agora:%Y%m%d}-{seq:04d}"
    registro = {
        "protocolo": protocolo,
        "criado_em": agora.isoformat(timespec="seconds"),
        "tipo": tipo,
        "motivo": motivo.strip(),
        "resumo": resumo.strip(),
        "contato_informado": contato.strip() or None,
        "status": "aberto",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {
        "protocolo": protocolo,
        "mensagem": "Caso registrado e encaminhado ao responsável.",
        "prazo_de_retorno": "até 24 horas úteis",
        "observacao": "Informe o protocolo e o prazo ao cliente. Não prometa resultado (reembolso, exceção, desconto).",
    }


# ---------------------------------------------------------------------------------------------
# Registro (schemas JSON compartilhados por OpenAI-compatible e MCP)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., dict]

    def openai_schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


TOOLS: list[Tool] = [
    Tool(
        "buscar_produtos",
        "Busca no catálogo real da loja (preço, promoção ativa, estoque). Use SEMPRE que o cliente perguntar por opções, "
        "faixas de preço ou disponibilidade de uma categoria/tipo de instrumento. Por padrão só retorna itens disponíveis.",
        _obj(
            {
                "consulta": {"type": "string", "description": "Termos livres: marca, tipo, cordas (nylon/aço), cor etc. Ex.: 'nylon', 'Yamaha'."},
                "categoria": {"type": "string", "description": "Categoria: guitarras, baixos, baterias, teclados, violões, sopro, cordas orquestrais, ukuleles."},
                "preco_min": {"type": "number", "description": "Preço mínimo em R$ (preço atual, já com promoção)."},
                "preco_max": {"type": "number", "description": "Preço máximo em R$ (preço atual, já com promoção)."},
                "apenas_disponiveis": {"type": "boolean", "description": "true (padrão) = só itens com estoque."},
                "limite": {"type": "integer", "description": "Máximo de itens (1-15, padrão 8)."},
            }
        ),
        buscar_produtos,
    ),
    Tool(
        "obter_produto",
        "Detalhes de UM produto específico (por nome ou id): preço, promoção, estoque, especificações e, se não estiver "
        "disponível, alternativas. Use para perguntas como 'quanto custa o Takamine GD20?' ou 'tem o X em estoque?'.",
        _obj({"produto": {"type": "string", "description": "Nome (ou parte do nome) ou id do produto."}}, ["produto"]),
        obter_produto,
    ),
    Tool(
        "simular_pagamento",
        "Calcula PIX (5%, exceto se o produto está em promoção), parcelamento sem juros válido pelas regras da loja, "
        "frete para Campo Grande e se dá para combinar formas de pagamento. Use em vez de fazer contas de cabeça.",
        _obj(
            {
                "produto": {"type": "string", "description": "Nome ou id do produto (preferível: aplica promoção corretamente)."},
                "quantidade": {"type": "integer", "description": "Quantidade (padrão 1)."},
                "valor_total": {"type": "number", "description": "Alternativa ao produto: valor total em R$ a simular."},
            }
        ),
        simular_pagamento,
    ),
    Tool(
        "consultar_pedido",
        "Consulta status, rastreio e prazos de troca/devolução de um pedido. EXIGE validação: número do pedido + e-mail "
        "ou telefone cadastrado. Nunca chame sem os dois dados informados pelo cliente.",
        _obj(
            {
                "numero_pedido": {"type": "integer", "description": "Número do pedido."},
                "email_ou_telefone": {"type": "string", "description": "E-mail ou telefone (com DDD) do cadastro do cliente."},
            },
            ["numero_pedido", "email_ou_telefone"],
        ),
        consultar_pedido,
    ),
    Tool(
        "consultar_politicas",
        "Busca no manual de políticas da loja: endereço, contatos, horários, formas de pagamento, parcelamento, trocas, "
        "devoluções, garantia, frete/entrega, rastreamento, promoções, privacidade e escopo do atendimento.",
        _obj({"pergunta": {"type": "string", "description": "O assunto/pergunta, em linguagem natural. Ex.: 'prazo para devolução por arrependimento'."}}, ["pergunta"]),
        consultar_politicas,
    ),
    Tool(
        "horario_atendimento",
        "Data/hora atual em Campo Grande e se a loja está aberta agora (considera sábado, domingo e feriados). "
        "Use para 'estão abertos?', 'até que horas?', ou quando precisar saber a data de hoje.",
        _obj({"data_hora": {"type": "string", "description": "Opcional, ISO 8601 (ex.: 2026-03-14T10:30:00) para checar outro momento."}}),
        horario_atendimento,
    ),
    Tool(
        "encaminhar_atendente",
        "Registra o caso e encaminha para um atendente humano (retorno em até 24 horas úteis). Use para reclamações, "
        "defeitos/avarias, pedidos de exceção, divergências no manual, ou qualquer coisa que as ferramentas não resolvam.",
        _obj(
            {
                "motivo": {"type": "string", "description": "Resumo em uma linha."},
                "resumo": {"type": "string", "description": "O que aconteceu, com números de pedido/produtos relevantes."},
                "tipo": {"type": "string", "enum": ["reclamacao", "troca_devolucao", "defeito_garantia", "duvida_politica", "pedido_especial", "outro"]},
                "contato": {"type": "string", "description": "Telefone/e-mail que o cliente informou para retorno, se houver."},
            },
            ["motivo", "resumo"],
        ),
        encaminhar_atendente,
    ),
]
REGISTRY = {t.name: t for t in TOOLS}


def openai_tools() -> list[dict]:
    return [t.openai_schema() for t in TOOLS]


def execute(name: str, arguments: Any) -> dict:
    """Executa uma ferramenta com tratamento de erro: o agente nunca quebra por argumento ruim do modelo."""
    tool = REGISTRY.get(name)
    if tool is None:
        return {"erro": f"Ferramenta desconhecida: {name}"}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            return {"erro": "Argumentos não são um JSON válido."}
    if not isinstance(arguments, dict):
        return {"erro": "Argumentos devem ser um objeto JSON."}
    try:
        return tool.fn(**arguments)
    except TypeError as exc:
        return {"erro": f"Parâmetros inválidos para {name}: {exc}"}
    except Exception:  # noqa: BLE001 - fronteira: não vazar stack trace para o modelo/cliente
        log.exception("falha em %s", name)
        return {"erro": "Falha interna ao executar a ferramenta."}
