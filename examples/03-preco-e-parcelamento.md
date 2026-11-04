# Preço e pagamento: Takamine GD20

> Modelo: `deepseek/deepseek-v4.1-flash` · data simulada: 20/02/2026 10:00 (Campo Grande) · linhas com 🔧 são chamadas de ferramenta.

**Cliente:** Quanto custa o Takamine GD20?

> 🔧 `obter_produto({"produto": "Takamine GD20"})`

**Bia:** Vou verificar o preço pra você.

> ↳ resultado: `{"produto": {"id": 95, "nome": "Takamine GD20 Dreadnought Natural", "categoria": "Violões", "situacao": "Disponível", "preco_atual": 2199.0, "preco_atual_fmt": "R$ 2.199,00", "preco_pix_fmt": "R$ 2.089,05", "pix_observacao": "5% de desconto à vista no PIX sobre o preço de tabela.", "unidades_em_esto…`

**Bia:** O Takamine GD20 Dreadnought Natural está saindo por **R$ 2.199,00**. No PIX à vista fica **R$ 2.089,05** (5% de desconto). Tem 5 unidades em estoque.

É um violão dreadnought com tampo sólido em cedro, cordas de aço, ótimo pra fingerstyle. Quer saber mais alguma coisa sobre ele?

**Cliente:** Dá pra parcelar em quantas vezes? E no PIX?

> 🔧 `simular_pagamento({"produto": "Takamine GD20"})`

> ↳ resultado: `{"produto": "Takamine GD20 Dreadnought Natural", "quantidade": 1, "total_fmt": "R$ 2.199,00", "pix": {"aplicavel": true, "valor_fmt": "R$ 2.089,05", "economia_fmt": "R$ 109,95"}, "debito_ou_boleto_a_vista_fmt": "R$ 2.199,00", "credito_sem_juros": [{"parcelas": 1, "texto": "1x de R$ 2.199,00 sem juro…`

**Bia:** Dá sim! No cartão de crédito você parcela em até **12x sem juros**:

- 1x de R$ 2.199,00
- 2x de R$ 1.099,50
- 3x de R$ 733,00
- 6x de R$ 366,50
- 10x de R$ 219,90
- 12x de R$ 183,25

E no **PIX à vista** sai por **R$ 2.089,05** — economia de R$ 109,95. O frete pra Campo Grande e região é grátis. 😊

Quer que eu veja mais alguma coisa?
