# SI-008 recovery at the capacity boundary

The R4 dispatcher records its exact unsent proof when it refuses a
reserved interactive turn whose Core slot was consumed. Recovery verifies
operation ID and hash, attempt token and owner, terminal outbox state and
absence of a receipt before releasing the original Core reservation.
Release confirmation preserves the operation and its refusal. A lost
reply leaves the same proof available. An operation that crossed the
`SENDING` cut retains possible effect and remains in reconciliation.

An abandoned pre-admission request uses a separate fence. The SQLite
writer checks the original prepared request and input revision. Expired
and cancelled inputs are already fenced. An explicit authorization denial
blocks the original queued input and advances its revision. Core receives
the original attempt and can record release even when it has yet to see a
reservation. The writer retains the terminal host proof. Recovery can
observe an earlier owner on the same executor. A staged request uses its
canonical operation instead.

The focused migrated SQLite suite passed 11 cases in the isolated prefix.
It covers lost release replies, the actual R4 unsent refusal CAS, the
connection-loss path after SENDING, and pre-admission fencing on expiry
and denied authorization. The host replies are fixture data. This
increment adds no migration or public runtime registration. Scheduler
composition and real harness qualification remain pending.

## Revalidação no pacote instalado

No Windows, passaram 22 casos com o candidato `8bcee9bd`. As quatro
variantes de reinício do ciclo de vida do Server recuperaram a operação
original, com a admissão ligada e desligada. Um efeito incerto permaneceu
em `DELIVERY_UNKNOWN` e um efeito confirmado retornou `ACCEPTED_NATIVE`.
O sucessor fez zero envios e conservou o item seguinte, que ficou bloqueado
após o encerramento da sessão original.

Em HTTP por loopback, a perda da resposta após o commit preservou o recibo,
a posição e o texto. A retomada entregou a entrada uma única vez. O teste
de expiração confirmou `BLOCKED_AUTH`, sem nova reserva nem alteração
do grant e do lease. O ensaio de revogação no Edge e Pi continua registrado
com seu próprio candidato e provedor simulado.

Os reinícios deste teste usaram duas instâncias ASGI, banco persistido
e falha injetada. O cenário de encerramento abrupto do processo Server
continua registrado como limite da campanha. Este marco atualiza as
evidências e pode ser revertido sem migração.
[Resultados, hashes e fontes por cenário](si008-current-recovery.json)
