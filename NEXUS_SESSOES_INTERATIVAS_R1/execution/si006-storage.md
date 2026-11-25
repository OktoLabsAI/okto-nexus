# SI-006 first SQLite increment

Migration 169 adds an input ledger and sequence per exact R4 session key.
It does not update old rows or migrations. Input identity binds the actor's
opaque authority reference and stable intention ID to exact scope, owner
generation, mode and text fingerprint. Retrying an unchanged intention
recovers the stored input. Changed text or scope under the same identity
conflicts. Two writes commit different sequence numbers.

The first write selects an exact session, its binding and endpoint agent.
The ledger stores the original content and server-chosen expiry. The
receipt contains metadata only. The write transaction allocates sequence
and records that receipt together. Before a caller acknowledges input it
must commit the unit of work. Acceptance creates no R4 operation, outbox
record or lease. A full queue refuses a new input and preserves retries of
prior inputs. SQL constraints maintain one canonical operation link and
keep possible effect on an unknown transmission.

Five SQLite tests used the full migration set and isolated fixture rows.
They covered rollback and retry across transactions, session and generation
isolation, two simultaneous authors, bounded pending intake and the writer
and workspace-binding guards. The scope
rows represent metadata only. The tests deliberately create no valid
lease or grant and do not confer operator authority. The final combined
session interaction and NS-00 run passed 32 cases.

The storage function is internal and no HTTP or CLI surface calls it yet.
The route must prove a current human authority reference. The processor
must reserve at the existing R4 capacity gate and revalidate authority
before an effect. TTL enforcement, pause/resume and cancellation are
worker and control behavior in subsequent stages. The migration's next
use must preserve uncertain operation links and accepted rows on rollback.

## Admissão e registros instalados

A rota de entrada usa `enqueue_human_input` para manter a autoridade do login e a transação de escrita até o commit. A mesma transação grava a sequência, o conteúdo, a impressão digital e as referências da sessão e da concessão. A restrição por sessão, autor e intenção mantém um recibo por pedido, e a restrição do vínculo com a operação preserva a identidade no despacho. A abertura do visualizador usa o registro de anexos. As leituras de conversa, capacidade, catálogo e fila consultam os dados da sessão.

Passaram 29 testes com os wheels instalados no Windows. As regressões verificaram a recusa de geração antiga, o vínculo ao login original, a ausência de recibo quando o commit falha e a recuperação do mesmo recibo quando a resposta se perde. A tentativa de trocar o texto sob a mesma intenção recebeu conflito. Com nome de projeto e ID público iguais em dois workspaces, a mistura de escopos retornou HTTP 409. O SQLite confirmou duas sessões encerradas e um único envio no workspace escolhido. [Resultados e hashes](si006-current-durable-input.json)

A migração de uma cópia do esquema 168 aplicou as 22 migrações até 190. A segunda execução aplicou zero. As colunas originais das 90 linhas em 161 tabelas permaneceram idênticas. O Core validou os quatro recibos legados e seus hashes, e o backup original conservou seu hash. O teste usou um banco descartável e peers simulados. As provas com Pi dos limites de entrada, leitura e autoria permanecem associadas aos seus ensaios. [Limites da API](si006-exact-input-boundaries.md) [Autoria no Pi](si006-pi-human-input-authority.md)

Este marco verifica SI-006. O commit atualiza as evidências e é reversível sem migração adicional.
No migration was applied to the global installation.
