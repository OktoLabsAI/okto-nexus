# Auditoria de aceite — handoff broadcast runtime/MCP

Esta matriz acompanha o plano original, sem reduzir seus requisitos. `Local`
significa evidência automatizada no código atual, com provider sintético quando
indicado. Não significa qualificação de todos os harnesses, build instalado ou
host remoto independente. `Parcial` indica uma lacuna de integração ou de
auditoria que ainda precisa ser fechada. Os relatórios históricos do ledger
continuam válidos para os cenários efetivamente exercitados, sem substituir a
auditoria do conjunto final.

Atualização da qualificação instalada: a campanha de 128 casos do Nexus e a de
12 casos de compatibilidade terminaram sem falhas nem alterações de inputs.
Essas campanhas usaram o primeiro build Core 0.0.11. A auditoria T24 detectou
depois um backfill incorreto de claims ao reabrir o journal e a correção gerou
o wheel Core de SHA-256 `bf84ad1f3e12bcde9ef2b83d80985fdeca41a8ca0bce0f8ebc7dc4f141636892`.
Com esse artefato, 187 testes instalados do Core e 99 do Connector passaram;
54 cenários de recuperação/integração do Nexus passaram, sem falhas, erros ou skips; campaign PASS e changed_inputs vazio. O ledger
registra essa distinção; a campanha anterior não comprova o build corrigido.
Os dez invariantes estão mapeados em `invariant-audit.md`, com evidência local.

Campanha de escala/capacidade: 85 casos distintos do Nexus e 29 do Core aprovados. Relatórios:

- `build/handoff-broadcast/criteria-discovery-affinity.xml`: 61 aprovados.
- `build/handoff-broadcast/criteria-admission-lifecycle.xml`: 21 aprovados e uma
  expectativa de fixture corrigida no relatório seguinte.
- `build/handoff-broadcast/criteria-last-slot-final.xml`: o caso corrigido passou.
- Core `build/handoff-criteria-physical.xml`: 29 aprovados.
- `build/handoff-broadcast/criteria-connector-process-final.xml`: 2 aprovados;
  reinício normal e queda abrupta do Connector, sem provider iniciado na queda.

Complemento de seleção, ordem e desfechos: 48 casos distintos do Nexus aprovados
(há sobreposição com regressões da campanha anterior; não somar como casos novos):

- `criteria-sender-message-order.xml`: 1 aprovado.
- `criteria-executor-selection-final.xml`: 26 aprovados, incluindo 6 casos com
  dois Connectors em processos separados e regressões de seleção/scheduler/métricas.
- `criteria-business-outcomes.xml`: 15 aprovados e 2 falhas de fixture por enviar
  feedback com verdict `pass`, contrato que aceita feedback apenas com `fail`.
  `criteria-verification-pass.xml` confirmou os 2 corrigidos. Depois,
  `criteria-business-outcomes-final.xml` aprovou os 6 casos de desfecho com
  contagem explícita de eventos e notificações; os outros 11 já haviam passado.
- `criteria-ordinary-fanout-final.xml`: 1 aprovado, dois runtimes e um MCP-only.
- `criteria-selection-architecture.xml`: 3 aprovados.

Esses relatórios estão em `build/handoff-broadcast/`. Nesta etapa houve uma
correção de produto: propagar `AMBIGUOUS_BINDING` até o scheduler/projeções em
vez de apresentar o conflito de seleção como `RECOVERING`. A autoridade de
seleção e a política de substituição de máquinas não foram alteradas.

Os nomes de arquivos abaixo são relativos a `tests/execution_r4/` do Nexus,
exceto onde indicado. Cada linha explicita o limite da evidência.

| Critério | Situação | Evidência e verificação restante |
|---|---|---|
| T01 | Local | `test_handoff_broadcast_scale.py`: 100 agentes cadastrados e conectados pelas APIs, descoberta paginada e scheduler real; um claim, um grant de trabalho consumido, um open/turn nativo; 99 tentativas perdedoras encerradas. Provider sintético. |
| T02 | Local | `test_handoff_runtime_candidates.py`: MCP-only vence com reserva runtime em curso; limpeza durável sem dispatch nativo. |
| T03 | Local | `test_handoff_last_slot.py`: depois do vencedor runtime, claim MCP retorna `HANDOFF_ALREADY_CLAIMED`; permanece uma execução e um vínculo canônico. |
| T04 | Local | `test_handoff_last_slot.py`: host com uma vaga ocupada recusa outro trabalho; a tarefa continua disponível e pode ser assumida por MCP, sem fila produtiva runtime. |
| T05 | Local | `test_handoff_runtime_candidates.py`: liberação física publica capacidade e acorda o scheduler com backoff e varredura ainda congelados, sem nova mensagem. |
| T06 | Local | Mesmo arquivo: sinal de wakeup descartado; avanço até a varredura limitada recupera o trabalho uma única vez. |
| T07 | Local | Matriz de afinidades em `test_handoff_runtime_candidates.py`: shared ocupado não cria sessão alternativa. |
| T08 | Local | `test_handoff_message_order.py`: três mensagens diretas do mesmo sender usam uma sessão e executam em FIFO; o handoff permanece OPEN sem consumir grant enquanto cada turno/fila está ocupado, e só reserva/assume depois da terceira mensagem. |
| T09 | Local | Matriz de afinidades: outro sender pode abrir sessão distinta quando há capacidade; teto físico validado pelo gate do Core. |
| T10 | Local | Matriz de afinidades e `test_handoff_source_capacity.py`: mesma sessão autenticada de origem permanece ocupada. |
| T11 | Local | `test_handoff_source_capacity.py`: três origens MCP autenticadas; a terceira executa enquanto os dois primeiros turnos seguem sem receipt terminal. Não é uma invocação dos providers Claude/Codex reais. |
| T12 | Local | `test_handoff_origins.py`: fallback histórico explícito e origem persistida na mesma transação; matriz de afinidades inclui ausência de origem. |
| T13 | Local | `test_handoff_origins.py`: origem adulterada, prova ausente/incorreta, teto de ferramentas e permissão do agente. |
| T14 | Local | `test_handoff_runtime_candidates.py` mais `test_one_shot_handoffs.py`: pool cheio não admite claim automático; claims explícitos preservam fila. |
| T15 | Local | `test_reserved_handoff_admission.py` e candidatos warm: reserva/consumo reutilizam a mesma sessão e slot físico; duas instâncias warm executam independentemente. |
| T16 | Local | `test_handoff_startup_deadline.py` e `test_initial_refusal_restart.py`: 19 casos finais aprovados (inclui 3 checks arquiteturais). Reserva fria sem provider antes do claim; deadline validado no despacho e na lease; abertura tardia local/remota contida; recusa inicial recupera mesma operação após cortes de persistência e reinício. Serviço automático executa tarefa nova sem replay da antiga. Provider sintético, Connector em processo separado. |
| T17 | Local | `test_handoff_startup_deadline.py`: CLOSING e abertura remota pendente conservam HOST_FULL até stop confirmado, sem close concorrente. Core `capacity-physical-retention-review.xml` (12 casos) mantém slots consumidos/efeitos incertos ocupados após expiração e reinício; finalizar turno não libera o processo. Atribuir slot provisório na recuperação não o libera. Evidência automatizada local. |
| T18 | Local | `test_handoff_runtime_candidates.py`: max_parallel=0 continua sujeito ao limite físico do host. |
| T19 | Local | `test_handoff_last_slot.py`: duas origens/tarefas concorrentes, uma reserva efetiva; a perdedora permanece elegível por MCP. Limpeza confirma tombstone para a tentativa recusada após envio. |
| T20 | Local | `test_reserved_handoff_admission.py`: mensagem anterior bloqueia claim; mensagem posterior não rouba reserva; controle segue disponível. |
| T21 | Local | `test_reserved_handoff_tools.py`, revalidado na campanha Pi: mesma sessão vencedora usa MCP/native; sessão irmã não assume ou conclui o claim, sem novo dispatch. |
| T22 | Local | `test_handoff_executor_selection.py`: dois Connectors em PIDs distintos, canais/journals reais e provider sintético. Catálogo histórico de dois bindings aprovados é preparado explicitamente, pois onboarding atual substitui a máquina anterior. Prioridade, grupo, ambiguidade, grant revogado, afinidade ocupada e sessão não reconciliada preservam uma identidade lógica e no máximo uma execução. `AMBIGUOUS_BINDING` é exposto como motivo específico. |
| T23 | Local | `revocation-audit.md` mapeia sete fronteiras de assess até primeira lease para policy/grant/binding (21 combinações), mais trabalho em andamento. `test_handoff_revocation_boundaries.py` também cobre sessão warm, resposta perdida, prova ausente/adulterada e rollback. `test_remote_unsent_capacity_release.py` confirma liberação da reserva original por Connector em processo separado, sem provider. A recusa após consumo agora deixa obrigação durável de release, sem compensar claim ou matar sessão warm. |
| T24 | Local | `commit-boundary-audit.md` consolida 21 fronteiras, a UoW compartilhada e cortes reais antes/depois dos commits. Inclui criação/desbloqueio, agenda, descoberta, reserva/admissão/consumo, claim, sender/envio, compensação, negação/renovação, journal/receipts, publicação, contenção/release e retirement. A auditoria detectou e corrigiu backfill indevido de claims no restart do Core. Qualificação instalada final: Core 187, Connector 99 e Nexus 54 testes aprovados, incluindo novos cortes de recusa/migração, renovação e release. Sem inferir ACID entre hosts ou execução ausente sem prova. |
| T25 | Local | `test_handoff_runtime_attempts.py` cobre consulta da tentativa original após resposta perdida. `test_capacity_connector_process.py` perde a resposta na aplicação após commit real do ledger remoto, recupera a mesma identidade e comprova limite de uma vaga; reconnect/restart não substituem o ticket. |
| T26 | Local | `test_lost_reserve_response_restores_original_attempt_and_claim_after_restart` em `test_handoff_runtime_attempts.py`: perda da resposta depois do commit de CLAIM_COMMITTED, nova instância do serviço recupera exatamente operação/tentativa; epoch1 e um único consumo de grant, abertura e turno. Passou novamente em `criteria-revocation-regression.xml`. Recriação do serviço usa o mesmo banco; não é qualificação instalada. |
| T27 | Local | `test_remote_capacity_expiry.py`: três casos com daemon Connector em outro PID e HTTP/WebSocket reais, TTL real no ledger do Core. Expiração antes de lookup, entre lookup/consume e resposta de consumo perdida; mesma tentativa/operação compensada uma vez, OPEN no epoch1, nenhum provider. Frame tardio não ressuscita o ticket, e nova reserva confirma reutilização física. `criteria-remote-expiry.xml`: 3 aprovados. Tupla instalada permanece um gate separado. |
| T28 | Local | `test_handoff_executor_selection.py[unknown_native_reply]`: dois daemons Connector em PIDs distintos; provider recebe o turno e lança erro sem resposta. Core grava OUTCOME_UNKNOWN, Connector publica o fato exato sem derrubar a conexão. Depois de desconectar o vencedor e aumentar a prioridade do outro host disponível, descoberta recriada não adquire nova tentativa; claim/operação/epoch e um único envio são preservados, sem compensação. Connector `test_r4_execution.py` recusa fato ausente/hash divergente e permite outra sessão após publicar incerteza. Recuperação completa após desconexão continua em T29. |
| T29 | Local | `test_handoff_executor_selection.py[unknown_reconnect]`: perda explícita de link após OUTCOME_UNKNOWN, lease real de 15s, novo owner/generation/boot e retorno a ready em dois processos Connector. A geração anterior não registra owner, publica observação, consome reserva nem remove o novo registro; claim/epoch/envio únicos. `criteria-generation-fences.xml`: 24 aprovados incluindo respostas fora de ordem, frames WebSocket com conexão antiga, ACK tardio, serial de lease concorrente e agenda/claim de geração anterior. Tupla instalada e T40 seguem gates separados. |
| T30 | Local | `test_remote_running_containment.py`: Connector em processo separado, native turn iniciado, grant revogado ou runtime.close solicitado pela API. Close nativo é retido por mais de 11s; ticket permanece RELEASE_PENDING, host recusa outro slot e Server não anuncia parada confirmada. Depois de liberar o close, receipt/obrigação chegam a SUCCEEDED/RELEASED, nova reserva comprova reutilização física, sem reabrir claim ou repetir envio. Dois casos finais aprovados em `criteria-reconnect-containment-final.xml`; T40 continua separado. |
| T31 | Local | `runtime_diagnostics_validation` no ledger: final nativo permanece aguardando decisão; projeção, HTTP e navegador real, inclusive epoch e TTL. |
| T32 | Local | `test_handoff_business_outcomes.py`: execução e final nativo precedem conclusão autenticada por MCP/native; VERIFYING exige decisão, pass conclui e fail conserva subject como dono no epoch2. Descoberta não reabre a disputa nem admite outra execução para o retrabalho. Limpeza antes do consumo continua coberta em `test_capacity_terminal_cleanup.py`. |
| T33 | Local | Mesmo arquivo: repetição de completion e verificação mantém uma transição/evento/notificação por desfecho, um resultado capturado e uma execução. Mesmo com conversation habilitado, o final nativo do auto-claim não gera relay adicional; conclusão/verificação preservam a regra de não notificar o próprio ator. |
| T34 | Local | `test_handoff_ordinary_fanout.py`: mensagem comum alcança dois runtimes e deixa entrega MCP disponível para agente com sessão no workspace. Após respostas, handoff direto aciona somente o runtime alvo, sem tentativa automática de broadcast nem claim implícito. |
| T35 | Local | `test_handoff_runtime_notifications.py`: texto imitando aviso permanece mensagem comum, sem auto-claim por regex. |
| T36 | Local | `test_handoff_notice_migration.py` aplica o schema 133 até 139 e reexecuta sem alterações: texto imitado não vira controle, históricos admitidos/incertos e inbox permanecem intactos. `test_handoff_notice_retirement.py` cobre fence RESERVED/SENDING/RECONCILING, rollback, ACK MCP e fila anterior. `test_handoff_notice_lifecycle.py` verifica dois ciclos reais de startup preservando OUTCOME_UNKNOWN e tentativas anteriores, além de reinício sem replay. Campanha final de fontes: `criteria-fifo-backlog-final.xml`; lifecycle/restart também aprovado no pacote final instalado. |
| T37 | Local | Candidatos recusam contrato ausente ou apenas parte das extensões de contenção; nenhum fallback por invocação nativa. |
| T38 | Local | `test_handoff_pool_priority.py`: uma mensagem one-shot em execução e duas na fila têm precedência sobre broadcast automático. Scheduler efetivo é exercitado antes/depois de cada resposta e recriado em um dos casos; nenhum claim/grant/call produtivo para o broadcast antes de drenar os três consumidores. Depois, um único claim/turno no epoch1. `test_pool_immediate_admission.py` cobre adaptadores SQLite/memória, reserva warm/cold e consumidores em preparação. Os 44 casos da campanha FIFO/backlog/arquitetura passaram. |
| T39 | Local | `test_capacity_connector_process.py`: dois casos aprovados, daemon Connector em processo filho, HTTP/WebSocket reais e journals distintos. Perda de resposta, reconnect, reinício normal/queda abrupta com ticket não consumido, execução única, close confirmado e nova reserva após liberar capacidade. Descoberta/provider sintéticos; ambos os casos passaram com o tuple final instalado. Não qualifica outra máquina. |
| T40 | Adiado pelo usuário | Em 2026-10-14 o usuário escolheu validar o Connector local agora e testar outro host junto conosco depois. T39 e os testes de contenção usam processo separado e HTTP/WebSocket reais nesta máquina. T40 permanece sem comprovação, fora do escopo desta conclusão local. |

Pins e artefatos de Nexus 0.3.0, Core 0.0.11 e Connector 0.0.9 foram conferidos,
incluindo bytes instalados, `pip check`, manifesto e `uv lock --check`.
A campanha final e a consolidação de T24 foram concluídas. T01–T39 e os dez
invariantes têm evidência local; T40 foi adiado pelo usuário. A instância do
usuário permanece sem alteração. Não houve commit/push.
