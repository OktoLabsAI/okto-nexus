# Contratos de integração — alvo explícito R4

**Status: ESPECIFICAÇÃO A IMPLEMENTAR, não descrição de endpoints já existentes.** As APIs Core citadas como existentes pertencem a `0.2.10.dev0`. Rotas, DTOs e frames R4 deste documento requerem implementação coordenada. Não tornar um mock do Connector a autoridade do protocolo.

## 1. Versões, prefixos e representação

Fixar os identificadores abaixo no pacote de contratos compartilhado:

```text
plan_revision        = nexus-server-unified-r4-2026-09-29
management_revision  = nexus-connections-2026-09-29-r4
protocol_major       = 1
nxl_revision         = nxl-1-agent-centric-http-only-2026-09-29-r4
catalog_format       = 1 (atual)
availability_format  = 2 (atual; candidate_ref identifica instalação)
executor_snapshot    = 1 (novo envelope do aplicativo)
```

A revisão r3 atual permanece imutável, com seus vetores e manifest. O Core publica R4 em diretório/revisão separado ou mecanismo de bundle explicitamente versionado, mantendo a leitura dos receipts históricos. O Server não baixa schemas de `main` e não copia enums autorais. Durante a integração inicial, exigir mesma revisão e wheel/hash compatível fixado nos dois hosts. Um Connector r3 recebe `VERSION_INCOMPATIBLE` antes de novo efeito, com instrução de atualização; MCP HTTP e dados legados não dependem dessa negociação.

A alteração é necessária: r3 admite payload genérico, não possui confirmação explícita de attach/reconcile, torna owner generation opcional e não especifica payload completo de abertura remota. Além disso, o alvo de steer não pode obrigar ID de turno nativo para um adapter cujo Core usa run sem ID. Essas são lacunas de contrato, não autorização para modificar os codecs no Server.

**Prefixo:** `/v1` nas rotas novas. Sucesso é objeto JSON direto. Falha: `{ "error": { "code", "stage", "message", "possible_effect", "retry_safe", "operation_id", "action" } }`; campos nulos admitidos conforme schema. `/api/v1` legado preserva `{ok,data/error}`. Não ter dois handlers canônicos que executam a mesma operação. APIs legadas adaptam entrada/saída e chamam o mesmo caso de uso.

Responder `X-Nexus-Connections-Revision` em toda resposta `/v1`; cliente envia a revisão depois de consultar protocolo. Em `/v1`, usar somente bearer em header para credenciais. Query string com chave é rejeitada nessas rotas. Compatibilidade de extração antiga no `/mcp` é preservada, com geração de novas configurações por header e redaction dos acessos existentes; não é uma migração silenciosa de credenciais.

IDs de fio novos: strings 1–160 caracteres, não truncadas. Native request ID é JSON original string ou inteiro limitado, guardado dentro da proposta; não convertê-lo na chave canônica global. Refs `nexus-install-v1:` e hashes `sha256:` conservam seu prefixo/versionamento. JSON rejeita chaves duplicadas, NaN/infinito e excesso de profundidade/bytes antes do JCS. `operation_id` externo legado de tamanho diferente permanece consultável pela rota de compatibilidade, não admitido como novo ID R4.

## 2. Autoridade e credenciais

### 2.1. Principais separados

`AuthenticatedPrincipal` é criado na fronteira autenticada e contém `server_id`, `actor_agent_id`, `authentication_source`, epoch e permissões verificadas. Operação que representa outro agente registra também `subject_agent_id` e exige permissão existente de operador. Não aceitar `operator=true` do payload.

`LinkPrincipal` deriva do ticket: servidor, executor, binding, agente, credential epoch, audiences/scopes, expiry e conexão autorizada. `ChannelContext` acrescenta `connection_id` opaco, `connection_generation` e serial de socket local. Todo frame herda essa origem interna. Campos do frame são assertions a comparar, inclusive ACK, reconcile, approval e detach.

### 2.2. Tickets operacionais

Manter chave canônica do agente apenas em hash no Server. Ticket operacional usa bytes criptograficamente aleatórios, hash persistido, TTL inicial 600 s e escopo de binding/executor. Permitir emissão automática a 70% da validade, com jitter/single-flight, enquanto chave e binding continuam válidos. Expiração de ticket não é renovação da lease de trabalho.

Audiência de ticket: `nexus-executor-control`. Escopos possíveis, explicitamente emitidos: `link:connect`, `lane:attach`, `inventory:publish`, `realization:publish`, `receipt:publish`, `history:read`, `lease:request`. Emitir só os necessários ao papel. Ticket inicial de executor sem binding concede apenas inventory/realization bootstrap para o agente que registrou o executor; não admite runtime/lane. Não existe chave mestra de máquina.

Consumo de attach é vinculado ao request/connection: mesma tentativa pode consultar a confirmação; ticket já vinculado a outra conexão não autoriza takeover. Reconexão obtém ticket novo. Uma lane de outro agente precisa de ticket obtido pela chave daquele agente. Receber catálogo não prova direito sobre todas as lanes.

### 2.3. Capability MCP HTTP

Audiência separada `nexus-mcp-session`, token opaco diferente do ticket. Escopo contém agente, workspace, binding, sessão, configuração, owner e ações de domínio permitidas. `tools/call` é teto de protocolo, não autorização para qualquer tool. O guard de cada caso de uso aplica suas próprias permissões e claim.

Capability de sessão reservada pode ser emitida antes do spawn para compor o cliente, mas efeitos produtivos só são permitidos quando a sessão e sua lease estão ativas. Guardar o segredo em armazenamento local adequado do executor, não no prompt/argv/Server plaintext. Na resposta de emissão, `Cache-Control: no-store`.

O token pode permanecer estável durante a sessão; o Server renova/restringe validade canônica enquanto a lease é renovada legitimamente. Não pressupor hot reload do harness. Revogação impede novas chamadas imediatamente no Server; partição é limitada pelo prazo do executor. Não aceitar ticket NXL, EPT ou chave administrativa como capability de sessão.

### 2.4. Resposta perdida na emissão de segredo

Nunca recuperar plaintext a partir de hash. GET de ticket/capability já emitido devolve metadados, não o segredo. Se a resposta inicial se perdeu, o cliente solicita substituição identificada por novo `credential_request_id`, citando o ID anterior; o Server invalida o derivado anterior e emite outro somente dentro da mesma autorização e enquanto ainda não foi instalado/ativado em uma sessão. Isso é emissão de um derivado, não rotação da chave canônica, e não gera processo ou turno.

Para capability já instalada, não invalidar automaticamente por um timeout do cliente: conservar sua validade e seguir a política de renovação servidor-side. Se o segredo realmente foi perdido pelo executor, bloquear nova realização e exigir recuperação de configuração compatível; nunca reiniciar trabalho incerto para obter outro token. Respostas de replay sem material retornam `CREDENTIAL_MATERIAL_UNAVAILABLE`, com identificação do derivado e recuperação permitida. Ticket novo pode ser solicitado automaticamente sob chave canônica vigente, mas o ticket anterior não volta a ser validado para nova conexão.

Precisão do DTO de erro de capability: `CREDENTIAL_MATERIAL_UNAVAILABLE` inclui `capability_id` e `recovery_allowed` no objeto `error`, sem segredo. Esses campos opcionais estão declarados em `ErrorBody`. `recovery_allowed=true` informa que uma nova requisição de substituição pode ser avaliada; não reserva autorização nem dispensa revalidação transacional. Se o envio da abertura já puder ter instalado configuração, ou existir histórico de lease, a substituição automática é recusada. Renovação de validade de capability estável acompanha o commit de aplicação legítima da lease, não o simples envio do grant.

## 3. DTOs canônicos novos

Os nomes abaixo são fixados para a implementação; transportar por dataclass/Pydantic equivalente sem mudar sua semântica. Modelos do Core continuam sendo consumidos, não redefinidos localmente com o mesmo nome.

### 3.1. `ExecutionScope`

```text
server_id, executor_id, binding_id, agent_id, workspace_id,
workspace_binding_id, session_id: ID
session_owner_generation, authorization_revision,
configuration_revision, binding_revision, credential_epoch: inteiro >= 1
```

`AuthorizedExecution` agrega scope, operação imutável, `grant_id`, `lease_id/lease_serial` instalados, canal esperado e token da reserva. Ao construir `ExecutionContext` para o Core, usar o deadline monotônico já instalado no executor, nunca recalculá-lo de “agora + duração” a cada mensagem. Ações vêm do grant aprovado; vazio permanece vazio.

### 3.2. `ExecutorInventorySnapshot`

```text
snapshot_format_version = 1
server_id, executor_id, producer_instance_id: ID
publication_sequence: inteiro >= 1, crescente e persistido por executor
inventory_revision: sha256 JCS(evidence) completo, não truncado
core_version: string
catalog: RuntimeCatalog serializado publicamente (format_version = 1)
availability: AvailabilityReport.to_dict() (format_version = 2)
evidence: lista ordenada de CandidateEvidence
observation_age_ms: inteiro 0..300000
```

`CandidateEvidence`: `adapter_id`, `candidate_ref`, `content_fingerprint`, `build_identity` ou null, versão/arquitetura ou null, trust/source, suporte/plataforma, estado técnico/razões e capability report **somente quando observado**. Não transmitir executável, launch_script, HOME, nome de variável de segredo, token ou classe Python.

Para o digest, incluir versões de formato/Core e todos os campos técnicos que possam alterar seleção/realização; excluir sequence, producer_instance_id, observation_age, nomes apenas cosméticos e horário de publicação. Ordenar por `(adapter_id,candidate_ref)` e ordenar listas que representem conjuntos. Não retirar conteúdo do hash porque a versão textual não mudou.

TTL operacional inicial: 120 s após recebimento, reduzido por `observation_age_ms`; o Server usa seu monotônico para frescor do processo. Após restart, nenhum deadline monotônico persistido é restaurado: exigir nova publicação/validação. `publication_sequence` impede que snapshot antigo com digest válido substitua o atual. Mudança de instância produtora exige reconciliação do canal, não aceitar sequence 1 cegamente.

`candidate_ref` é local ao inventário do executor. Duas máquinas podem derivar refs iguais para paths iguais; validar executor no envelope. O Server não deduz os paths do hash e não os resolve.

### 3.3. `BindingProposal`

Campos exigidos: `proposal_id`, `proposal_revision`, `expires_at`, `server_id`, `executor_id`, `agent_id`, `binding_id`, `endpoint_id`, `profile_id`, `workspace_id`, `workspace_binding_id`, `adapter_id`, `candidate_ref`, `inventory_revision`, `realization_ref`, `realization_revision`, `authorization_revision`, `configuration_revision`, `required_approvals`, `diff`, `can_apply`.

`local_realization_ref` é emitida pelo executor depois de validar pasta/candidato/configuração e consentimento local. A publicação autenticada registra essa prova e recebe do Server a `realization_ref` canônica; o executor conserva o mapeamento entre ambas. O Server guarda somente refs, revisões e escopo, não o alvo físico como autoridade. Uma repetição idempotente retorna o mesmo mapeamento. Não criar um workspace remoto resolvendo path em A.

### 3.4. `IntentResolution`

Campos exigidos: `client_intent_id`, `intent_id`, `operation_id`, `session_id`, `reuse`, `scope`, `semantic_intent`, `intent_hash`, `resolution_revision`, `expires_at`, `can_submit`, `blockers`, `dispatch_owner="server"`.

Resolver pode reservar IDs e proposta durável, mas **não cria processo, turno ou outbox de efeito**. Repetir client_intent_id com mesmo conteúdo retorna a resolução; mudar conteúdo retorna `OPERATION_CONFLICT`. Resolution expirada exige nova resolução vinculada explicitamente, nunca executar dados aprovados sob outra revisão.

### 3.5. `OperationView`

Campos: `operation_id`, `client_intent_id`, `scope`, `action`, `intent_hash`, `admission_state`, `executor_stage`, `possible_effect`, `retry_safe`, `receipt_revision`, `last_observed_at`, `error`, `follow_up_operation_ids`.

`admission_state`: `RESOLVED`, `ACCEPTED`, `DISPATCH_PENDING`, `DISPATCHED`, `RECONCILING`, `RESOLVED_TERMINAL`. `executor_stage` é o estágio real do receipt Core, ou null antes de haver receipt. Não usar `SUCCEEDED` no estágio do executor só porque o POST teve 202.

### 3.6. `DecisionView`

Campos: `decision_id`, `client_intent_id`, `ApprovalKey`, `request_hash`, `request_revision`, `proposal_decision`, `native_decision`, `actor_agent_id`, `subject_agent_id`, `canonical_state`, `native_operation_id`, `native_stage`, `possible_effect`, `retry_safe`, `response_digest`, `expires_at`.

Estados canônicos: `PENDING`, `CONFIRMED`, `DENIED`, `EXPIRED`, `CANCELLED`. Aplicação nativa é outro fato: `NOT_DISPATCHED`, `DISPATCH_PENDING`, `SUBMITTED`, `APPLIED_OBSERVED`, `REFUSED_BEFORE_EFFECT`, `OUTCOME_UNKNOWN`. Somente observação explícita permite `APPLIED_OBSERVED`. Não devolver apenas `applied=true` como autorização suficiente.

## 4. Rotas HTTP — contrato fechado

Todas são novas ou adaptações a implementar; o Nexus inspecionado não implementa este conjunto `/v1`. A tabela fixa a responsabilidade; os exemplos/schemas de planejamento no pacote não são um SDK de produto publicado.

| Método e rota | Principal | Entrada principal | Saída e efeitos |
|---|---|---|---|
| GET `/v1/connections/protocol` | Público, sem dados privados | Nenhuma | 200 com management_revision, NXL aceito, formatos e limites; não enumera agentes/executores. |
| GET `/v1/connections/me` | Chave canônica | Header bearer | 200 identidade autenticada, permissões e revisões; lookup indexado. |
| POST `/v1/connections/executors:register` | Chave canônica | client_intent_id, connector_id, label aprovado, capabilities de controle declaradas | 200/201 executor_id canônico, bootstrap ticket limitado e estado; não cria agente ou binding privilegiado. |
| PUT `/v1/runtime/executors/{id}/inventory` | Ticket `inventory:publish` | ExecutorInventorySnapshot | 200 revision/sequence/validade aceitas; transação idempotente; 409 stale/conflict; nenhum spawn. |
| GET `/v1/runtime/executors/{id}/inventory` | Operador ou agente com vínculo autorizado | Cursor/revisão opcional | Snapshot filtrado e freshness; nada de paths; acesso de outro agente recusado. |
| POST `/v1/runtime/executors/{id}/inventory:refresh` | Operador ou agente autorizado | client_intent_id | 202 pedido de refresh ao executor; não faz scan remoto por conta própria. |
| POST `/v1/runtime/executors/{id}/realizations` | Ticket `realization:publish` | Prova de root local e candidato/revisão, refs de perfil sem secrets | 200/201 realization_ref canônica associada ao handle local; processo não inicia. |
| POST `/v1/connections/bindings:prepare` | Chave do agente ou operador autorizado | client_intent_id, executor_id, adapter_id, candidate_ref, inventory_revision, realization_ref, workspace_id/hint lógico, alias | 200 BindingProposal; 409 stale/ambiguidade; nenhuma concessão implícita. |
| POST `/v1/connections/bindings:apply` | Mesmo principal + prova de approval quando exigida | client_intent_id, proposal_id/revision, approved_diff_hash | 200 BindingView aplicado + revisões; CAS em endpoint/binding/profile; sem spawn. |
| GET `/v1/connections/bindings/{id}` | Sujeito ou operador | Escopo resolvido no Server | 200 estado e refs; não revela chaves/tokens. |
| POST `/v1/connections/bindings/{id}/ticket` | Chave do mesmo agente | client_intent_id, credential_request_id, audience e scopes pedidos | 200 ticket, ticket_id, expires_in, epochs e executor_id; intersectar política. |
| GET `/v1/agents/{agent_id}/runtime-options` | Próprio agente ou operador | executor_id obrigatório, workspace_id opcional | 200 catálogo/availability e can_prepare/can_bind/can_start + razões; não tem enum frontend. |
| POST `/v1/runtime/intents:resolve` | Agente/operador | client_intent_id, intenção, binding, workspace_binding, session quando existente, new_session, payload | 200 IntentResolution sem execução; 409 conflito/ambiguidade; guardar intenção antes de responder. |
| GET `/v1/runtime/intents/{client_intent_id}` | Mesmo ator+escopo | Consulta | 200 resolução e OperationView associado ou 404 consistente; não resolve nova intenção. |
| POST `/v1/runtime/operations` | Mesmo sujeito/operador | client_intent_id, operation_id, resolution_revision, intent_hash | 202 após commit de operação+outbox; 200 replay idêntico conhecido; 409 hash/revisão conflitante. Só este comando admite efeito. |
| GET `/v1/runtime/operations/{id}` | Próprio sujeito, ticket history escopado ou operador | Consulta | 200 OperationView/receipt; não exige runtime ou binário local. |
| POST `/v1/runtime/operations/{id}/receipts` | Ticket receipt:publish escopado | Receipt Core íntegro + source revision | 200 aceite durável ou 409 conflito; **não despacha** operação. Via WSS operation.receipt tem o mesmo caso de uso. |
| GET `/v1/runtime/sessions/{id}` | Sujeito/operador | executor_id se necessário | Estado composto; ausência de handle != STOPPED. |
| POST `/v1/runtime/sessions/{id}/capability` | Próprio agente com sessão/resolução válida ou operador representando | binding_id, audience MCP/nativa, actions pedidas, capability_request_id idempotente | 200 capability_ref, segredo uma vez/no-store, expires_in e audiência específica. `nexus-mcp-session` serve MCP HTTP; `nexus-native-session` serve somente as ações nativas não MCP. Nunca intercambiar tokens. |
| POST `/v1/runtime/approval-decisions` | Operador ou proof de operador escopado; chave do agente sozinha não basta em escalada | client_intent_id, ApprovalKey, expected_revision, request_hash, decision approve/deny, cas_token, response opcional | 202 DecisionView CONFIRMED e operação nativa na outbox; 200 replay da mesma decisão; 403/409 recusas. Não aplicar nativo na CLI. |
| GET `/v1/runtime/approval-decisions/{id}` | Ator autorizado/sujeito com leitura limitada | Consulta | 200 DecisionView; sem resposta sensível bruta. |
| POST `/v1/runtime/native-actions` | Capability `native-actions` limitada à sessão | action_id, scope, action context/claim/complete, payload tipado | Caso de uso canônico idempotente; sem MCP envelope, sem texto livre interpretado. |
| GET `/v1/runtime/executors/{id}/link` | Ticket link:connect | Upgrade WebSocket, subprotocolo nxl.v1 | Negociação R4 e registro de conexão; autenticação de WebSocket própria, sem fallback operador do middleware HTTP. |

**Resolução da diferença com o Connector atual:** `IntentResolution` do cliente passa a ler `scope` completo; `/approval-decisions` deixa de retornar bool como informação suficiente; `BindingProposal` incorpora executor, instalação e realização; CLI start/submit não chama Core diretamente; receipt usa a rota própria. Essas mudanças pertencem ao agente Connector e constam de `06_HANDOFF_CORE_CONNECTOR.md`. O Server não deve preservar o fluxo defeituoso duplicando efeitos.

### 4.0. Ações nativas de domínio e repetição durável

A audiência aceita em `POST /v1/runtime/native-actions` é exclusivamente
`nexus-native-session`, via bearer. Chave canônica, ticket NXL e capability MCP
não a substituem. Os verbos HTTP `context`, `claim`, `complete` correspondem
respectivamente às ações `handoff.get`, `handoff.claim`, `handoff.complete`
da bridge pública Core e do ceiling da capability. Não se exige `tools/call`.

Payloads fechados:

- `context`: `handoff_id`.
- `claim`: `handoff_id`, `idempotency_key` (1–128 caracteres) e
  `claim_epoch` opcional. O epoch fornecido somente permite reutilizar um
  claim ativo já pertencente à mesma sessão/escopo; não despacha outro runtime.
- `complete`: `handoff_id`, `claim_epoch` inteiro positivo e `result` JSON.

O `operation_id` do pedido tipado Core é o `action_id` HTTP. Escopo completo,
IDs e epoch são validados sem coerção. Request e resposta têm limite de
16 KiB; JSON duplicado/não finito e campos extras são recusados. Um resultado
de claim grande demais exige referência de artefato e não deixa o claim aplicado.

O registro durável do pedido e o efeito canônico fazem commit juntos.
Repetição do mesmo ID/conteúdo recupera a resposta original após revalidar
autoridade e acesso ao domínio. ID/conteúdo conflitantes retornam 409.
Reutilizar `idempotency_key` com outro `action_id` também retorna 409:
o caller deve recuperar o ID original. A resposta armazenada é um recibo
original; estado corrente é obtido por novo pedido de contexto. Mudança de
geração do claim impede recuperar dados da geração anterior.

MCP e ações nativas compartilham handoff, claim/epoch, permissões, visibilidade
e eventos; não há um domínio paralelo no Core/Connector. Perda da resposta
após efeito possível conserva `OUTCOME_UNKNOWN` e o ID original, sem retry
automático nem nova identidade. Segredos não são gravados no ledger e todas
as respostas da rota usam `Cache-Control: no-store`.

### 4.1. Exemplo de fluxo remoto sem ambiguidade

```text
Connector CLI: grava client_intent_id=ci_A no seu journal de comandos
POST intents:resolve(ci_A, runtime.start, binding_B)
Server: reserva session_S/op_OPEN; devolve resolução R1; nenhum processo
POST operations(ci_A, op_OPEN, R1, hash_H)
Server: commit canônico + outbox; 202
Server dispatcher → Connector: operation.submit(op_OPEN, runtime.open)
Connector: resolve instalação/realização local → solicita lease inicial
Server: lease.granted correlacionada
Connector/Core: prepare → open(op_OPEN, SessionKey S, contexto completo)
Connector → Server: receipt(op_OPEN) + eventos duráveis
Server: ingresso/ACK → OperationView
CLI: consulta ci_A/op_OPEN; não inicia outro runtime
```

Prompt fornecido no start produz `op_TURN` separado, com parent `op_OPEN`; o Server somente libera sua outbox após prontidão comprovada. Reuso devolve sessão compatível existente e não cria open adicional; `new_session=true` cria intenção distinta autorizada.

## 5. NXL R4 — delta obrigatório sobre r3

A fonte executável continua no Core. O arquivo `contratos/nxl-r4-delta.json` lista mudanças normativas para seu agente; não é permissão para manter uma segunda implementação no Server. O manifesto atual r3 tem status `development-partial`; preservar esse fato no baseline, sem confundir o campo histórico `core_version` do manifest com a versão atual da biblioteca.

### 5.1. Envelope e hash

Para efeitos, exigir todos os IDs/revisões de `ExecutionScope`, `connection_generation`, `operation_id`, `intent_hash`, `action`, `payload` e `grant_id`. `session_owner_generation` deixa de ser opcional. `grant_id` referencia uma autorização instalada via lease correlacionada; não é um bearer independente ou fonte de permissões autodeclaradas.

Usar o canonicalizador/hash público do Core para semântica. O intent inclui configuração e alvo; exclui ticket, número de envio, instante de lease e geração de conexão. Não alterar hashes históricos de R3. Se o delta mudar representação semântica, seu domínio/versão de hash deve ser distinguível; receipts R3 continuam interpretados pelo decoder R3 para história.

Cada verbo possui payload fechado, `additionalProperties=false` e limite 64 KiB:

| action | Payload exigido / restrições |
|---|---|
| runtime.open | adapter_id, candidate_ref, inventory_revision, realization_ref/revision, profile_revision, mode=managed, model opcional. Proibir executable/argv/env/path/target_pid remoto. |
| turn.submit | text, delivery_id opcional e referências autorizadas. Não incluir scripts de execução. |
| turn.steer | text; expected_turn_id quando o Core declara alvo nativo. Targeting sem ID somente se capability efetiva do Core permitir current-run; ausência não é licença para escolher qualquer turno. |
| turn.interrupt | Motivo limitado; target correlacionado conforme capacidade. Não fabricá-lo a partir do primeiro turno. |
| runtime.close | razão e política dentro dos limites aprovados; não PID nem sinal livre do cliente. |
| approval.decide | canonical_request_id, decisão accept/decline/cancel confirmada, proposta operacional íntegra, decision_id/revision, response_digest. |
| input.provide | Os campos correlacionados acima + resposta tipada ou ref autorizada entregue de forma protegida. Core valida pedido original e tipo; não usar prefixo da decisão para inferir input. |

Metadata de targeting deve ser publicada pelo Core; Server/UI não mantêm regra `if adapter == codex/pi` para autorizar. R4 permite representar explicitamente ausência de turno nativo, e os reducers recusam combinações incompatíveis antes da escrita.

### 5.2. Frames novos e alterados

| Frame | Alteração normativa |
|---|---|
| hello/welcome | Adicionar link_attempt_id/connection_id, revisão HTTP, formatos de snapshot aceitos e capacidades de controle efetivas; welcome não significa lanes/sessões READY. |
| binding.attach | Incluir attach_request_id, expected_connection_generation, configuração e token de tentativa. Ticket continua sensível. |
| **binding.attached** | Novo ACK do Server após validar ticket/escopo e registrar lane; devolve attach_request_id, connection_id/generation, agent/binding/epochs/revisions, expires_in. Só este ACK conclui attach; write no socket não conclui. |
| binding.detach | Exigir scope/canal e razão; fechar concessão em memória antes de I/O; não concede controle de outro agente. |
| reconcile.request/report | Incluir reconcile_id, connection_id/generation e páginas/cursosres. Reporta receipts, claims, stream watermarks e fatos de ownership separados. |
| **reconcile.accepted** | Novo ACK canônico do Server com reconcile_id, próxima recuperação pendente e readiness autorizada por sessão/lane. Falha de storage não é report vazio. |
| lease.renew | Adicionar request_id não reutilizável, grant_id, expected lease_serial, configuração/owner/conexão e finalidade initial/renew/reconnect; captura monotônico t0 no executor antes do envio. |
| lease.granted | Correlacionar request_id; devolver lease_serial crescente, grant_id, scope/revisões completos, allowed_actions, valid_for_ms <=120000. Emissor é o Server. |
| **lease.applied** | Novo recibo do executor de aplicação no Core, com request_id, serial e scope; para abertura inicial, indica contexto instalado antes do open. Não confundir com processo pronto. |
| operation.submit/receipt/query | Scope completo e schemas por verbo; query não autoriza reexecução. Receipt pode ser histórico e mantém hash original. |
| event.batch/event.ack | Acrescentar connection_id/generation ao envelope R4; evento mantém identidade independente de reconexão e sequence/epoch estáveis. ACK pós-commit contíguo. |
| approval.request | Notificação de pedido; separar proposta operacional íntegra de representação para UI. Scope completo, expiry, request_hash/revision e tipo administrativo/nativo. |
| approval.decision | **Somente notificação da decisão canônica. Não gera aplicação adicional.** Efeito nativo usa exatamente a operação approval.decide/input.provide já admitida. |
| inventory.snapshot/delta | Snapshot técnico completo utiliza HTTP versionado nesta revisão; frames NXL antigos servem apenas projeção reduzida/hints quando negociados. Não alojar campos extras de availability neles. |
| heartbeat | Atividade de canal apenas; não renova lease de trabalho. |
| error/goaway | códigos de incompatibilidade, capacidade, escopo, estado/erro tipado; nunca incluir ticket/hash de chave ou raw response de operador. |

### 5.3. Máquina de estados do canal

```text
DISCONNECTED → AUTHENTICATING → NEGOTIATING → RECONCILING
             → CONTROL_READY → DRAINING / DISCONNECTED
```

`CONTROL_READY` exige contrato válido, geração obtida por CAS, ingress journal disponível e reconcile aceito. Lane pode continuar `ATTACHING`; sessão pode continuar `LEASE_PENDING`. Server não despacha trabalho produtivo para lane/sessão não pronta. Exceção de bootstrap explicitamente delimitada: `runtime.open` pode ser entregue a uma lane ADMITTED com sessão `OPEN_AUTHORIZED_PENDING_LEASE`; esse comando permite apenas resolver a realização e solicitar a lease inicial. O Connector não chama prepare/open do Core nem produz spawn antes de instalar a concessão correlacionada e emitir lease.applied. turn.submit/steer e decisões permissivas continuam aguardando lease aplicada e readiness real. Essa exceção não concede prazo ou ações por default. No início de reconnect, invalidar serial de socket anterior antes de aceitar tráfego novo. Operação já admitida permanece consultável; não é automaticamente reenviada como efeito.

Lane: `PENDING → ATTACHING(token/epoch) → ADMITTED → FENCED/EXPIRED/DETACHED`. Rotação fecha a prova antiga em memória; task antiga tem token próprio; seu término agenda o estado desejado atual, mas não marca nova epoch como pronta. O Server aceita ticket atual e emite ACK da mesma tentativa. Expiração de ticket limita admissão/renovação; não matar todos os agentes por revogar um.

### 5.4. Lease sem relógios compartilhados

No executor, antes do request, capturar `t0 = monotonic()`. Server concede duração <=120000 ms baseada no tempo de emissão e em sua própria política/expiração. Executor aplica `deadline = t0 + valid_for_ms/1000`. Atraso de ida/volta consome orçamento; se resposta chegar tarde, recusar/renovar sem executar. Não transmitir timestamp monotônico entre máquinas. Server guarda sua própria validade; não compara diretamente clocks monotônicos de hosts diferentes.

Mapear request_id para t0 uma única vez; replay do mesmo grant reutiliza esse t0 e não estende deadline. Reboot perde o t0 e exige nova autorização. A serial da lease aumenta por concessão confirmada; mensagem antiga, owner diferente ou configuração divergente não altera contexto. Renovação/reconnect chama `Core.renew_lease(SessionKey, ExecutionContext, expected_connection_generation=...)` e aguarda sua evidência antes de tornar a sessão produtiva. Uma linha durável SUPERSEDED impede o contexto anterior; ela não contém permissões para importar automaticamente.

Contenção autorizada — interrupt, close e resposta estritamente negativa — preserva semântica do Core após lease produtiva vencer, mas não amplia `allowed_actions`. Shutdown interno proprietário é outra trilha, não `containment=true` enviado pelo peer.

## 6. Idempotência e resultados possíveis

### 6.1. Intenção HTTP

A chave de idempotência do comando é `(server_id, authenticated_actor, client_intent_id)`. Guardar digest do corpo semântico completo e escopo. Uma nova tentativa de transporte envia a mesma chave. Se ID existia com corpo diferente, 409 antes de operação/outbox. Cliente grava essa chave antes do POST; sem isso, a consulta após resposta perdida é impossível.

`GET intents/{client_intent_id}` resolve operation_id quando a resposta inicial se perdeu. Não retornar zero efeitos de um ReadTimeout/5xx genérico. O Server só marca `retry_safe=true` quando sua transição comprova que nada foi admitido/executado e explica qual ação pode ser repetida; autorização para novo ID é separada.

### 6.2. Outbox e execução

Uma linha outbox corresponde à operação, não à tentativa de socket. Reservar tentativa por CAS com deadline, sem I/O dentro da transação. Antes do efeito, revalidar contexto, revisão, lane e resolução. `POST receipts`/WSS receipt ingressa fatos sobre uma operação existente e hash igual; receipt estrangeiro ou sem admissão canônica vai para quarentena/erro, não cria trabalho retroativamente.

Quando send falha após possível entrega, marcar despacho para **consulta**, não retransmissão cega. Resposta Core idempotente permite obter receipt da operação; não requer novo turno. Novo efeito só se a semântica do Core comprovar não envio e houver nova intenção explicitamente autorizada conforme o contrato.

### 6.3. Eventos e ACKs

Chave: `(server_id, executor_id, session_id, stream_epoch, sequence)`. Server valida scope/canal, tamanho, continuidade e hash. Duplicata com mesmo conteúdo é idempotente; mesmo sequence com hash diferente é conflito. Gap não recebe watermark além da última sequência contígua persistida. Eventos posteriores podem ser guardados sob limite para recuperação, sem fabricar o trecho ausente.

ACK é produzido após COMMIT do ingresso. Quando o COMMIT falha, nenhum ACK. Quando COMMIT sucede e ACK se perde, retransmissão do evento é aceita sem repetir efeito ou projeção. UI offline não bloqueia ACK. Receiver, persistência e controle usam quotas/budgets diferentes; saturação de texto não ocupa toda capacidade de interrupt/revoke/ACK.

No Connector/Embedded bridge: `remote_acked_through` e `core_ack_applied_through` são distintos. A espera do lote fixa `target=batch[-1].sequence`; ACK1 satisfaz replay1 e não lote2. Erro ao aplicar ACK no Core conserva obrigação e retry coalescido; reconexão assegura task viva mesmo sem novo evento. Server não compacta dados críticos só porque foram enfileirados no frontend.

## 7. Aprovação — fluxo único, sem aplicação dupla

### 7.1. Ingresso

Evento nativo autenticado contém a proposta que o Core já correlacionou. O Server guarda uma cópia operacional imutável, valida campos e seu request_hash, e produz uma cópia de apresentação redigida. Hash/digests de correlação não são credenciais; redaction de secrets não pode substituir o hash operacional por `[redacted]`.

Scope completo: Server/executor/binding/agente/workspace/sessão/owner/turno/request nativo + canonical_request_id. Receber mesmo pedido de outra execução não sobrescreve o original. Native IDs de dois Servers/sessões podem coincidir sem colisão.

### 7.2. Decisão e aplicação

1. UI ou CLI envia proposta `approve`/`deny`, client_intent_id, CAS/revision e proof do operador existente.
2. Server valida autoridade humana exigida, pedido vigente, scope/hash/turno e capacidade. Chave do agente que transporta a proposta não concede autoridade de aprovador.
3. Em UMA transação, confirmar decisão canônica, criar operation_id de aplicação e outbox, com vínculo ao pedido.
4. Responder 202/DecisionView. A aplicação nativa ainda pode estar pendente.
5. Dispatcher envia somente a operação canônica `approval.decide` ou `input.provide`. Traduzir approve→accept, deny→decline/cancel conforme tipo validado; não inferir ação por `startswith`.
6. Connector valida namespace, obtém SessionKey exata e chama Core com argumentos nomeados. Proposta operacional não passa pelo redactor de UI.
7. Receipt entra no mesmo ingresso de operação. Core SUBMITTED não comprova que provider agiu. UI mostra fatos distintos.

`approval.decision` de notificação não aplica novamente. A rota HTTP não devolve um bool para instruir a CLI a chamar o Core por fora. Esse é o ajuste coordenado que elimina a ordem/ownership híbridos das revisões anteriores.

### 7.3. Cancelamento, segredo de input e recuperação

Cancelar o request HTTP não cancela transação/producer já admitido. Repetir client_intent_id consulta DecisionView. Duas interfaces com decisões diferentes disputam CAS; só uma confirma. Uma decisão confirmada não volta a PENDING por erro da aplicação nativa.

Não persistir resposta sensível de input em logs ou no journal técnico; guardar digest e referência no domínio. Para este escopo, a resposta bruta é mantida somente em memória protegida do produtor, com TTL do pedido. Se houver crash antes de entrega e nenhum store sensível persistente qualificado estiver configurado, reportar `AUTHORIZED_INPUT_UNAVAILABLE`: exigir fornecimento explícito do mesmo conteúdo/novo fluxo autorizado, sem inventar input nem declarar recuperação automática pós-crash. Isso é um limite explícito; não criar um serviço de segredos novo como dependência implícita. Resultado de possível escrita continua consultado pelo receipt Core, não reenviado.

Um pedido administrativo sem sessão gerenciada termina no CAS do domínio. Marcar esse tipo explicitamente no registro; sessão nativa ausente não é motivo para convertê-lo em administrativo silenciosamente.

## 8. Erros e códigos de status

401: identidade/ticket/capability inválida. 403: scope/ação/autoridade negada. 404: recurso inexistente após autorização de leitura. 409: ID/hash conflitante, CAS obsoleto, inventário stale, ambiguidade. 422: corpo/tipo/forma inválida antes da admissão. 429: capacidade não disponível antes de aceitar, com retry policy. 503: dependência indisponível; não afirmar ausência de efeito se a operação já foi admitida. 202: operação durável consultável, não sucesso nativo.

Erros novos de aplicativo: `INVENTORY_STALE`, `INSTALLATION_REF_NOT_FOUND`, `INSTALLATION_REF_AMBIGUOUS`, `LANE_NOT_READY`, `EXECUTOR_NOT_READY`, `RECONCILIATION_REQUIRED`, `APPROVAL_AUTHORITY_REQUIRED`, `AUTHORIZED_INPUT_UNAVAILABLE`, `DISPATCH_OWNER_MISMATCH`. Acrescentar ao bundle quando atravessarem NXL; não converter todos em UNKNOWN. Preservar CoreError `possible_effect/retry_safe/stage/operation_id` e manter mensagem de diagnóstico separada do código.

## 9. Interfaces existentes versus alvo

| Ponto | Existente observado | Alvo decidido |
|---|---|---|
| HTTP Server | `/api/v1`, envelope `ok/data` | Preservado; novo `/v1` direto tem handler separado e caso de uso comum. |
| HTTP Connector | `/v1`, DTOs parciais e bool para approval | Atualizar para DTOs R4 completos e consulta idempotente. |
| Native runtime local | Server contém classes próprias | Core público no EmbeddedExecutor. |
| Remote runtime.open | Enumerado no schema r3, ainda indisponível no Connector | Payload/lease/realização fechados e dispatcher Server único. |
| Catálogo | Core API publicada | Consumir exatamente; UI sem lista paralela. |
| Snapshot | Availability v2 existe; publicação ainda não qualificada | HTTP snapshot R4 com scope, revisão completa e TTL. |
| Lane ready | Write de attach tratado como prontidão em partes do Connector | ACK binding.attached explícito e token/revisão corrente. |
| Reconcile | r3 report limitado | Páginas/ACK/correlation e histórico sem provider. |
| MCP | HTTP existente + stdio ainda no código do Nexus | HTTP preservado; stdio removido sem shim. |

Tudo nessa coluna “Alvo” é trabalho especificado, não capacidade já testada entre os produtos.
