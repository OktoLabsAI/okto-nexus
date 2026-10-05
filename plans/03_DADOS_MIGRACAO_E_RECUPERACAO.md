# Dados, migração, lifecycle e recuperação

**Status: desenho R4 a implementar.** Manter o SQLite e os repositórios do Nexus. Este documento não autoriza executar SQL em base do usuário, apagar estado incerto ou reiniciar processos reais durante o planejamento.

## 1. Duas persistências, fatos diferentes

O **banco canônico do Server** guarda agentes, permissões, workspaces, endpoints, handoffs, decisão de execução, outbox e ingresso durável dos fatos remotos/locais. O **journal técnico do Core** guarda admissão do executor, possíveis efeitos nativos, receipts, eventos, claims de sessão, fences e slots.

No executor local, ambos podem estar na mesma máquina, mas não devem ser confundidos. Decisão de domínio não é atomicamente transacional com spawn/write; uma transação SQL não pode envolver espera de subprocesso ou socket. O ledger do Core impõe limite físico compartilhado às instâncias daquela instalação, inclusive quando o Server compõe um Core por sessão.

Escolha desta revisão: banco canônico existente + um journal Core compartilhado do executor local + um ledger Core de instalação. Usar implementações públicas Core; não copiar SQL do journal nem reimplementá-lo no Nexus nesta rodada. O adapter `core_history.py` consulta esse journal sem candidatos/factory para recuperar recibos depois de restart.

## 2. Entidades existentes preservadas

Foi confirmada a existência de `agent_endpoints`, `runtime_profiles`, `runtime_boot_bindings`, `runtime_execution_grants`, `runtime_open_requests`, `runtime_access_audit` e `delivery_outbox` nos arquivos examinados. O executor deve registrar o schema completo real antes das migrações, inclusive tabelas de sessões/handoff/claims não integralmente lidas nesta elaboração.

Regras fechadas:

* `agents`, chaves hash-only, permissões, IDs e mensagens não são recriados.
* `agent_endpoints` permanece autoridade de política do endpoint: enabled, activation_state, consumption, response_policy, priority e seleção aprovada. Não duplicar flags contraditórias em uma tabela nova.
* `runtime_profiles` permanece autoridade da configuração aprovada; dados nativos de lançamento passam a ser produzidos pelo Core, não campos livres de command/argv.
* `delivery_outbox` continua a fila canônica da entrega lógica e sua causalidade. A nova outbox de despacho abaixo transporta a operação referenciada; não cria segunda entrega/inbox.
* `runtime_open_requests` legado continua consultável. Novas operações têm contrato R4; a migração registra vínculo com a requisição anterior, sem recalcular seu hash.
* Binding remoto não recebe `root_realpath` calculado no Server. Dados históricos locais continuam mantidos para compatibilidade.

## 3. Extensões canônicas

Nomes-alvo abaixo fixados para a implementação. Se já existir tabela equivalente no HEAD posterior, reutilizá-la por migração de colunas e registrar o crosswalk; não criar duplicata. Ausência/diferença deve ser diagnosticada antes de aplicar, não resolvida com `DROP TABLE`.

| Tabela/conceito | Campos mínimos e chave | Invariante / índices |
|---|---|---|
| `execution_installation` | singleton com server_id, embedded_executor_id, schema_revision | Identidade da instalação persistida, não derivada do host a cada boot. |
| `execution_executors` | PK `(server_id,executor_id)`; connector_id, kind embedded/remote, label, control_state, generation, owner_instance_id, last_seen, revoked_at | UNIQUE `(server_id,kind,connector_id)` para remoto; índice por state/last_seen; sem user_id ou master key. |
| `execution_bindings` | PK `(server_id,binding_id)`; executor_id, endpoint_id UNIQUE no Server, workspace_binding_id, candidate_ref, inventory_revision, realization_ref/revision, binding_revision | FK endpoint existente; agente/adaptador/workspace são resolvidos e comparados com endpoint, não valores autônomos que podem divergir. |
| `execution_workspace_bindings` | PK `(server_id,workspace_binding_id)`; executor_id, workspace_id, realization_handle, revision, local_label aprovado, status | Handle opaco no remoto; root físico em registro local apenas. Índice executor/workspace. |
| `execution_realizations` | PK `(server_id,executor_id,realization_ref)`; local_realization_ref, subject_agent_id, workspace_binding_id, candidate_ref, inventory_revision, configuration_digest, local_root_proof_digest, revision/status | UNIQUE executor/local_realization_ref/revision; mapeamento canônico→handle opaco do executor, sem path remoto resolvido. |
| `execution_inventory_snapshots` | PK `(server_id,executor_id,publication_sequence)`; revision, formatos, core_version, canonical_projection, received_at, age, producer_instance_id | UNIQUE executor/sequence; digest igual não autoriza retroceder sequence; projeção sem paths/secrets. |
| `execution_inventory_current` | PK `(server_id,executor_id)`; sequence/revision atuais | Ponteiro atualizado por CAS após validar snapshot completo; guardar últimas duas revisões para diagnóstico, não histórico ilimitado. |
| `execution_proposals` | proposal_id PK no Server; client_intent_id, actor, subject, escopo, revisões esperadas, diff_hash, expires_at, status | Proposta não autoriza spawn; idempotência por ator/client_intent_id. |
| `execution_client_intents` | PK `(server_id,actor_agent_id,client_intent_id)`; body_hash, intent_id, operation_id, resolution_revision, resolved_json, created_at | Mesmo ID/corpo devolve resultado; corpo diferente conflita. Não depender do primeiro HTTP response para saber o ID. |
| `execution_operations` | PK `(server_id,executor_id,operation_id)`; subject_agent_id, actor_agent_id, binding/workspace/session, action, intent_hash, semantic_payload, expected revisions, decision/delivery parent, admission_state | Imutável quanto à semântica após admissão; índice subject/workspace/status. Payload sensível é ref/digest, não texto de input em logs. |
| `execution_dispatch_outbox` | PK FK da operação; dispatch_state, attempt_token, attempt_no, connection_generation, lease_id/serial, next_attempt_at, last_error, last_receipt_revision | Um item por operação; query/reconcile para unknown, não resend cego. Índices pendente/executor e next_attempt. |
| `execution_receipts` | PK operação + receipt_revision; intent_hash, stage, possible_effect, retry_safe, native_id, error_code, received_at | Receipt de hash/scope diferente não é anexado à operação. Projeção reduzida mantém última revisão. |
| `execution_sessions` | PK `(server_id,executor_id,session_id)`; binding/workspace, open_operation_id UNIQUE por scope, core_owner_ref, owner_generation, estado/prova, stream_epoch, lease state, legacy_session_id quando houver | É a projeção de execução governada. Sessão lógica preexistente conserva seu ID e ligação; não criar novo Agent nem substituir histórico. |
| `execution_leases` | PK sessão + lease_serial; grant_id, allowed_actions_json, auth/config/owner/connection/credential epochs, valid_until_server, request_id, status | Prazo do Server independente do monotônico do executor; revogada não volta a ativa por replay. Índices expiração/subject. |
| `execution_link_tickets` | ticket_id PK; hash único, scope, audiences/scopes, epochs, expires_at, bound_connection_id, revoked_at | Nunca plaintext. Binding ticket não concede todas as lanes. |
| `execution_session_capabilities` | capability_id PK; hash, audiência MCP ou native-actions, sessão/subject/actions/validity/revocation | Segredo retornado uma vez/no-store; token não vai em URL/argv. |
| `execution_event_ingress` | PK `(server_id,executor_id,session_id,stream_epoch,sequence)`; event_hash, tipo, payload operacional íntegro validado, received_at | Duplicata mesmo hash idempotente; hash divergente conflito; limites de tamanho e retenção. |
| `execution_event_watermarks` | PK StreamKey; committed_contiguous, projected_through, gap state | ACK deriva exclusivamente de committed_contiguous. UI/SSE não altera esse campo. |
| `execution_decisions` | decision_id PK; ApprovalKey único + revision; proposta íntegra/digest, ator/sujeito, decisão, canonical state, native_operation_id, response_digest/ref, expiry | CAS para decisão única; resultado nativo é receipt separado. Raw hash operacional não passa por redaction. |
| `execution_migration_map` | PK fonte/tipo/legacy_id; canonical_ref, row_digest_before, migration_batch_id, state | Retomada/backfill auditável; preservar IDs e hashes antigos. |

Campos de revisão são inteiros >=1, exceto serial esperado zero na primeira concessão. Guardar datas canônicas de auditoria UTC; timers ativos são monotônicos de processo e não sobrevivem ao boot por restauração numérica. Schema de JSON é validado na escrita e na fronteira; não confiar em payload porque veio do próprio banco legado.

**Escolha de reaproveitamento:** endpoint e binding são relação 1:1 por `endpoint_id`, não duas políticas. `execution_sessions` é projeção do executor e liga a sessão lógica/harness legada pelo campo de referência. O executor registra a tabela de sessão legada efetiva no manifesto da migração; os campos novos não podem substituir silenciosamente `session_secret` da identidade existente.

## 4. Transações exatas

### T1 — Apply de binding

Validar principal, proposta, hashes/revisões, snapshot ainda vigente e realização aprovada. Abrir UoW; confirmar revisões atuais; criar/atualizar endpoint/profile e binding extension; registrar auditoria e mapa legado; commit. Somente depois responder. Se a confirmação se perde, reusar client_intent_id e consultar a mesma proposta aplicada. Nada de enviar ticket ou criar processo dentro da transação.

### T2 — Admissão de operação

Verificar resolução e hash; UoW adquire idempotência; confirma políticas/subject/realização/configuração; cria operation e dispatch_outbox na mesma transação e reserva o claim lógico quando aplicável; commit; responder 202. O dispatcher adquire attempt_token por CAS em outra transação curta e faz I/O depois. Worker revalida o token e a autorização depois de fila/espera.

### T3 — Evento/ACK

Validar namespace contra canal e semântica do frame; UoW insere eventos inéditos, compara hashes dos duplicados e avança somente watermark contíguo; commit; ACK. Reducer/projeção é idempotente e pode ocorrer nessa transação para fatos pequenos ou depois via offset persistido; nenhum ACK espera o frontend. Gap/lote não contíguo preserva último limite comprovado.

### T4 — Decisão

Validar operador e pedido íntegro; UoW CAS de revision e estado PENDING; grava decisão, client intent, operation de aplicação e outbox; commit. Request HTTP interrompido não desfaz o commit nem cancela o produtor. A confirmação perdida é consultada por client_intent_id. Input bruto sem armazenamento sensível persistente tem a limitação declarada no contrato.

### T5 — Revogação/rotação

Após autorização, bloquear concessões em memória na seção curta pertencente ao agente/binding. UoW altera epoch/revision e derivados; commit; invalida cache, lanes, capabilities e concessões do Server; envia controles/revokes fora do UoW. Se commit ficar incerto, manter bloqueio conservador e reconciliar; não reabrir com um bool. Na partição, validade local do executor é limite real, não promessa de revogação instantânea remota.

## 5. Migração em etapas, sem reset

### M0 — Pré-condições e backup

Registrar schema/user_version/migration log reais, conteagens de agentes/keys/workspaces/mensagens/claims/handoffs/endpoints/sessões/outbox, índices e negações. Gerar backup consistente pelo mecanismo SQLite de backup ou aplicativo parado; nunca copiar somente o arquivo principal com WAL ativo. O número da migration SQL é o próximo número livre encontrado no runner, registrado no manifesto; não fixar um número que possa colidir com trabalho posterior.

### M1 — Expansão aditiva

Criar extensões e índices, mantendo leitores legados. Preservar checks e FKs. Não alterar as permissões por default: endpoint desabilitado continua desabilitado, método negado continua negado. Criar embedded_executor canônico para a instalação, mas não abrir processos por fazer backfill.

### M2 — Tradução do catálogo legado

Somente para dados históricos e migração, manter tabela fechada:

| ID do Server legado | ID Core |
|---|---|
| `codex` | `codex_app_server` |
| `pi` | `pi_rpc` |
| `claude_code.stream` | `claude_stream` |
| `claude_code.attach` | `claude_attach` |
| `mcp` | tools-only/MCP HTTP; não é adapter de processo |

Essa tabela não é um catálogo novo. IDs não conhecidos não recebem fallback; marcar `MIGRATION_REVIEW_REQUIRED`. Remover a tabela do hot path após migração concluída, conservando tradução read-only de histórico. Não substituir nomes dentro de hashes/receipts antigos.

### M3 — Endpoints e workspaces

Associar endpoints locais antigos ao embedded_executor e criar linkage de binding. Paths antigos são validados localmente pelo Core para uma nova realização; não transformar command strings livres em argv autorizados. Campo legacy ID permanece. Novo candidato não observado vira `REDISCOVERY_REQUIRED`, não arquitetura/versão inventada. Profile amplo/hook/home herdado exige consentimento definido, sem ligar bypass de permissions.

Workspaces baseados em path mantêm IDs. Novo workspace remoto recebe ID opaco Server + handle do executor, com associação explícita ao lógico existente quando o agente/operador tem permissão. Git remote, nome do diretório ou igualdade textual de path não mesclam workspaces.

### M4 — Sessões em curso e cutover

Não migrar processo vivo de supervisor antigo para Core por copiar PID. Antes do cutover, colocar admissões antigas em drain, preservar readers/queries, aguardar ou encerrar pelo owner antigo com evidência. Unknown continua identificado; não lançar substituto para “completar migração”. Bindings migrados só são ativados no novo caminho depois de resolução. Arquivos HOME/config ativos não são movidos.

Migrar o mapa de operações e histórico sem alterar IDs/hashes. Quando um receipt histórico não pode ser representado integralmente no R4, manter a consulta legada e uma referência de origem, sem inventar estágio novo. Replay mutável de operação legada não acontece automaticamente.

### M5 — Remoção de MCP stdio e duplicação

Extrair antes o bootstrap/Deps e o registro compartilhado de ferramentas. Remover só a implementação do transporte stdio, o ramo de execução, exemplos command/args e testes que exigem esse transporte. A CLI principal passa a módulo neutro; sem argumentos mostra help e código de saída definido, não inicia stdio. `serve` continua HTTP.

Migrar somente configurações MCP Nexus explicitamente escolhidas, com backup/diff/CAS, preservando agent key e entradas alheias. Não inserir comando shim stdio→HTTP. Remover adapters nativos do Server depois de seus consumidores dependerem do Core e de paridade delimitada; até lá wrappers finos não contêm parsing/spawn próprio.

### M6 — Verificação e rollback

Comparar conteagens e digests dos dados preservados; repetir migrations; injetar falha entre batches e retomar. Antes de novo efeito R4, rollback de aplicação pode usar expansão compatível. Depois de efeitos remotos/R4, requer drain/reconcile e versão capaz de ler dados novos. Não apagar journal/outbox nem reativar stdio como fallback. Restore é operação explícita do operador, não corretor automático.

## 6. Startup e recuperação sem binários

Ordem do owner `serve`:

1. Lock de instalação/owner existente; configuração válida; migrações canônicas concluídas.
2. Inicializar auth, registro técnico e readers públicos. Servir health com readiness ainda RECOVERING.
3. Abrir journal/ledger Core do executor local fora do loop bloqueante; leitura de claims/receipts/leases/slots paginada.
4. Reconstituir projeções e obrigações, **não handles vivos**. Birth record é histórico e não direito de sinalizar PID.
5. Retomar ingresso/outbox em modo consulta para resultados incertos. Nenhum prompt é reenviado por haver linha pendente.
6. Negociar executores remotos por ticket, geração e reconcile; snapshots devem ser refrescados.
7. Habilitar novas admissões somente para bindings/sessões reconciliados e autorizados. Falha em um provider local não derruba APIs nem executores remotos independentes.

`GET operation/intents/decisions` e scans de reconciliação funcionam sem `candidate_for`, sem provider instalado e sem chamar `prepare`. Usar `Journal.get_receipt`, `claimed_sessions`, `get_session_lease`, `get_process_birth` e APIs públicas correspondentes. Para batch, respeitar limite real do Core: até 256 IDs por reconcile e páginas de claims/slots até 4096; default 128. Não usar scan ilimitado nem SQL paralelo no handler.

## 7. Ownership dos producers

Cada operação em voo possui registro com owner token, task/Future produtor, waiter(s), resultado conhecido e obrigação durável. O socket/HTTP/CLI não possui o producer. `asyncio.wait_for(gather(...))` sobre producers possuídos é proibido quando o cancelamento do waiter abandonaria uma thread/commit; separar observers descartáveis de operações que ainda podem produzir efeito.

Casos obrigatórios:

| Caso | O que conservar | O que não concluir |
|---|---|---|
| Open iniciado, chamador cancelado | Tentativa, guard, Future e slot | Cancelamento não prova que não houve spawn. |
| Handle retorna depois do shutdown | Owner forte antes de qualquer await; coordenador Core | Não descartar porque cliente já saiu. |
| Close/observe bloqueado | Força com capacidade independente | Não esperar cancelamento de close para despachar força. |
| Force em thread ainda ativa | Future físico e coalescência | Coroutine cancelada não autoriza outra força simultânea. |
| STOPPED observado, release falhou | Prova de parada + obrigação leve de release | Não omitir a obrigação nem exigir nova força. |
| Decisão Server confirmada, Core incerto | Pedido, decision_id, operação e receipt | Não restaurar pending para outro approve. |
| ACK Server recebido, ACK Core falhou | Watermark remoto e pendência de aplicar | Não repetir trabalho do agente. |

Essas garantias são consumidas do Core, não reimplementadas no Server. O host deve preservar sua vida útil e o acesso aos stores necessários.

## 8. Shutdown do Server

`serve` possui o executor embutido. Ao iniciar shutdown, marcar draining e fechar novos starts/submits em memória; permitir consultas, controle autorizado e ingresso final de eventos. Agendar controles de todos os recursos locais em paralelo sob quotas. Política inicial: 30 s drain + 15 s de interrupção + 5 s de espera/relatório; orçamento de resposta total 50 s, configurável e medido uma vez por shutdown, não multiplicado por sessão.

Chamar Core.shutdown por instância sem serializar tudo atrás do POST/release de outra. Não excluir instância com unknown nem fechar journal/ledger enquanto houver producer que possa usá-los. Resultado por SessionKey deve separar processo desconhecido e somente liberação durável pendente.

**Decisão de produto nesta revisão:** se restarem recursos locais sem prova de parada/transferência, permanecer em `DRAINING_PENDING`, conservar o supervisor e disponibilizar health/consulta administrativa de recuperação. O comando retorna relatório pendente; não fazer `sys.exit(1)` como se isso conservasse o loop. Saída forçada do processo é operação administrativa explícita, com limite de contenção do SO documentado e qualificado. SIGKILL não passa pelo caminho gracioso; não prometer guarantees sem guardian/back-end qualificado.

Parar Server não mata imediatamente processos remotos: fecha novas concessões e deixa o Connector aplicar o prazo já autorizado. Se for desejado parar remotamente antes de sair, usar operações canônicas de close e relatar confirmação/unknown; não confundir desconexão WSS com morte física.

## 9. Quotas, controle e observabilidade

Defaults de planejamento, sujeitos aos testes de carga antes de anúncio de capacidade:

| Recurso | Limite inicial |
|---|---|
| Frame NXL | 1 MiB; texto por chunk até 64 KiB |
| Operação inline | 64 KiB; pedido/input nativo até o limite Core de 16 KiB |
| Pendentes produtivos por executor | 32; admissão antes de criar task |
| Controle reservado por executor | 8 itens + orçamento próprio de bytes |
| Runtimes por instalação | Ledger Core: 8 por default, compartilhado |
| Journal Core | 256 MiB lógico, reserva crítica 16 MiB |
| Snapshot técnico | 128 instalações por publicação inicial; coleção maior exige paginação/manifest acordado antes de habilitar |
| Heartbeat / ausência de canal | 15 s / 45 s; não lease de execução |
| Lease / renovação | Até 120 s / 30 s; duração consome RTT |
| Ticket | Até 600 s, renovar a 70% com jitter |
| Cache positivo de chaves | Até 4096 entradas; TTL máximo 60 s + invalidação de epoch |
| Backoff recuperável | 0,5–30 s com jitter e uma task por obrigação/stream |

Quota em itens e bytes é reservada em token que guarda custo exato. Liberação é idempotente pelo token, sem recalcular outro JSON. Reader valida/encaminha em fila limitada e continua recebendo controles; não cria milhares de tasks que esperam semáforo. Nenhum retorno de enqueue=false é tratado como sucesso.

Cenário de 100 mil agentes mede lookup por chave, paginação, memória e latência sem providers. Não significa 100 mil runtimes simultâneos. Não alocar lane/thread por agente offline. Métricas não usam session_id/agent_id como labels ilimitados. Logs escopados preservam IDs/digests operacionais e redigem secrets; UI recebe só o necessário ao principal.

## 10. UI e CLI — critérios concretos

**Tela do agente:** manter identidade e permissions; separar aba “Ferramentas MCP HTTP” de “Runtimes gerenciados”. Retirar TTL técnico/connection-key manual do caminho normal. Host remoto oferece comando protegido; host local não oferece instalação de Connector como pré-condição.

**Seletor:** executor primeiro, instalação depois. Renderizar `label/display_name/state/reasons` do snapshot; estado OFFLINE/STALE aplica overlay, sem modificar o fato técnico histórico. Duas cópias iguais continuam duas escolhas. Atualização do inventário invalida o formulário pendente e exige refresh; não escolher a primeira após reorder.

**Aprovação:** mostrar ator requerido, agente-alvo, host, projeto, tipo de operação, escopo/diff, validade e estados canônico/nativo separados. Depois de confirmar, acompanhar decision_id; timeout não apresenta outro botão que envia nova intenção automaticamente. Pedido de outra sessão/Server não é resolvido pelo rótulo.

**Runtime:** estados distintos para binding aprovado, transporte pronto, instalação pronta, starting, ready, running, waiting input, draining, unknown e stopped/release pending. Botões derivam capacidades efetivas, não enum TypeScript. Interromper turno não é parar processo. O fim do turno não mostra handoff concluído automaticamente.

**CLI:** `runtime discover/start/status/interrupt/stop/logs/doctor/bindings`, com `--json` e `--non-interactive`. Sem parâmetros mostra ajuda; stdin não inicia MCP. Headless exige escolha inequívoca ou erro com alternativas; não autoaprova nem pergunta secret no argv. ID de intenção fica disponível mesmo no timeout. Follower de logs pode encerrar sem parar runtime.

Testar UI com API real de laboratório, não apenas JSON copiado: duas instalações byte-idênticas, executor remoto de outra plataforma, atualização com mesma versão, snapshot stale, revogação entre seleção e apply, timeout de operation, duplicate approval e ausência de provider local no Server.
