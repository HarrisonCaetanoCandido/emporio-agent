"""Carga e tratamento dos CSVs da loja.

Tratamentos aplicados (documentados no README):
- strip em todos os campos; preços como Decimal (nunca float);
- `specs` (JSON em texto) vira dict; 'yes'/'no' vira 'sim'/'não';
- situação do produto derivada de (status, estoque): um produto "active" com estoque 0 é
  `sem_estoque` (não vendável); "coming_soon" e "discontinued" nunca são vendáveis, mesmo com estoque > 0;
- promoções: só `is_active == 1` conta; se houver mais de uma ativa no mesmo produto, vale a maior;
- telefones/e-mails normalizados (dígitos / minúsculas) para validação de identidade em pedidos.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import lru_cache

from . import config
from .util import q2

PIX_DISCOUNT = Decimal("0.05")

STATUS_PEDIDO = {
    "pending": "Aguardando confirmação do pagamento",
    "confirmed": "Pagamento confirmado — pedido em preparação",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

SITUACAO_PRODUTO = {
    "disponivel": "Disponível",
    "sem_estoque": "Temporariamente sem estoque",
    "descontinuado": "Descontinuado (fora do catálogo)",
    "em_breve": "Em breve (ainda não está à venda)",
}


def _read(name: str) -> list[dict[str, str]]:
    path = config.DATA_DIR / f"desafio_tecnico_ai_eng - {name}.csv"
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _pagamento_label(code: str) -> str:
    if code == "pix":
        return "PIX"
    if code == "debit":
        return "Cartão de débito"
    if code == "boleto":
        return "Boleto bancário"
    m = re.fullmatch(r"credit_(\d+)x", code)
    if m:
        return f"Cartão de crédito em {m.group(1)}x"
    return code


@dataclass(frozen=True)
class Product:
    id: int
    nome: str
    categoria_id: int
    categoria: str
    preco: Decimal
    descricao: str
    estoque: int
    status: str
    specs: dict
    criado_em: date

    @property
    def situacao(self) -> str:
        if self.status == "discontinued":
            return "descontinuado"
        if self.status == "coming_soon":
            return "em_breve"
        if self.status == "active" and self.estoque > 0:
            return "disponivel"
        return "sem_estoque"

    @property
    def vendavel(self) -> bool:
        return self.situacao == "disponivel"


@dataclass(frozen=True)
class Promotion:
    product_id: int
    percent: Decimal
    descricao: str
    ativa: bool


@dataclass(frozen=True)
class Customer:
    id: int
    nome: str
    telefone: str
    telefone_digitos: str
    email: str
    cidade: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantidade: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    data: date
    status: str
    total: Decimal
    pagamento: str
    rastreio: str
    previsao_entrega: date | None
    observacoes: str
    itens: tuple[OrderItem, ...] = field(default_factory=tuple)

    @property
    def pagamento_label(self) -> str:
        return _pagamento_label(self.pagamento)


def _date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


class Database:
    def __init__(self) -> None:
        self.categories = {int(r["category_id"]): r["name"] for r in _read("categories")}
        self.products: dict[int, Product] = {}
        for r in _read("products"):
            specs = json.loads(r["specs"]) if r["specs"] else {}
            if "electronics" in specs:
                specs["electronics"] = {"yes": "sim", "no": "não"}.get(str(specs["electronics"]).lower(), specs["electronics"])
            cat_id = int(r["category_id"])
            self.products[int(r["product_id"])] = Product(
                id=int(r["product_id"]),
                nome=r["name"],
                categoria_id=cat_id,
                categoria=self.categories.get(cat_id, "Sem categoria"),
                preco=q2(r["price_brl"]),
                descricao=r["description"],
                estoque=int(r["stock_quantity"] or 0),
                status=r["status"],
                specs=specs,
                criado_em=date.fromisoformat(r["created_at"]),
            )

        self.promotions = [
            Promotion(int(r["product_id"]), Decimal(r["discount_percent"]), r["description"], r["is_active"] == "1")
            for r in _read("promotions")
        ]
        self.active_promo: dict[int, Promotion] = {}
        for promo in self.promotions:
            if promo.ativa:
                best = self.active_promo.get(promo.product_id)
                if best is None or promo.percent > best.percent:
                    self.active_promo[promo.product_id] = promo

        self.customers = {
            int(r["customer_id"]): Customer(
                id=int(r["customer_id"]),
                nome=r["name"],
                telefone=r["phone"],
                telefone_digitos=re.sub(r"\D", "", r["phone"]),
                email=r["email"].lower(),
                cidade=r["city"],
            )
            for r in _read("customers")
        }

        items: dict[int, list[OrderItem]] = {}
        for r in _read("order_items"):
            items.setdefault(int(r["order_id"]), []).append(OrderItem(int(r["product_id"]), int(r["quantity"])))
        self.orders = {
            int(r["order_id"]): Order(
                id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                data=date.fromisoformat(r["order_date"]),
                status=r["status"],
                total=q2(r["total_brl"]),
                pagamento=r["payment_method"],
                rastreio=r["tracking_code"],
                previsao_entrega=_date(r["estimated_delivery"]),
                observacoes=r["notes"],
                itens=tuple(items.get(int(r["order_id"]), [])),
            )
            for r in _read("orders")
        }

    def preco_info(self, p: Product) -> dict:
        """Preço de tabela, promoção ativa (se houver), preço atual e preço PIX.

        Regra do manual (seção 6.2): promoções não são cumulativas — o desconto de PIX (5%)
        NÃO se aplica a preços já promocionais.
        """
        promo = self.active_promo.get(p.id)
        if promo:
            atual = q2(p.preco * (Decimal(100) - promo.percent) / Decimal(100))
            return {"tabela": p.preco, "promo": promo, "atual": atual, "pix": None}
        return {"tabela": p.preco, "promo": None, "atual": p.preco, "pix": q2(p.preco * (1 - PIX_DISCOUNT))}

    def quality_issues(self) -> list[str]:
        """Inconsistências encontradas nos dados (usadas no README e em testes)."""
        out = []
        for p in self.products.values():
            if p.status == "active" and p.estoque == 0:
                out.append(f"produto {p.id} ({p.nome}): status 'active' com estoque 0")
            if p.status in ("coming_soon", "discontinued") and p.estoque > 0:
                out.append(f"produto {p.id} ({p.nome}): status '{p.status}' mas estoque {p.estoque}")
        used = {p.categoria_id for p in self.products.values()}
        for cid, name in self.categories.items():
            if cid not in used:
                out.append(f"categoria {cid} ({name}) não tem nenhum produto cadastrado")
        by_email: dict[str, list[int]] = {}
        for c in self.customers.values():
            by_email.setdefault(c.email, []).append(c.id)
        for email, ids in by_email.items():
            if len(ids) > 1:
                out.append(f"e-mail repetido em clientes {ids}")
        for o in self.orders.values():
            soma = sum(self.products[i.product_id].preco * i.quantidade for i in o.itens if i.product_id in self.products)
            if o.itens and abs(soma - o.total) > Decimal("0.01"):
                out.append(f"pedido {o.id}: total {o.total} difere da soma dos itens a preço atual {soma}")
        return out


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database()


def reload_db() -> Database:
    get_db.cache_clear()
    return get_db()
