#!/usr/bin/env python3
"""Gera as conversas de exemplo (examples/*.md) rodando cenários REAIS contra o modelo configurado.

Nada aqui é escrito à mão: cada arquivo é a transcrição (mensagens, chamadas de ferramenta e respostas)
da execução. O relógio fica fixo em EMPORIO_NOW para os prazos de devolução serem reproduzíveis.

Uso:  python scripts/generate_examples.py        (requer OPENROUTER_API_KEY)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 20/02/2026 10:00 (sexta): pedido 7 foi entregue em 17/02 -> ainda dentro dos 7 dias de arrependimento.
os.environ.setdefault("EMPORIO_NOW", "2026-02-20T10:00:00")
os.environ["EMPORIO_STATE_DIR"] = tempfile.mkdtemp(prefix="emporio-examples-")

from emporio import config, data  # noqa: E402

config.load_env()
config.STATE_DIR = Path(os.environ["EMPORIO_STATE_DIR"])

from emporio.agent import EmporioAgent  # noqa: E402
from emporio.store import ConversationStore  # noqa: E402

_c = data.get_db().customers[14]  # dono do pedido 7 (entregue em 17/02/2026)

SCENARIOS: list[tuple[str, str, list[str]]] = [
    ("01-catalogo-violoes-ate-1000", "Catálogo: violões até R$ 1.000", ["Oi! Quais opções de violões disponíveis custando até R$1000?"]),
    ("02-endereco-e-horario", "Informações gerais: endereço e horário", ["Qual o endereço da loja?", "E vocês abrem sábado? Até que horas?"]),
    ("03-preco-e-parcelamento", "Preço e pagamento: Takamine GD20", ["Quanto custa o Takamine GD20?", "Dá pra parcelar em quantas vezes? E no PIX?"]),
    (
        "04-devolucao-pedido",
        "Política de devolução com consulta de pedido (caso não trivial)",
        [
            "Me arrependi da minha compra, posso devolver meu pedido?",
            f"Pedido 7, meu e-mail é {_c.email}",
        ],
    ),
    (
        "05-fora-de-escopo-e-sem-estoque",
        "Fora de escopo, acessório e produto sem estoque",
        ["Vocês vendem corda de violão?", "Qual a capital da França?", "Tem o Giannini GF-3D em estoque?"],
    ),
]


def main() -> None:
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    agent = EmporioAgent(store=ConversationStore(Path(os.environ["EMPORIO_STATE_DIR"]) / "ex.sqlite3"))
    print(f"modelo: {agent.model} | agora (fixo): {config.now():%d/%m/%Y %H:%M}")
    for slug, title, turns in SCENARIOS:
        for turn in turns:
            agent.reply(slug, turn)
        header = f"> Modelo: `{agent.model}` · data simulada: {config.now():%d/%m/%Y %H:%M} (Campo Grande) · linhas com 🔧 são chamadas de ferramenta.\n\n"
        md = agent.store.export_markdown(slug, title=title)
        title_line, _, rest = md.partition("\n\n")
        (out / f"{slug}.md").write_text(title_line + "\n\n" + header + rest, encoding="utf-8")
        print("gerado:", out / f"{slug}.md")


if __name__ == "__main__":
    main()
