# Matriz de testes e critérios de aceite

Todos os casos abaixo estão **planejados, não executados**. `05_BACKLOG.json` contém os mesmos IDs para rastreabilidade. Os nomes de estados são lógicos e devem ser mapeados para o contrato implementado.

## Estratégia

Usar testes unitários de domínio, integração com SQLite real em diretórios temporários, testes black-box por MCP/REST/serve, processos sintéticos de protocolo e testes com binários reais. Fakes verificam invariantes do Nexus; só os casos nativos demonstram suporte real do protocolo.

Testes de concorrência devem usar barreiras/events/clock injetável, não depender apenas de sleeps frágeis. Stress real complementa os testes determinísticos. Sempre que um defeito envolver composição, repetir ao menos uma reprodução através da composição efetiva de produção.

Não é suficiente afirmar “a contagem de mensagens parou”: observar o mecanismo que bloqueou/reconciliou, o estado durável e os efeitos que não aconteceram. Denials precisam provar zero spawn/write; dedupe precisa provar um efeito, não apenas uma resposta idêntica.

Cada gate deve verificar feature ON e OFF conforme aplicável. Protocolo/credencial/ambiente indisponível é NOT_RUN, e não PASS ou N/A.

## ID — Identidade e perfis

Fases: P01, P02, P03.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-ID-01 | Perfil preservado | Abrir, fechar e reabrir conexão com capabilities, metadata, role, tags, permissions e comm_scope existentes. | Todos os campos canônicos permanecem idênticos; apenas dados de conexão/presença mudam. |
| T-ID-02 | Agente inexistente | Abrir harness para agent_id não cadastrado por MCP e REST. | Erro prescritivo antes de spawn; nenhum Agent é criado implicitamente. |
| T-ID-03 | Abertura concorrente | Duas aberturas autorizadas para o mesmo agente, incluindo a mesma idempotency key. | Pedidos distintos criam bindings válidos; pedido repetido não duplica processo/sessão nem altera perfil. |
| T-ID-04 | Metadata legada | Passar role/metadata antigos, incluindo JSON em string e campos conflitantes. | Normalização/depreciação explícita; nenhum descarte silencioso ou profile overwrite. |
| T-ID-05 | Catálogo de habilidades | Usar capabilities existentes e desconhecidas pelas superfícies canônicas. | Validação de catálogo preservada; abrir conexão não contorna nem apaga catálogo. |
| T-ID-06 | Falha de start | Handshake, persistência ou validação de sessão falham depois do spawn. | Sem identidade fantasma; processo próprio reconciliado e nenhum estado RUNNING inventado. |

## AUTH — Autenticação, autorização e segredos

Fases: P01, P04, P11.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-AUTH-01 | MCP versus REST | Mesmo ator tenta abrir/enviar/steer/interrupt/close no mesmo recurso em ambas as superfícies. | Mesma decisão canônica, com zero efeitos externos nos casos negados. |
| T-AUTH-02 | Sessão alheia | Agente autenticado conhece session_id de outro agente e tenta controlá-lo. | Negação opaca e auditada, sem controle por conhecimento do ID. |
| T-AUTH-03 | Leitura alheia | Tentar replay, get, endpoint listing e resultados fora da audiência. | Nenhum payload, path, backend privado ou existência indevida é exposto. |
| T-AUTH-04 | Grant válido | Delegação estreita autoriza uma ação específica em workspace/endpoint/handoff. | Ação permitida funciona; ações e recursos adjacentes continuam negados. |
| T-AUTH-05 | Revogação antes do envio | Enfileirar comando autorizado, revogar grant/policy antes de dispatch. | Nova validação impede envio; intenção tem estado/motivo explícito. |
| T-AUTH-06 | Revogação após aceitação | Revogar grant durante turno e receber resultado final. | Evidência histórica é preservada; novos comandos/transições/publicações respeitam autoridade atual. |
| T-AUTH-07 | Impersonação no payload | Forjar actor/from_agent/grant/root no corpo ou num native event. | Identidade autoritativa vem do contexto e correlação confiáveis, não desses campos. |
| T-AUTH-08 | Stdio sem identidade | Chamar controles novos no modo stdio legado sem contexto verificável. | Não vira operador implicitamente; configuração local confiável habilita só o escopo previsto. |
| T-AUTH-09 | Segredos de backend | Fornecer secrets em env/refs e inspecionar respostas, logs, journal e erros. | Secrets não aparecem; perfil efetivo redigido continua diagnosticável. |
| T-AUTH-10 | Bypass por opções nativas | Tentar mudar cwd/sandbox/provider/env/argv fora do perfil aprovado. | Negação antes de spawn/write; adapter não aceita passthrough genérico. |
| T-AUTH-11 | EPT e caminho de monitoração | Usar credencial read-only/monitor para novos controles de runtime. | Escopo read-only preservado; nenhum upgrade de autoridade. |
| T-AUTH-12 | Idempotência não vaza dados | Ator diferente reutiliza chave/operation_id de request existente. | Autorização acontece antes de retornar o resultado persistido. |

## ENDP — Bindings e capacidades

Fases: P02, P03, P05, P07.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-ENDP-01 | Duas conexões, uma entrega | Mesmo Agent possui dois endpoints executores elegíveis. | A policy escolhe um binding; não ocorre fan-out executor dentro do Agent. |
| T-ENDP-02 | Dois workspaces | Mesmo Agent possui runtimes em projetos diferentes. | A execução usa o workspace/contexto autorizado da solicitação. |
| T-ENDP-03 | Continuação fixada | Enviar conversa e depois steer/interrupt enquanto muda a prioridade dos endpoints. | Controle continua vinculado à sessão/turno original, ou falha claramente. |
| T-ENDP-04 | Binding ambíguo | Duas sessões não intercambiáveis sem default ou seletor explícito. | AMBIGUOUS_BINDING; não usa a primeira entrada da registry. |
| T-ENDP-05 | Fallback seguro | Endpoint A falha antes de qualquer envio e B é fallback aprovado. | Uma tentativa em B, mesma operação lógica, seleção/auditoria consistentes. |
| T-ENDP-06 | Fallback inseguro | A pode ter aceitado; B está disponível. | B não executa automaticamente; operação permanece reconciliável/unknown. |
| T-ENDP-07 | Capabilities efetivas | Descriptor anuncia operação que a versão/configuração real não suporta. | Operação indisponível com motivo; não é enviada na esperança de funcionar. |
| T-ENDP-08 | Extensão adicional | Registrar um quinto adapter fake e um endpoint sem runtime local. | Funciona pelo registro sem novo branch por produto no domínio/supervisor. |

## TX — Atomicidade e idempotência

Fases: P05, P06, P09.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-TX-01 | Rollback de criação | Falhar entre writes de message, delivery, evento e outbox. | Tudo é revertido; nenhuma entrega sem intenção requerida ou vice-versa. |
| T-TX-02 | Crash após commit | Matar processo depois do commit e antes de wake. | Entrega/intent persistem; restart ou reconciliação retoma sem duplicar. |
| T-TX-03 | Request repetida | Repetir a mesma chave e payload com concorrência. | Uma única operação lógica e um único conjunto de efeitos canônicos. |
| T-TX-04 | Chave com outro payload | Reutilizar idempotency key alterando conteúdo/target/contexto. | Conflito; operação original não muda. |
| T-TX-05 | Aprovação pendente | Policy exige HITL antes de enviar. | Nenhuma intent executável antes da decisão; aprovação repetida gera uma única execução. |
| T-TX-06 | Todos os produtores | Criar mensagem por MCP, REST, handoff sintético, aprovação e projector. | Todos usam a transação/planejamento corretos; não há produtor que contorne outbox/coalescência. |
| T-TX-07 | Sem IO no UoW | Instrumentar network, spawn, secret resolver, model e callback de transporte. | Nenhum é chamado dentro da transação de escrita. |
| T-TX-08 | Writer incompatível | Tentar escrever com processo/schema capability antigo enquanto integração gerenciada está ativa. | Defesa explícita de incompatibilidade; não gerar mensagens sem reservas/intents exigidas. |

## CONS — Consumo único e inbox

Fases: P05, P06, P09.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-CONS-01 | Pull versus push concorrentes | Dois consumers disputam a mesma MessageDelivery em barreira controlada. | Uma reserva executora vence; payload não é entregue a dois executores. |
| T-CONS-02 | Push aceito e pull posterior | Observar ACK confiável do harness e depois fazer inbox_pull. | Ack/receipt canônicos aplicados uma vez; não iniciar nova execução pelo pull. |
| T-CONS-03 | Falha anterior ao envio | Forçar NOT_SENT após reservar consumo. | Reserva liberável e fallback MCP utilizável; mensagem não desaparece. |
| T-CONS-04 | Envio desconhecido | Perder confirmação depois de write e vencer lease. | Incerteza visível; lease não libera outro executor automaticamente. |
| T-CONS-05 | Takeover explícito | Operador autorizado decide repetir operação desconhecida com razão e risco. | Auditoria/correlação de risco; sem fingir garantia exactly-once. |
| T-CONS-06 | Retry do transporte | Várias falhas de socket seguras antes de aceitação. | Contador/lease da inbox não é consumido como tentativa de transporte. |
| T-CONS-07 | Mirror-only | Configurar observador e executor para a mesma entrega. | Observador não inicia outro send_turn executor; configuração insegura é rejeitada. |
| T-CONS-08 | Receipts duplicados | Reaplicar ACK e projetar receipt após restart. | Ack e read_receipt idempotentes, sem cascata automática de respostas. |

## DISP — Dispatch, recuperação e pressão

Fases: P06, P07.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-DISP-01 | Retorno independente do harness | Travar write/aceitação do adapter e chamar message_create. | Chamada termina após commit/wake sem precisar destravar adapter. |
| T-DISP-02 | Wakeup perdido | Descartar IPC/sinal pós-commit mantendo serve vivo. | Reconciliação indexada recupera intent no prazo configurado. |
| T-DISP-03 | Lost wakeup race | Commit acontece entre drainage e entrada na espera. | Generation/deadline impede dormir indefinidamente com trabalho pendente. |
| T-DISP-04 | Stdio escritor separado | Processo stdio atualizado escreve no mesmo store. | Serve recebe wake/reconcilia; stdio não cria supervisor/filho próprio. |
| T-DISP-05 | Dois owners | Iniciar serves concorrentes e simular perda/retomada de owner epoch. | Um proprietário válido; owner antigo não comita resultados nem despacha nova execução. |
| T-DISP-06 | SENDING expirado | Crash após send-intent; tornar o processo antigo lento e expirar lease. | Estado ambíguo, não retry cego; fencing não é confundido com cancelamento externo. |
| T-DISP-07 | Thread travada | Repetir falhas de uma API bloqueante não cancelável. | Limite de threads/slots preservado e endpoint quarentenado, sem crescimento ilimitado. |
| T-DISP-08 | Ordem e controle | Fila de send_turn com steer/interrupt urgente e expected_turn. | Turnos ordenados; controle correto não espera atrás de toda a fila nem afeta turno futuro. |
| T-DISP-09 | Fairness | Um endpoint lento e outro saudável sob backlog. | Endpoint saudável continua processando; quotas por agente impedem multiplicar limite com endpoints. |
| T-DISP-10 | Backlog cheio | Exceder limites de quantidade e bytes. | Backpressure antes de efeitos indevidos; estado informado, sem descarte de resultados. |
| T-DISP-11 | Backoff | Falhas retryable seguras com clock/jitter injetados. | Retry no deadline correto, sem sleep loop/hot polling nem tempestade de tentativas. |

## LIFE — Lifecycle e protocolos nativos

Fases: P07, P12.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-LIFE-01 | Boot idempotente | Reiniciar serve com specs estáveis e falha em um conector. | Sem identidades/filhos duplicados; falha isolada e outros endpoints disponíveis. |
| T-LIFE-02 | Janela de spawn | Matar owner entre nascimento do filho, registro e handshake. | Mecanismo de birth/ownership reconcilia filho sem depender só de snapshot periódico. |
| T-LIFE-03 | SIGTERM | Encerrar serve com turnos e journal pendentes. | Shutdown limitado, eventos capturados drenados, processos próprios encerrados. |
| T-LIFE-04 | SIGKILL sob carga | Repetir kill com pressão de scheduler comprovada. | Registrar reaps/leaks; nenhuma garantia fictícia baseada só numa execução verde. |
| T-LIFE-05 | PID reutilizado | Simular reutilização de PID e validar identidade do processo. | Processo não pertencente ao Nexus não é encerrado. |
| T-LIFE-06 | Attach preservado | Close/kill do serve com sessão externa dedicada anexada. | Nexus desanexa; não mata o processo externo nem inventa ENDED do peer. |
| T-LIFE-07 | Close concorrente | Close e EOF/erro da pump ocorrem simultaneamente; chamar close novamente. | Teardown/estado idempotentes; finais capturados e nenhuma subscription pendurada. |
| T-LIFE-08 | Multiplexação | Duas sessões Codex usam o mesmo processo e uma encerra. | Um leitor demultiplexa sem perda; fechar uma sessão não mata a outra. |
| T-LIFE-09 | Pi settle | Abort e novo prompt/steer em sequência com eventos atrasados. | Novo comando não corre contra teardown do turno anterior; timing real respeitado. |
| T-LIFE-10 | Claude multi-turn | Dois ou mais turnos no mesmo stream-json. | Identidade nativa estável conforme protocolo e respostas correlacionadas. |
| T-LIFE-11 | Frame inválido e buffers | NDJSON fragmentado, UTF-8, stdout/stderr cheios, frame muito grande ou inválido. | Parser limitado; erro atribuível; nenhum deadlock ou overflow ilimitado. |
| T-LIFE-12 | Drift de protocolo | Binário/schema incompatível com o descriptor. | Capacidade/binding degradado com diagnóstico; outros conectores permanecem operacionais. |

## JRN — Journal, resultados e replay

Fases: P08, P12.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-JRN-01 | SQLite indisponível | Receber resultado final com projeção bloqueada. | Journal durável preserva resultado; volta do SQLite permite projeção única. |
| T-JRN-02 | Crash após journal | Crash após fsync e antes do commit de projeção. | Replay recompõe evento/resultado/intent sem duplicidade. |
| T-JRN-03 | Crash após projeção | Commit de projeção ocorre antes de atualizar checkpoint externo. | Replay vê event_uid já aplicado; nenhum receipt/resultado duplicado. |
| T-JRN-04 | Cauda truncada | Cortar último registro durante append. | Recuperar prefixo íntegro; expor lacuna, não interpretar bytes parciais como resultado válido. |
| T-JRN-05 | Corrupção no meio | Checksum inválido em segmento já fechado. | Parada/quarentena e diagnóstico, sem pular silenciosamente conteúdo. |
| T-JRN-06 | Mesmo texto, eventos diferentes | Dois eventos legítimos idênticos no conteúdo. | Ambos preservados; dedupe por identidade estável, não por texto. |
| T-JRN-07 | Evento duplicado | Repetir o mesmo evento/native ref após reconnect/replay. | Uma projeção canônica, com vínculo correto à tentativa original. |
| T-JRN-08 | Deltas e terminal | Acumular deltas transitórios e finalizar turno. | Terminal durável inclui/referencia texto completo e flush dos registros necessários. |
| T-JRN-09 | Falta de espaço | Esgotar quota/disco de journal e storage. | Nova admissão bloqueada; resultados não são chamados de duráveis; buffers finitos e alerta. |
| T-JRN-10 | Resultado anterior à captura | Matar processo antes de capturar evento, sem replay nativo disponível. | Execução UNKNOWN/resultado indisponível detectável, sem sucesso ou recuperação inventados. |
| T-JRN-11 | Replay paginado | Várias páginas com append concorrente, limite inválido e cursor retido/expirado. | Sequência/cursor explícitos; sem omissões, repeats indevidos ou vazamento de ACL. |
| T-JRN-12 | Artifact e UoW | Falhar entre gravação de artifact e commit de refs. | Nenhuma referência confirmada para arquivo inexistente; órfão recolhível quando aplicável. |
| T-JRN-13 | Resultado negado por policy | Guardrail/approval bloqueia divulgação do resultado. | Original protegido continua durável; publicação pendente/negada não apaga evidência. |

## WORK — Handoffs, grants, input e approvals

Fases: P04, P09.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-WORK-01 | Claim competitivo | Vários agentes e endpoints tentam executar uma oferta. | Um claimant e uma execução; demais recebem apenas informação permitida. |
| T-WORK-02 | Oferta sem payload | Agente elegível observa handoff ainda não claimed. | Payload executável restrito conforme o core; não vaza pelo envelope de oferta. |
| T-WORK-03 | Coalescência | Handoff cria mensagem sintética e intent de dispatch. | Só uma entrada executora; notificação não gera outro turno de trabalho. |
| T-WORK-04 | Bootstrap canônico | Runtime inicia como agente com role, profile e capabilities existentes. | Obtém contexto autorizado correto, sem novo Agent nem secrets/perfis alheios. |
| T-WORK-05 | Fim de turno não é aceite | Emitir turn_completed sem evidências/complete explícito. | Turno encerra; handoff não é marcado COMPLETED indevidamente. |
| T-WORK-06 | Conclusão válida | Claimant autorizado entrega resultado/evidências pelo caminho canônico. | Mesmas validações/transições de complete/verify/reject já existentes. |
| T-WORK-07 | Resultado de claim antigo | Cancelar/reatribuir com política explícita e receber final tardio. | Evidência registrada no claim antigo; novo trabalho não é concluído por ela. |
| T-WORK-08 | Interrupt aceito | Peer aceita pedido de cancelamento sem sinal final imediato. | Estado INTERRUPT_REQUESTED; não declarar interrupção concluída antecipadamente. |
| T-WORK-09 | Approval nativo | Runtime pede aprovação e recebe allow/deny pelo HITL. | Correlação e escopo corretos; nenhuma autoaprovação ou troca silenciosa para sandbox permissivo. |
| T-WORK-10 | Approval repetido/tardio | Duplicar decisão e entregar decisão após encerrar o turno. | Idempotência; decisão não alcança outro turno. |
| T-WORK-11 | Perfil incompatível | Trabalho exige approvals/sandbox que aquele adapter não implementa. | Não elegível para esse trabalho; capacidades conversacionais compatíveis continuam úteis. |
| T-WORK-12 | Attach gerenciado | Executar attach sem ACK e depois com canal Nexus autenticado externo. | Sem canal, não anunciar managed work confiável; com canal, claim/ack/complete são validados. |

## RELAY — Causalidade e budgets

Fases: P10.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-RELAY-01 | Cadeia legítima | A→B e A→B→C com grants/targets válidos. | Entrega e resposta funcionam dentro do orçamento, sem bloqueio genérico entre harnesses. |
| T-RELAY-02 | Cadeia lenta | Hops a cada dez minutos, max depth quatro, deadline trinta minutos. | Deadline/root não reinicia depth; continuação expirada é bloqueada. |
| T-RELAY-03 | Restart no meio | Reiniciar Nexus entre hops. | Root/depth/budget/correlação persistem. |
| T-RELAY-04 | Conversas intercaladas | Mesma sessão participa de dois roots simultâneos/alternados. | Cada saída herda o pai correto, sem usar o estado da última mensagem da sessão. |
| T-RELAY-05 | Múltiplos endpoints | Mesmo Agent envia respostas por conexões diferentes. | Root decorre da operação, não da primeira sessão encontrada em memória. |
| T-RELAY-06 | Fan-out concorrente | Muitos filhos tentam reservar último orçamento disponível. | Reserva atômica respeita limite total; profundidade sozinha não é o único controle. |
| T-RELAY-07 | Retry de filho | Repetir a mesma criação de mensagem filha. | Não consome budget duas vezes nem cria outro filho. |
| T-RELAY-08 | Nova conversa legítima | Entrada nova autenticada após root anterior encerrado. | Novo root permitido sob quotas; não herda bloqueio da sessão anterior. |
| T-RELAY-09 | Loop de receipt/erro | Resultado, receipt, erro sintético e bloqueio de relay são publicados. | Não geram turnos automaticamente nem criam loop no handler de erro. |
| T-RELAY-10 | Spoofing/trace desligado | Modelo forja root/depth e feature_trace está desligada. | Servidor mantém causalidade real e limites independentemente de telemetry. |
| T-RELAY-11 | Resposta broadcast explícita | Configurar notify_target broadcast autorizado e depois removê-lo. | Broadcast explícito funciona; default não divulga resultado privado a toda audiência. |

## PRES — Presença e gramática de targets

Fases: P03, P05, P11.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-PRES-01 | Targets reais | Usar direct/capability/role/tag/broadcast pelas superfícies reais. | Harnesses elegíveis recebem pela mesma semântica, sem inserts manuais de presença em produção. |
| T-PRES-02 | Heartbeat por binding | Dois runtimes do mesmo Agent, fechar apenas um. | Presença restante mantém agente elegível apenas nos workspaces realmente ativos. |
| T-PRES-03 | Stale e crash | Processo some mas linha histórica continua RUNNING. | Não sustentar presença/liveness com o registro antigo. |
| T-PRES-04 | Audiencia e privacidade | Policies inbound/outbound excluem participantes. | Resolver e projeção respeitam as mesmas exclusões sem expor policies privadas. |

## API — Superfícies e extensibilidade

Fases: P01, P02, P11.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-API-01 | Flag desligada | Inicializar MCP stdio/HTTP e REST sem integração habilitada. | Baseline legada preservada e sem novas tools/processos implícitos. |
| T-API-02 | Flag ligada | Exercitar os oito nomes e as rotas equivalentes com autorização. | Façades reusam casos de uso; recursos preservados e respostas honestas. |
| T-API-03 | Schema em cache | Desabilitar feature/permissão depois de um cliente guardar o schema. | Handler runtime ainda nega efeitos não autorizados. |
| T-API-04 | Payload compatível | text/content/canônico, JSON-string e conflitos. | Normalização explícita; dados não são ignorados nem interpretados como autoridade. |
| T-API-05 | Estado por operação | Comando aceito retorna operation_id; observar execução por evento/replay. | Queued, accepted, unconfirmed e final são distinguíveis sem exigir status polling nominal. |
| T-API-06 | Descoberta unificada | Ler agente com múltiplos endpoints e capabilities parciais. | Uma identidade e projeção segura de habilidades/capacidades, sem segredos. |
| T-API-07 | Métrica da superfície | Comparar schema/descrições com flags OFF/ON. | Crescimento real medido; nenhuma isenção fictícia ou duplicação de tool por adapter. |
| T-API-08 | UI diagnóstica | Abrir operação UNKNOWN/ambígua/pending approval e processo detached. | Usuário identifica causa e opções autorizadas sem estado de sucesso enganoso. |

## MIG — Migração e rollback

Fases: P03, P11, P12.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-MIG-01 | Antes de 029 | Migrar store com dados legados. | Dados intactos, nenhum dispatch ou endpoint executor implicitamente criado. |
| T-MIG-02 | 029 existente | Migrar eventos/sessões com e sem dados suficientes de workspace. | Histórico preservado; desconhecidos ficam pending-review/legacy-unlinked. |
| T-MIG-03 | Perfil já danificado | Store apresenta capabilities/metadata apagados anteriormente. | Não inventar conteúdo; emitir diagnóstico e restaurar só com fonte confiável. |
| T-MIG-04 | Idempotência do runner | Interromper backfill e executar novamente. | Sem duplicar bindings/events ou perder dados; constraints consistentes. |
| T-MIG-05 | Histórico unread | Ativar integração com backlog antigo. | Não disparar automaticamente trabalhos anteriores; replay exige seleção/ação explícita. |
| T-MIG-06 | Cutover único | Transição callback antigo→dispatcher novo. | Nunca dois envios reais para a mesma entrega. |
| T-MIG-07 | Rollback ativo | Desabilitar feature com intents SENDING/accepted e journal pendente. | Drenagem/reconciliação seguras; unknown não libera executor concorrente. |
| T-MIG-08 | Backup/restore | Fazer backup consistente e restaurar store+journal/artifacts. | Ponto de consistência verificável; sem owner anterior ativo nem refs confirmadas quebradas. |
| T-MIG-09 | Retenção e exclusão | Prunar histórico/desativar Agent com dedupe e operações pendentes. | Não apagar fences/refs necessários nem causar replay como trabalho novo. |

## E2E — Integração real, carga e evidência

Fases: P12.

| ID | Cenário | Estímulo | Aceite obrigatório |
|---|---|---|---|
| T-E2E-01 | Três full-duplex simultâneos | Pi, Codex e Claude stream no mesmo hub com backends aprovados. | Conversas multi-turn, correlação e isolamento demonstrados por trace real. |
| T-E2E-02 | Attach real dedicado | Injetar marcador em sessão de teste aprovada pelo operador. | Injeção demonstrada separadamente de ACK/resultado, que não são inventados. |
| T-E2E-03 | No-polling nativo | Capturar frames do começo ao fim do turno. | Zero consultas de status; steer/interrupt/approval legítimos classificados à parte. |
| T-E2E-04 | Leaks repetidos | Executar ciclos start/stop/crash/recovery sob carga. | Threads/processos/FDs/memória dentro dos limites; sample size e falhas documentados. |
| T-E2E-05 | Performance comparável | Benchmark antes/depois na mesma configuração, incluindo journal/authorization. | Percentis e overhead medidos; sem remover segurança ou durabilidade para melhorar números. |
| T-E2E-06 | Composição real | Repetir caminhos críticos por servidor real e múltiplos processos. | Wiring de auth/flags/dispatch/journal/presença realmente usado, não só services montados em fixtures. |
| T-E2E-07 | Relatório honesto | Gerar índice a partir dos resultados e comparar com o SHA executado. | PASS/FAIL/NOT_RUN/NOT_APPLICABLE corretos; versões e limitações explícitas. |

## Cortes de crash que precisam ser instrumentados

Instrumentar: antes/depois do commit; antes/depois do wake; depois da reserva de consumo; depois de marcar SENDING; antes/depois de escrever no peer; depois de aceitação externa e antes de persisti-la; após captura do evento e antes de fsync; após fsync e antes da projeção; após projeção e antes do checkpoint; durante close; durante spawn/registro de ownership; e durante atualização de claim.

Em cada corte, registrar a classificação de recuperação esperada: retry seguro, retomar projeção, aguardar peer/reconciliar, desconhecido ou encerrado. Não exigir replay automático onde não há prova de que é seguro.

## Propriedades para testes gerativos

Gerar sequências aleatórias de enqueue/claim/send/ack/timeout/close/revoke/restart com seeds registradas. Invariantes: perfil imutável; no máximo um executor autorizado por unidade lógica; operação desconhecida não vira pendente segura por passagem de tempo; owner antigo não altera novo epoch; resultado durável não desaparece; budget não aumenta; transição de handoff exige claimant/autoridade atuais; evento não vaza para audiência não autorizada.

A biblioteca de testes gerativos é opcional se o repo não a utiliza, mas os cenários determinísticos equivalentes são obrigatórios. Não adicionar dependências pesadas por conveniência.

## Gates finais

**Segurança:** nenhum teste negativo obrigatório falha; matriz positiva também passa para a funcionalidade continuar utilizável.

**Consistência:** crash/races não produzem execução duplicada automática nos fluxos gerenciados nem conclusão sem evidência. Protocolos sem dedupe/ACK permanecem com limitações explicitamente controladas.

**Capacidades:** todos os quatro conectores permanecem implementados; recursos anunciados exigem evidência nativa na versão testada. Um recurso opcional não suportado fica declarado como tal, não simulado.

**Operação:** upgrade, ativação, desativação, rollback, presença, backlog, unknown, journal e limpeza de processo são diagnosticáveis e testados.

**Evidência:** reportar contagem calculada, SHA, fixtures, comandos, versões e limites. O gate dependente de integração real não passa enquanto o respectivo caso estiver NOT_RUN.
