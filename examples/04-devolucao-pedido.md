# Política de devolução com consulta de pedido (caso não trivial)

> Modelo: `deepseek/deepseek-v4.1-flash` · data simulada: 20/02/2026 10:00 (Campo Grande) · linhas com 🔧 são chamadas de ferramenta.

**Cliente:** Me arrependi da minha compra, posso devolver meu pedido?

**Bia:** Claro, posso te ajudar com isso! Só preciso de dois dados pra localizar seu pedido:

- Número do pedido
- E-mail ou telefone do cadastro

Me passa que eu verifico os prazos de devolução pra você.

**Cliente:** Pedido 7, meu e-mail é leticia.rocha@jmail.com

> 🔧 `consultar_pedido({"numero_pedido":7,"email_ou_telefone":"leticia.rocha@jmail.com"})`

> ↳ resultado: `{"pedido": 7, "cliente_primeiro_nome": "Letícia", "status": "Entregue", "status_codigo": "delivered", "data_do_pedido": "03/02/2026", "itens": [{"produto": "Shelby SU-21S Soprano Sunburst", "quantidade": 1}], "total_fmt": "R$ 159,90", "forma_de_pagamento": "Cartão de crédito em 3x", "codigo_de_rastr…`

> 🔧 `consultar_politicas({"pergunta":"prazo e condições para devolução por arrependimento"})`

> ↳ resultado: `{"trechos": [{"secao": "4.1 Direito de Arrependimento (Compras Online)", "texto": "- O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o recebimento do produto, sem necessidade de justificativa.\n- O produto deve estar em sua embalagem original, sem sinais de uso, com todos os …`

**Bia:** Boa notícia, Letícia! Seu pedido está dentro do prazo de arrependimento. 😊

Aqui está o resumo:

- Pedido 7 — Shelby SU-21S Soprano Sunburst
- Entrega registrada em 17/02/2026
- Prazo de arrependimento (7 dias corridos): até 24/02/2026 — você está dentro!

Condições para a devolução:
- O produto precisa estar na embalagem original, sem sinais de uso, com todos os acessórios e manuais.
- O reembolso é feito na mesma forma de pagamento (no seu caso, cartão de crédito em 3x), em até 10 dias úteis.
- O frete da devolução fica por conta da loja.

Só um detalhe importante: o sistema usa a data de entrega registrada, então a equipe confirma a elegibilidade final do seu caso.

Quer que eu encaminhe sua solicitação de devolução para um atendente dar sequência?
