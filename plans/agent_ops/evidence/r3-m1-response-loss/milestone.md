## 2026-11-07 — driver finito de perda de resposta M1

Preparado driver de cliente que descarta uma resposta de admissão e uma de
decisão, somente após a confirmação canônica correspondente. Reservas duráveis
impedem novo POST; reconstrução usa os mesmos checkpoints e IDs. Uma reserva
forwarding/unconfirmed deixada por crash bloqueia novas admissões/decisões,
mantendo inspeção e interrupt/close canônicos disponíveis.

No build final, 11 casos únicos passaram, incluindo integração com Nexus/Core
instalados, ASGI e SQLite reais e executor nativo sintético. A integração exige
um POST de trabalho, um POST de decisão, um turno e uma resposta sintéticos,
os mesmos IDs após perda, resultado e close. Foram conferidos 992 arquivos
antes/depois e ausência de módulos de produto importados do checkout.
Falhas anteriores de guard de teste e prefixo de rota permanecem preservadas;
a correção do crash foi seguida de requalificação dos 11 casos finais.

Isso prepara instrumentação da campanha, sem qualificar M1, Connector real,
login, inferência ou serviço do SO. A cota de seis envios deste wrapper ainda
não inclui setup:test automaticamente; faltam coletor e integração do runner
antes do primeiro teste produtivo. Nenhuma credencial pessoal ou provider foi
usado, nenhum arquivo de produto alterado, nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-response-loss/preparation/README.md`.
