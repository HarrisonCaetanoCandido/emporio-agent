"""Normalização de texto (PT-BR) e formatação de dinheiro."""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def q2(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def brl(value) -> str:
    """Decimal/float -> 'R$ 1.299,90'."""
    s = f"{q2(value):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def fold(text: str) -> str:
    """minúsculas e sem acentos."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def stem_pt(tok: str) -> str:
    """Normaliza plurais comuns (violões -> violao, guitarras -> guitarra)."""
    if len(tok) <= 3:
        return tok
    if tok.endswith(("oes", "aes")):
        return tok[:-3] + "ao"
    if tok.endswith("ais"):
        return tok[:-3] + "al"
    if tok.endswith("ns"):
        return tok[:-2] + "m"
    if tok.endswith("s"):
        return tok[:-1]
    return tok


def stem_prefix(tok: str, n: int = 5) -> str:
    """Stemmer agressivo (prefixo) para recuperação: devolver/devolução -> 'devol'."""
    return stem_pt(tok)[:n]


STOPWORDS = frozenset(
    "a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem e ou que se "
    "me meu minha eu voce voces vc tem ter tenho quero queria gostaria quais qual quanto quanta "
    "como onde quando posso pode podem ser esta estao opcoes opcao disponivel disponiveis "
    "mostre mostra mostrar ate custando custa preco valor".split()
)
