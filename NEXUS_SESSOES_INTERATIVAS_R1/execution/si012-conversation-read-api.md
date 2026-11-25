# SI-012 scoped conversation replay over HTTP

`GET /v1/runtime/sessions/{session_id}/conversation` and its existing
dashboard alias read the same bounded projection. The request carries
Server, executor, binding, workspace, workspace binding, agent and the
expected owner generation. Pagination uses the canonical stream epoch and
sequence. Both surfaces use existing identity, session visibility and
error handling. Conversation pages carry `Cache-Control: no-store`, and bearer
authentication for this read uses the existing passive path.

The canonical replay, contract and transcript regression passed 39 cases.
The integration case sends synthetic host events through canonical ingress
and exercises both HTTP surfaces with real temporary SQLite storage,
subject authentication and a revocable operator login. It checks pagination,
omission of tool output, exact scope, foreign identity and logout. Replay
leaves operation and queue counts unchanged.

The archive still lacks some native message identities under the current
Core pin. The response therefore reports incomplete history. The HTTP test
is separate from native and browser qualification. This step adds no
migration. Reverting the route leaves the canonical journal intact.

## Revalidação no pacote instalado

Passaram 30 casos no candidato `8bcee9bd` no Windows. A leitura
reconciliou deltas e snapshots pela identidade nativa e conservou
mensagens distintas que tinham o mesmo texto. A origem de subagente
foi preservada. A projeção excluiu eventos privados e sinalizou o
trecho incompleto quando o histórico tinha uma lacuna. As páginas
usaram um cursor limitado à sessão e à geração selecionadas. O stream
voltou a conferir a autorização original antes de continuar.

O teste HTTP consultou os dois pontos de leitura sobre o journal
canônico em SQLite. Os ensaios de navegador, privacidade com Pi e
origem de subagente no Claude permanecem registrados com seus
próprios candidatos e limitações. A verificação dispensa migração e
pode ser revertida pelo commit. [Resultados e hashes](si012-current-transcript.json)
