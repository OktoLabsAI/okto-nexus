# SI-T-B21 — Encaminhamento de agente e mensagem humana na mesma sessão

O Nexus recebeu uma mensagem pela API de interação e um encaminhamento
pelo fluxo canônico de coordenação. As duas intenções disputaram
`next_turn` da mesma sessão e geração no Core. O teste forçou as duas
ordens, suspendendo cada vencedor após a reserva do host.

| Reserva inicial | Efeito durante a disputa | Entrega após o primeiro turno |
| --- | --- | --- |
| Encaminhamento | O Core retornou `BUSY_AFFINITY` para a entrada humana e o recibo ficou na fila sem operação. | O dispatcher enviou a mensagem humana após o término do encaminhamento. |
| Mensagem humana | O Core retornou `BUSY_AFFINITY` para o encaminhamento. Sem claim e sem consumo de grant, ele continuou disponível. | Uma nova avaliação reservou a vaga e entregou o mesmo encaminhamento. |

A política mantém a reserva já concedida, serializa os turnos e mantém
as entradas humanas na ordem de aceite. O primeiro bloqueio do
encaminhamento é uma recusa de capacidade antes do claim. Ele pode ser
avaliado de novo pelo fluxo normal e não se transforma numa entrada
humana. Nenhuma das origens interrompe a outra automaticamente.

Passaram os dois casos no pacote instalado. A auditoria SQLite do Server
e do Core confirmou dois turnos, dois resultados e uma só sessão por
caso. Cada encaminhamento teve exatamente um claim, e cada mensagem
humana teve exatamente uma entrega. O cenário usou um peer Codex
simulado e o registro real de capacidade do host.
[Relatórios e hashes](si007-shared-turn-arbitration.json)

O primeiro observador supunha que a revisão inicial era 1. A repetição
usou a revisão retornada pelo recibo para correlacionar a reserva humana.
O marco atualiza as evidências, sem migração. Reverter o commit remove o
registro.
