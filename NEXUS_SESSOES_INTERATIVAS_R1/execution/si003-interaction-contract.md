# SI-003 session interaction contract

The first wire models are in
`src/okto_nexus/adapters/inbound/http/session_interaction_contract.py`. They
reject unknown fields and accept exactly one bounded UTF-8 text block per
input. The session references existing R4 IDs. The complete selection has
Server, executor, binding, workspace, workspace binding, agent, session and
owner generation. A capability revision is a precondition and never acts as
authority. Validation and reading of a DTO never admits an operation.

The Server gets the human author and surface from the authenticated route.
Persist a revocable reference to that authority with the input. Keep actor
and session recipient separate. Participate in the exact current R4 grant,
lease and ownership checks whenever the input can produce an effect,
including the last dispatch gate. No client field sets the actor or surface.
A delayed worker will need an ordering protocol across authorization and the
execution database before it can submit on behalf of a previous login.

## Queue lifecycle

`EnqueueInput` represents only `next_turn`. It has a stable client intent ID
and a fingerprint of the exact normalized scope, mode and content. Preserve
text bytes without stripping or concatenating. An identical retry returns
the same durable input. Inputs are ordered by the committed sequence in
each exact session. Missing, stale or uncertain readiness yields no
productive dispatch. A positive reservation is still required at the
existing arbiter, after fully settling the prior turn.

Ordinary dispatch selects `QUEUED` only. A transaction must fence the
current scope, queue and input revisions before assigning a canonical
operation and moving to `DISPATCHING`. The operation carries any later
turn outcome. The input records delivery separately. `DELIVERY_UNKNOWN`
holds the reference for canonical reconciliation. A timeout does not
promote, cancel or send it again. `REFUSED_BEFORE_SEND` requires recorded
evidence of no write before any explicit recovery.

Cancel accepts only held input before dispatch, including paused input.
Promote accepts queued input and fixes its exact turn target and effect
review. The target is a native turn ID or a qualified observation of a
specific run, for adapters without native turn IDs. An unqualified
`current_run` target is refused.
Both actions require current input and queue revisions. An atomic promotion
makes the item ineligible for normal dispatch before sending the steer
operation. Reject a racing cancel or promote after the operation can have
an effect. Interrupt fixes the same kind of target and installs a durable session queue
barrier before control dispatch. A refusal does not remove the barrier.
Resuming the queue is a separate operation with current authority and
queue revision. Closing any presentation leaves the queue alone.

## CLI and attachment

`connect -i` and `connect --interactive` request native attachment after a
confirmed connection. `--no-interactive` and legacy `--no-chat` suppress
post-connect interaction. A positive and negative request conflict.
Reject `-ni`, abbreviations, and interactive JSON or streams without a TTY
before setup effects. A compatible `--plan` shows the selected surface
without opening a process. Default TTY after successful setup asks once,
default No. A post-setup attachment failure preserves the setup receipt.
`work resume` continues recovery of a previously submitted request.

`PrepareAttachment` distinguishes live attach from reopening a saved context
and read from write. Its public scope has no provider credential, host
path, engine token or command line. The broker must independently authorize
and resolve the requested strategy. Method allowlists, one writer, viewer
lease and no propagation of client shutdown are implementation gates.
The versioned catalog can report commands as unqualified. Syntax alone
does not advertise support or activate a handler.

This increment freezes the first server wire models and validates their
negative boundary cases. It introduces no routes, migrations or activation.
Frontend client generation, transport, queue effects and native attach
qualification are still tracked in their own tasks.

The focused contract suite passed 17 checks after adding typed turn targets
and a receipt fence. The earlier combined source run passed its 14 preceding
contract checks and 14 existing command-payload/backlog checks with the
version-bump dependencies. Those existing checks exercise the current
canonical runtime. They do not qualify the new interaction route or queue.

## Validação do contrato atual

`SteerTargetView` passa a conferir a combinação de alvo e efeito na resposta de revisão. A Home já representa esses pares em `SessionSteerTarget` e valida a resposta recebida. O CLI também confere o par antes de pedir a confirmação. Os três pares válidos preservam o formato publicado.

| Alvo | Efeito anunciado |
| --- | --- |
| `native_turn` | `same_turn` |
| `observed_run` | `next_boundary` |
| `claude_operation` | `interrupt_then_send` |

O teste de contrato reproduziu a aceitação de pares incompatíveis no wheel anterior. No candidato, a validação aceita os três pares da tabela e recusa as seis combinações cruzadas. Os exemplos negativos de entrada, anexo e recibo continuam na suíte. Eles incluem revisão ausente, identidade de autor enviada pelo cliente e efeito incerto sem operação vinculada.

No Windows, passaram 82 testes instalados de contrato, armazenamento, fila, controles HTTP e parser. Dois autores receberam sequências distintas no SQLite. A disputa de cancelamento ou promoção com o despacho preservou um vencedor em cada ordem. O teste de reorientação também confirmou o envio único e a liberação da fila após o turno. A prova com duas abas permanece vinculada a SI-T-B05. [Fila com duas abas](si007-concurrent-browser-fifo.md) [Disputas de despacho](si035-queue-dispatch-races.md)

Uma checagem adicional executou sete chamadas do CLI instalado, incluindo as quatro combinações conflitantes com `-i` no ConPTY. Todas retornaram código 2, mantiveram os arquivos locais e deixaram o socket de teste sem conexões. As provas concluem os cenários focais do contrato. A disputa HTTP usou um peer simulado. [Resultados, invocações e hashes](si003-current-contract.json)

O wheel e o sdist passaram no Twine e a instalação offline conferiu os pins. O único arquivo do pacote alterado é o modelo de contrato. O Ruff conservou os mesmos dois diagnósticos do teste de compactação já presentes no baseline. A mudança dispensa migração e pode ser revertida pelo commit.
