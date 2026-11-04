# Informações gerais: endereço e horário

> Modelo: `deepseek/deepseek-v4.1-flash` · data simulada: 20/02/2026 10:00 (Campo Grande) · linhas com 🔧 são chamadas de ferramenta.

**Cliente:** Qual o endereço da loja?

> 🔧 `consultar_politicas({"pergunta": "endereço da loja"})`

> ↳ resultado: `{"trechos": [{"secao": "0 Contato e localização", "texto": "Empório da Música — \"Sua música começa aqui.\"\nEndereço: Rua 14 de Maio, 3200 — Centro, Campo Grande – MS, CEP 79202-333.\nTelefone: (67) 3341-4444. E-mail: contato@emporiodamusica.com.br.\nVersão 2.1 — Junho de 2025. Documento interno, d…`

**Bia:** Nossa loja fica na Rua 14 de Maio, 3200 — Centro, Campo Grande/MS, CEP 79202-333.

Quer que eu veja o horário de funcionamento ou ajude com mais alguma coisa?

**Cliente:** E vocês abrem sábado? Até que horas?

> 🔧 `horario_atendimento({})`

> ↳ resultado: `{"agora": "sexta-feira, 20/02/2026 10:00 (horário de Campo Grande)", "aberto_agora": true, "motivo_se_fechado": null, "proxima_abertura": null, "horario_de_funcionamento": {"segunda a sexta": "09:00 às 18:00", "sábado": "09:00 às 13:00", "domingo e feriados": "fechado"}, "feriados_verificados": true…`

**Bia:** Sim, abrimos sábado! Das 09:00 às 13:00. De segunda a sexta é das 09:00 às 18:00, e domingo e feriados ficamos fechados.

Agora são 10:00 de sexta, então estamos abertos. 😊
