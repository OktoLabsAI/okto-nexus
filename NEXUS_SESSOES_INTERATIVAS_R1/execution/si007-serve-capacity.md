# SI-007 compose the session queue with serve and R4

Serve advances a bounded page of durable input scopes through the existing
Core capacity registry. The scheduler uses the original request and operation
records for recovery. It shares serve shutdown ownership with handoff
scheduling. The embedded pump and both remote link paths use the original
operator login fence and the same next-turn revision resolver.

The resolver checks the exact session, current capacity owner and recent
binding observation. The approved installation must report a qualified
managed build in current Core evidence and match the build recorded at
opening. A heartbeat or lease renewal preserves the revision. Core
independently checks the boot, channel, lease and turn boundary when it
reserves capacity.

The startup option `--runtime-session-interaction-enabled true` enables
admission independently of automatic handoff acquisition. Its default is
false during qualification. Disabling it preserves the database and
prevents new session-input sends. Outstanding capacity attempts can still
be queried and reconciled with exact evidence. There is no new migration.

A serve integration with real SQLite, Core and R4 and a synthetic native
peer observed a busy ordinary turn, two FIFO inputs dispatched once each
after their preceding turns settled, and a revoked third input that stayed
blocked without a reservation or native submission. It also rejected a
different generation and stale inventory as capability evidence.
The related regression passed 94 tests with one excluded test. The excluded
handoff shutdown case timed out at both the working revision and baseline
`55e45460`. The fixture does not qualify a native adapter or remote journey.
Three existing settings assertions also failed at both revisions because
their expected feature lists omit `feature_observations`.

## Revalidação no pacote instalado

No candidato `8bcee9bd`, o Server registra o agendador junto ao registro
compartilhado de capacidade e ao pump R4. A fila seleciona o menor
`enqueue_sequence`, admite até 50 entradas pendentes por sessão e usa
validade de 24 horas. No Windows, passaram 16 casos de SQLite, capacidade
e HTTP, incluindo a espera pela fronteira elegível, a pausa e retomada em
ordem, a expiração de autorização e a troca de geração.

Os ensaios já registrados com Pi e Edge cobrem o fim de ferramenta, a
pergunta bloqueante, a chegada tardia de `agent_settled` e a fila após
fechar as abas. Os ensaios de ConPTY cobrem o fechamento do cliente
durante um turno do Codex. Esses ensaios usaram respostas simuladas e
mantêm seus respectivos candidatos e limitações. A revalidação acrescenta
evidência ao ledger e é reversível pelo commit, sem migração.
[Casos, hashes e evidências por cenário](si007-current-fifo.json)
