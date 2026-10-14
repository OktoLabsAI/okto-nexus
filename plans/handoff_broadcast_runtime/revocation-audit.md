# Auditoria de revogação — T23

Os cenários abaixo usam os serviços, SQLite, gates de capacidade e journals reais.
O provider é sintético. A matriz local revoga separadamente o opt-in de automação,
o grant de trabalho e o binding (endpoint desabilitado/revogado, como na substituição
de conexão). Policy e grant usam a API pública; a fixture de binding reproduz o
estado persistido para isolar o instante da revogação.

| Fronteira | Prova exigida e cenário |
|---|---|
| Antes de assess | Tentativa já persistida; autorização atual recusa aquisição. Limpeza não cria claim, operação ou consumo de grant. |
| Depois de assess | Observação AVAILABLE não concede posse; revalidação recusa a mesma tentativa antes da reserva. |
| Depois da reserva | Ticket real HELD; claim recusado, liberação idempotente da reserva original, handoff OPEN no epoch0. |
| Antes do consumo | Claim já commitado no epoch1; autoridade revogada impede consumo. Recusa comprovada permite compensação atômica e reabertura no mesmo epoch1. |
| Depois do consumo, antes do commit local | Core confirma consumo, depois a autoridade é revogada; Core libera apenas o gate ainda não iniciado. Prova exata e fence local permitem compensação, sem provider. |
| Antes do despacho | Reserva consumida e persistida; revogação enquanto o pump aguarda send_lock. A recusa RESERVED→RESOLVED_TERMINAL registra o fence e a obrigação de liberar na mesma transação. Scheduler envia release da reserva original, sem replay ou reabertura do handoff. |
| Antes da primeira lease | Envelope já enviado ao owner, sem autorização para abrir provider. Negação inicial e receipt do Core fecham a sessão e liberam a capacidade original; agente permanece disponível. |
| Durante trabalho nativo | `test_handoff_work_leases.py` revoga grant/opt-in. Contenção por sessão mantém RELEASE_PENDING enquanto stop é incerto; sessão irmã continua trabalhando. Retry retém o mesmo owner e só publica liberação após parada confirmada. |

As primeiras sete fronteiras estão em
`tests/execution_r4/test_handoff_revocation_boundaries.py` (21 combinações).
O mesmo arquivo cobre next_turn em sessão aquecida, perda da resposta de release,
prova de envio ausente/adulterada, rollback do commit local e resposta perdida
depois do commit. Não se deve confundir o fechamento da reserva de turno com
encerramento do processo do harness.

`test_remote_unsent_capacity_release.py` percorre consumo e liberação pelo
Connector em processo filho e HTTP/WebSocket reais. O grant é revogado no commit
que torna o consumo visível ao dispatcher. O worker não abre provider nem envia
turno, e uma nova reserva prova reutilização da vaga física do host remoto.
Isso não substitui a qualificação instalada nem o host independente de T40.

## Tratamento da recusa após consumo

A aplicação consulta a obrigação pelo port CapacityAdmissionRepository. O
adaptador SQLite correlaciona operação, hash, sessão, attempt_no, token e owner
do fence de não envio. A liberação usa o port de capacidade já existente,
igualmente para embedded e Connector; não há I/O do host na transação SQLite.

A admissão conserva o fato histórico de consumo. Enquanto a liberação não está
confirmada, permanece NEEDS_RECONCILIATION com motivo
UNSENT_DISPATCH_RELEASE_PENDING. Somente o receipt de capacidade RELEASED,
com request/reservation/consumption exatos e revisão não regressiva, permite
registrar UNSENT_DISPATCH_RELEASED e encerrar essa obrigação. Não existe
compensação de claim nessa etapa nem inferência de conclusão de tarefa.

Relatórios e resultados definitivos: `revocation_boundaries_validation` no
ledger. Esta auditoria mapeia T23; não declara que a matriz de todos os commits
do plano (T24) ou todos os cenários de cancelamento remoto (T30) está concluída.
