"""Busca nas políticas da loja.

Decisão: o manual tem ~8 páginas e cada seção é semanticamente autocontida, então usamos
chunking por seção/subseção + BM25 lexical (com normalização PT-BR, stemmer de prefixo e uma
pequena expansão de sinônimos) em vez de embeddings + banco vetorial. Vantagens: zero dependência
externa, determinístico, auditável, e a resposta carrega o número da seção como fonte.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from . import config
from .util import STOPWORDS, stem_prefix, words

# gatilho (palavra normalizada) -> termos extras. Cobre o vocabulário do cliente x o do manual.
SINONIMOS: dict[str, str] = {
    "devolver": "devolucao arrependimento reembolso",
    "devolucao": "devolucao arrependimento reembolso",
    "arrependi": "devolucao arrependimento reembolso",
    "arrependimento": "devolucao arrependimento reembolso",
    "reembolso": "devolucao arrependimento reembolso",
    "estorno": "devolucao reembolso",
    "trocar": "troca defeito preferencia",
    "troca": "troca defeito preferencia",
    "quebrou": "defeito garantia troca",
    "defeito": "defeito garantia troca",
    "conserto": "garantia defeito",
    "endereco": "endereco localizacao empresa rua",
    "onde": "endereco localizacao empresa rua",
    "localizacao": "endereco localizacao empresa rua",
    "fica": "endereco localizacao",
    "telefone": "telefone contato whatsapp email",
    "contato": "telefone contato whatsapp email",
    "whatsapp": "whatsapp telefone atendimento",
    "email": "email contato",
    "horario": "horario funcionamento",
    "aberto": "horario funcionamento",
    "abre": "horario funcionamento",
    "fecha": "horario funcionamento",
    "funciona": "horario funcionamento",
    "sabado": "horario funcionamento",
    "domingo": "horario funcionamento",
    "feriado": "horario funcionamento feriados",
    "pagar": "pagamento formas parcelamento",
    "pagamento": "pagamento formas parcelamento",
    "pix": "pix pagamento desconto",
    "parcelar": "parcelamento parcela credito",
    "parcela": "parcelamento parcela credito",
    "cartao": "cartao credito debito pagamento",
    "boleto": "boleto pagamento",
    "frete": "frete entrega envio",
    "entrega": "frete entrega envio prazo",
    "entregar": "frete entrega envio prazo",
    "envio": "frete entrega envio correios",
    "prazo": "prazo entrega",
    "rastreio": "rastreamento codigo correios",
    "rastrear": "rastreamento codigo correios",
    "rastreamento": "rastreamento codigo correios",
    "promocao": "promocao desconto promocoes",
    "desconto": "promocao desconto pix",
    "oferta": "promocao desconto",
    "garantia": "garantia fabricante defeito",
    "corda": "acessorios exclusivamente instrumentos escopo",
    "palheta": "acessorios exclusivamente instrumentos escopo",
    "cabo": "acessorios exclusivamente instrumentos escopo",
    "case": "acessorios exclusivamente instrumentos escopo",
    "pedal": "acessorios exclusivamente instrumentos escopo",
    "amplificador": "acessorios exclusivamente instrumentos escopo",
    "acessorio": "acessorios exclusivamente instrumentos escopo",
    "reclamacao": "reclamacao atendimento responsavel",
    "reclamar": "reclamacao atendimento responsavel",
    "lgpd": "privacidade dados lgpd",
    "privacidade": "privacidade dados lgpd",
    "excluir": "privacidade dados exclusao",
}


@dataclass(frozen=True)
class Chunk:
    secao: str  # ex.: "4.1"
    titulo: str  # ex.: "Direito de Arrependimento (Compras Online)"
    pai: str  # título da seção-mãe, p/ contexto
    texto: str

    @property
    def rotulo(self) -> str:
        return f"{self.secao} {self.titulo}".strip()


def _parse(md: str) -> list[Chunk]:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    chunks: list[Chunk] = []
    pai = ""
    cur: dict | None = None

    def flush():
        nonlocal cur
        if cur and "".join(cur["lines"]).strip():
            chunks.append(Chunk(cur["secao"], cur["titulo"], cur["pai"], "\n".join(cur["lines"]).strip()))
        cur = None

    for line in md.splitlines():
        m = re.match(r"^(#{2,3})\s+(\d+(?:\.\d+)?)\.?\s+(.*)$", line)
        if m:
            flush()
            level, secao, titulo = len(m.group(1)), m.group(2), m.group(3).strip()
            if level == 2:
                pai = titulo
            cur = {"secao": secao, "titulo": titulo, "pai": pai if level == 3 else "", "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    flush()
    return chunks


def _tokens(text: str) -> list[str]:
    return [stem_prefix(w) for w in words(text) if w not in STOPWORDS]


def _expand(query: str) -> list[str]:
    toks = [w for w in words(query) if w not in STOPWORDS]
    extra: list[str] = []
    for w in toks:
        base = w[:-1] if w.endswith("s") and len(w) > 3 else w
        extra += words(SINONIMOS.get(w, "")) + words(SINONIMOS.get(base, ""))
    return [stem_prefix(w) for w in toks + extra]


class PolicyIndex:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(_tokens(f"{c.titulo} {c.titulo} {c.pai} {c.texto}")) for c in chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, top_k: int = 3) -> list[tuple[float, Chunk]]:
        q = Counter(_expand(query))
        scored = []
        for i, doc in enumerate(self.docs):
            s = 0.0
            for term, qtf in q.items():
                tf = doc.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
                s += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / denom * (1 + 0.25 * (qtf - 1))
            if s > 0:
                scored.append((s, self.chunks[i]))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]


@lru_cache(maxsize=1)
def get_index() -> PolicyIndex:
    md = (config.DATA_DIR / "politicas_da_loja.md").read_text(encoding="utf-8")
    return PolicyIndex(_parse(md))


def consultar(pergunta: str, top_k: int = 3) -> dict:
    hits = get_index().search(pergunta, top_k=top_k)
    if not hits:
        return {
            "trechos": [],
            "observacao": "Nenhuma seção do manual trata disso. Não invente: diga que não tem essa informação "
            "e ofereça encaminhar para um atendente.",
        }
    return {
        "trechos": [{"secao": c.rotulo, "texto": c.texto, "relevancia": round(s, 2)} for s, c in hits],
        "fonte": "Manual de Políticas e Procedimentos da Empório da Música, v2.1 (jun/2025)",
        "observacao": "Use apenas o que está nos trechos. Se trechos divergirem entre si, diga isso e ofereça confirmar com um atendente.",
    }
