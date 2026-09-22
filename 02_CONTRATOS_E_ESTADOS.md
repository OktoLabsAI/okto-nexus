# Contratos, estados e algoritmos — PR #34

Este documento define comportamento obrigatório. Nomes de campos podem acompanhar os padrões do repositório, desde que o mapeamento seja documentado e não se percam as distinções abaixo. É uma especificação, não uma alegação de implementação existente.

## 1. Identidade e cardinalidades

```text
Agent 1 ── N AgentEndpoint
AgentEndpoint 1 ── N HarnessSession
RuntimeProcess 1 ── N HarnessSession (somente quando o adapter suporta)
Message 1 ── N MessageDelivery (uma por destinatário lógico)
MessageDelivery 1 ── 0..1 reserva de consumo ativa
MessageDelivery 1 ── 0..1 intent executor ativo
DeliveryIntent 1 ── N DeliveryAttempt
HandoffClaim 1 ── 0..1 execução canônica ativa
RuntimeOperation 1 ── N turnos/controles correlacionados, quando necessários
```

Não criar `AgentEndpoint` para cada turno nem novo `Agent` para cada processo. A identidade de endpoint é persistente; uma sessão concreta pode encerrar e ser substituída. A identidade de processo não é igual à identidade da sessão multiplexada.

Um endpoint pull legado pode ser projetado virtualmente para descoberta. Ele não exige migração de todos os agentes nem um processo extra. Endpoints remotos futuros não precisam possuir HarnessSession.

## 2. Contrato de AgentEndpoint

| Campo lógico | Regra |
|---|---|
| `endpoint_id`, `agent_id` | IDs persistidos, imutáveis após criação; agent deve existir |
| `adapter_id`, `protocol` | Resolvidos num registro local autorizado; protocolo não define identidade |
| `adapter_contract_version` | Versão do contrato de integração, distinta da versão do binário/protocolo |
| `enabled`, `activation_state` | Somente operador/autoridade delegada; migração ambígua inicia desabilitada |
| `workspace_binding` | Workspace exato ou conjunto explicitamente autorizado; nenhum wildcard implícito |
| `runtime_profile_id` | Configuração aprovada; opcional em endpoints que não iniciam processo |
| `priority`, `selection_group` | Seleção determinística apenas entre conexões declaradas intercambiáveis |
| `declared_capabilities`, `effective_capabilities` | Declaração versus capacidades verificadas na sessão atual |
| `public_config`, `secret_refs` | Configuração não sensível e referências protegidas, nunca tokens livres |
| `health`, `last_observed_at`, `health_reason` | Saúde observada; separada do status do Agent e da sessão |
| `delivery_consumption`, `response_policy` | Consumo/espelhamento e autorização de resposta explicitamente configurados |
| `revision`, `created_at`, `updated_at` | CAS/revisão para evitar selecionar uma configuração alterada |

O root do workspace vem da resolução canônica de paths. Não inferir equivalência por substring, path relativo recebido de outro agente ou metadata arbitrária. Uma mensagem global pode existir na inbox; executar em um diretório local exige binding explícito.

### Perfil de execução

O perfil contém adapter, binário permitido e versão compatível, opções suportadas, diretórios autorizados, provider/model, ambiente mínimo, secret refs, restrições de recursos, política de sandbox/approval e limites de concorrência. Só expor projeção redigida ao cliente.

Operador pode manter perfis que usam configurações ambientes, mas deve ativar explicitamente `inherit_ambient=true`. Sem isso, não herdar silenciosamente provider, proxies, HOME de ferramentas ou variáveis sensíveis. Um agente comum seleciona um perfil aprovado e não ganha permissão para alterar `CODEX_HOME`, `PATH`, loaders, scripts de inicialização ou argumentos capazes de alterar a autoridade do processo.

Attach não aceita overrides de backend de um processo que não será criado. A ferramenta de descoberta de sessões attach, quando habilitada, só expõe dados permitidos do mesmo usuário e valida identidade do processo/socket; não retorna tokens ou paths sensíveis a agentes sem permissão.

## 3. Registro e negociação de capacidades

```text
AdapterDescriptor
  adapter_id, contract_version, supported_platforms
  configuration_schema, input_schema, native_versions_tested
  capabilities, factory, config_validator, compatibility_probe
```

O registro é construído no composition root. Extensões instaladas pelo operador são código confiável da instalação; não importar módulos definidos por strings fornecidas num payload MCP. Descritor não pode elevar permissões.

### Dimensões distintas

**Habilidades do Agent:** claims de roteamento do catálogo canônico, como revisão de código. Não inferir habilidade da marca do modelo.

**Capacidades do endpoint:** enviar conversa, notificar contexto sem iniciar trabalho, executar handoff gerenciado, receber eventos, observar aceitação, resultados correlacionados, recuperar histórico, suportar idempotency key nativa, multiplexar, serializar, steer e seu timing, interrupt e settle, administrar lifecycle, capturar approvals, preservar artefatos.

**Permissões:** o que determinado ator pode fazer naquela identidade, endpoint, workspace, operação e contexto de trabalho.

A capacidade é efetiva somente se suportada pelo adapter, verificada na versão/configuração real e permitida pelo perfil. `supports_idempotency_key=false` é o default até existir prova do comportamento de deduplicação no peer. Incluir uma chave num prompt não é deduplicação.

`send_only` permanece como compatibilidade, mas não deve ser usado como sinônimo universal de “sem eventos”, “sem observação de processo” ou “sem todos os controles”. Cada operação testa sua capacidade específica. O attach atual não ganha novas garantias por adotar o descriptor.

O catálogo de conectores deve declarar pelo menos o seguinte, confirmado por testes reais em P07:

| Adapter | Recursos a preservar | Não inventar |
|---|---|---|
| Pi RPC | Multi-turn, stream, steering no timing suportado, abort com settle | Steering imediato ou resume/dedupe sem prova |
| Codex app-server | Sessões/threads multiplexadas, eventos, steer/interrupt e approvals suportados | IDs de thread válidos após restart sem reconciliação |
| Claude stream-json | Processo long-lived, conversa multi-turn, saída correlacionável | Controles não observados no binário testado |
| Claude attach cc-socks | Injeção no processo externo selecionado | ACK, execução confirmada, resposta correlacionada ou término observado |

## 4. RequestContext e ExecutionGrant

### RequestContext

```text
request_id
actor_agent_id / trusted_operator_principal
represented_agent_id (quando existir delegação)
authentication_source + credential_binding
workspace_id
endpoint_id, runtime_session_id (quando aplicáveis)
execution_grant_id (resolvido e validado no servidor)
authentication_time, request_deadline
```

Nunca persistir credencial bruta no contexto de auditoria. Nunca derivar `actor_agent_id` de `from_agent_id` livre. Um valor de tool pode escolher o recurso alvo, mas não provar propriedade do recurso.

O contexto de um evento nativo vem do owner da conexão, correlation map e dispatch registrados, não de campos inseridos pelo modelo no corpo do evento.

### ExecutionGrant

Grant descreve delegação limitada: issuer, ator autorizado, agente representado, operações permitidas, workspace, endpoint/profile, handoff/claim e epoch quando aplicáveis, budgets, validade e revogação. Reutilizar o provider/serviço de autenticação existente, estendendo-o para resolver esse escopo onde necessário.

A regra não deve virar `is_operator OR has_agent_id`. A sequência é: autenticar → resolver recurso sem vazar dados → verificar ator/grant → verificar políticas/escopos/quotas da ação → verificar capacidade técnica → produzir efeito.

Uma resposta histórica capturada de um runtime autorizado deve poder ser preservada para auditoria mesmo se o grant foi revogado depois. Entretanto, novos comandos, publicação a novas audiências e transições de trabalho precisam respeitar a autoridade/claim atuais. Guardar evidência e aceitar uma transição são ações diferentes.

### Matriz de autorização lógica

| Ação | Operador confiável | Agente sem grant | Agente com grant adequado |
|---|---|---|---|
| Ver catálogo público de capabilities | Sim, dados redigidos | Apenas projeção permitida | Apenas projeção permitida |
| Administrar endpoints/perfis/secrets | Sim, com auditoria | Não | Somente se o grant administrativo autoriza explicitamente |
| Abrir runtime do próprio agente | Sim | Não por default | Conforme workspace/profile e limites |
| Abrir/controlar runtime de outro agente | Sim | Não | Conforme agente representado e ações específicas |
| Enviar conversa | Conforme regras canônicas | Pelas permissões de mensagem, não por bypass de session id | Pelas mesmas regras + escopo do grant |
| Executar trabalho delegado | Conforme handoff/grant ou operação administrativa explícita | Apenas fluxo de handoff permitido | Claim + grant e política do trabalho |
| Steer/interrupt/close | Conforme escopo/ownership | Não só por conhecer session_id | Ação específica, sessão/turno e claim corretos |
| Replay/resultados | Conforme audiência e autoridade de operador | Apenas quando autorizado | Apenas escopo autorizado; sem secrets |

Ausência de principal num stdio legado não equivale a operador para os novos controles. Um modo CLI de operador local explícito pode ser oferecido com autenticação/permissões locais correspondentes e precisa ser testado separadamente.

## 5. Envelope canônico

Forma lógica ilustrativa, sem expor credenciais:

```json
{
  "schema_version": 1,
  "operation_id": "op_...",
  "delivery_id": "del_...",
  "message_id": "msg_...",
  "intent": "conversation",
  "sender_agent_id": "planner",
  "recipient_agent_id": "reviewer",
  "workspace_id": "ws_...",
  "context_id": "ctx_...",
  "subject": "Revisão da proposta",
  "content": [{"type": "text", "text": "..."}],
  "artifact_refs": [],
  "handoff": null,
  "causality": {
    "root_operation_id": "root_...",
    "causation_id": null,
    "hop_count": 0
  },
  "response_requested": true,
  "reply_to": {"message_id": "msg_..."},
  "trust": {"content_origin": "agent", "instruction_authority": "untrusted_content"}
}
```

IDs e campos de confiança/causalidade são preenchidos ou validados pelo servidor. Referências de trace para observabilidade não conferem autorização e não devem depender de uma feature de telemetry habilitada. A causalidade de segurança existe mesmo se `feature_trace=false`.

Intents mínimos: `information`, `conversation`, `handoff_offer`, `handoff_execute`, `runtime_control`, `receipt`, `result_notification`. Isso classifica o contrato da operação, não o texto natural. Não pedir a uma LLM que decida se um payload pode contornar handoffs.

No adapter, contexto de execução confiável e conteúdo recebido ficam separados conforme o protocolo permite. Quando só existe texto, usar envelope delimitado e orientações de tratamento como dado não confiável; reconhecer que isso não é isolamento de segurança. A autorização precisa continuar fora do modelo, e o sandbox/perfil precisa limitar efeitos fora do Nexus.

Artifacts são referências autorizadas, não paths arbitrários. Resolver/expor apenas o que aquele destinatário pode consumir. Validar tipos/tamanho; externalizar payloads grandes no artifact store existente. Resultado pode conter texto materializado e referências, não duplicação integral de blobs no outbox/event log.

### Compatibilidade de payload

A façade de `harness_send` aceita o payload canônico. Durante a migração pode aceitar os antigos `text`/`content`, normalizando-os numa única representação. Se ambos diferem, retornar `VALIDATION_ERROR`. Valores JSON em string devem ser parseados conforme a convenção do repo ou rejeitados explicitamente, nunca descartados como se o parâmetro estivesse ausente.

Um namespace `native_options` só aceita campos registrados pelo adapter e aprovados para o ator/perfil. Não permitir native passthrough genérico que execute comandos ou mude sandbox/cwd sem autorização.

## 6. Persistência: mínimo lógico

Reutilizar estruturas equivalentes existentes. O desenho lógico necessário é:

| Estrutura | Responsabilidade e constraints |
|---|---|
| `agent_endpoints` | Binding estável, revisão, config redigida, FK Agent; identidade não muda em update |
| `harness_sessions` ampliada | Endpoint, workspace, owner epoch, processo/conexão, lifecycle observado; preservar IDs antigos |
| `delivery_outbox` | Uma operação lógica por destinatário/intenção, idempotency key/hash, envelope/ref, seleção, estado e scheduling |
| `delivery_attempts` | Tentativas imutáveis/auditáveis, dispatch epoch, outcome, native refs, timings e erro redigido |
| `delivery_consumers` ou extensão equivalente | Reserva exclusiva entre pull/push para MessageDelivery; independe do contador de retry do transporte |
| `harness_correlations` | Native connection/session/thread/turn → operation/attempt/claim; uniqueness no escopo correto |
| `harness_events` ampliada | event_uid, sequência estável, origem, operation/attempt, resultado/transitório, watermark/refs |
| `causal_roots` ou estrutura equivalente | Orçamentos persistidos, contadores atômicos, deadline e estado do root |
| Grants/projeção de checkpoint | Reutilizar estruturas existentes; persistir revogação/checkpoint onde não houver equivalente |

Não criar um registro “Operation” e outro “Outbox” idênticos. `delivery_outbox.operation_id` pode ser o próprio identificador canônico de dispatch. Um request que faz fan-out pode ter um correlation/request id pai e operações filhas por destinatário.

Índices mínimos: intents por estado/next_attempt; claim por lease expiry; delivery/recipient; endpoint e workspace; native correlation; event session/sequence; root/state/deadline. Filtragem de payload e `json_extract` no hot path não substituem índices em chaves relevantes.

Uniqueness obrigatória: operação/idempotency no escopo de ator e request apropriado; uma reserva ativa por MessageDelivery; uma execução ativa por handoff claim/epoch; event_uid por domínio estável; native turn mapping por conexão/sessão; attempt_id. Retenção deve preservar dedupe/fences até encerrar toda possibilidade aceita de replay.

Não usar semânticas de PostgreSQL como `SELECT FOR UPDATE SKIP LOCKED` em SQLite. Usar transação curta de escrita e CAS/versionamento compatíveis com a implementação real do UnitOfWork.

## 7. Estados de operação, tentativa e consumo

### 7.1 Operação de transporte

```text
PENDING → CLAIMED → SENDING
                  ├─ ACCEPTED
                  ├─ RETRY_WAIT (somente falha comprovadamente segura)
                  ├─ OUTCOME_UNKNOWN
                  ├─ REJECTED
                  └─ FAILED_FINAL
PENDING/RETRY_WAIT → CANCELLED (se nada externo foi iniciado)
```

Uma operação pode ficar pendente por `waiting_reason` como `NO_LIVE_ENDPOINT`, `BUSY_LANE` ou `APPROVAL_REQUIRED`; não criar uma máquina paralela de tarefas por esse motivo. Aprovação obrigatória não autoriza envio enquanto pendente.

`ACCEPTED` significa a confirmação de aceitação que o adapter consegue provar, e registra o `ack_level`; não equivale a resultado. A execução correlacionada acompanha `RUNNING`, `WAITING_INPUT`, `RESULT_CAPTURED`, `RESULT_PROJECTED`, `INTERRUPT_REQUESTED`, `INTERRUPTED_OBSERVED`, `FAILED`, `UNKNOWN`. Reusar estados existentes onde a semântica coincide.

### 7.2 DispatchResult

```text
outcome: NOT_SENT | REJECTED | ACCEPTED | SENT_UNCONFIRMED | UNKNOWN
ack_level: NONE | TRANSPORT_WRITE | HARNESS_ACCEPTED | AGENT_ACK
safe_to_retry: bool + fundamento enumerado
native_request_id / thread_id / turn_id / session_id
error_code, redacted_details, occurred_at
```

`safe_to_retry` não é decidido pela frase de um erro. É derivado do estágio de envio/protocolo: falhou antes de escrever bytes; peer rejeitou explicitamente antes de aceitar; ou peer oferece dedupe/reconciliação demonstrados. Timeout após write ou resposta perdida não é seguro por default.

`SENT_UNCONFIRMED` do attach não é sucesso confirmado. É uma entrega tentada sem confirmação, visível como tal, sem retries automáticos cegos. Não gerar turn_completed sintético para “fechar” seu lifecycle.

### 7.3 Reserva lógica de consumo

Antes de despachar, reservar o consumidor autorizado daquela entrega. `inbox_pull` participa da mesma exclusão; não recebe o payload para execução se o push já o reservou ou aceitou. `inbox_peek`/histórico podem continuar mostrando a existência conforme ACL.

Para endpoints com ACK confiável, `consume_on_accept` usa a operação canônica de ack/receipt e registra `ack_source`/`ack_level`. Isso significa aceitação do agente/harness segundo o contrato, não leitura humana nem término de trabalho. Para endpoints em que só a conclusão prova recepção, reter a reserva até esse marco.

Falha `NOT_SENT` permite liberar a reserva e fallback MCP. `UNKNOWN`/`SENT_UNCONFIRMED` mantêm visibilidade da inbox, mas não liberam automaticamente outro executor. Operador/agente explicitamente autorizado pode reconciliar ou solicitar takeover reconhecendo risco de duplicidade, com auditoria. Não apagar mensagens nem bloqueá-las invisivelmente.

Ack de observador ou sessão não proprietária não libera uma reserva gerenciada nem autoriza nova execução. Validar o binding de consumo com a credencial/sessão canônica ou token de reserva resolvido no servidor. Um ack legado sem esse vínculo mantém a semântica anterior somente quando não há reserva gerenciada ativa; nunca usar um message_id conhecido como prova de ownership da execução.

No attach, notificações não executoras podem ser espelhadas na sessão externa por configuração. Para trabalho gerenciado, só admitir attach se existir um caminho Nexus autenticado no runtime externo para claim/ack/complete, ou uma operação administrativa explícita que aceite a ausência de confirmação. Caso contrário, anunciar `can_execute_managed_work=false`, mantendo a injeção conversacional.

`mirror_only` não executa tarefas em duas pontas. Só pode transportar observação/contexto em uma rota que não inicia outro executor, ou uma entrega compartilhando um mecanismo de dedupe end-to-end realmente comprovado. Dois `send_turn` com o mesmo texto não atendem a esse requisito.

## 8. Algoritmo de seleção e ordenação

1. Resolver destinatários pela gramática/policies do Nexus; preservar exclusões de audiência e presença.
2. Para cada destinatário, resolver workspace/context/lane. Não derivar workspace de um endpoint escolhido aleatoriamente.
3. Para continuação ou controle, usar binding e native turn da operação original. Não enviar steer a outro endpoint como fallback.
4. Para operação nova, filtrar endpoints habilitados, permitidos ao ator, compatíveis com workspace/profile/capabilities e recursos exigidos.
5. Escolher primeiro o binding explícito aprovado; senão o default do contexto; senão o grupo intercambiável de maior prioridade. Ordenar desempate estável por endpoint_id apenas dentro de um grupo realmente intercambiável.
6. Se houver duas sessões não intercambiáveis sem regra de escolha, retornar/registrar `AMBIGUOUS_BINDING`. Não selecionar a primeira `_live.values()`.
7. Persistir seleção/revisão e reserva de consumo antes dos efeitos. Se revisão/owner mudou, revalidar antes de enviar.
8. Após aceitação, manter afinidade da execução. Novo endpoint só recebe após transferência reconciliada e autorizada.

Cada lane tem uma ordem durável de entrada. Um turno normal não ultrapassa outro da mesma lane. Controles podem ter prioridade, mas carregam expected_turn/epoch e nunca afetam um turno futuro por acidente. Quotas são por agente/root/workspace além de endpoint; abrir vários endpoints não multiplica o orçamento concedido ao agente.

## 9. Algoritmo transacional de enqueue

```text
autenticar/validar forma e tamanho
iniciar UoW de escrita
  verificar principal/policies/guardrails e estado canônico
  procurar idempotency key autorizada
    mesma chave + mesmo hash: retornar operação existente, sem reexecutar
    mesma chave + hash diferente: conflito
  criar message/delivery ou transição canônica de handoff
  criar intent executor único quando permitido
  gravar evento e correlação/budget necessários
commit
notificar WakeupPort (best-effort, sem payload e sem esperar o harness)
retornar aceitação durável + identificadores
```

Para requests duplicados, verificar autenticação e autorização antes de devolver o resultado armazenado. Uma idempotency key descoberta por outro agente não autoriza acesso a conteúdo alheio.

Commands novos que possam executar trabalho devem exigir uma chave de idempotência fornecida pela façade/cliente e devolvê-la. Chamadas legadas sem chave podem receber uma chave gerada, mas não podem ser vendidas como resistentes a retry de um cliente que perdeu a resposta e não sabe a chave. Documentar essa limitação de compatibilidade.

Pending approval tem registro canônico próprio e não gera envio executável. O executor da aprovação reusa a mesma operação/hash, revalida políticas atuais e gera intent uma vez.

## 10. Dispatcher, leases e fencing

A lease de dispatch tem owner id, lease deadline, attempt_id e geração crescente. O owner do `serve` tem epoch persistido. Todas as mutações de tentativa usam CAS com esses identificadores. Um worker que perdeu lease/epoch não pode marcar accepted, release, done ou projetar o trabalho de outra tentativa.

Registrar `SENDING`/send-intent antes de chamar o adapter. Se o processo cair depois desse registro, existe uma janela em que o envio pode ou não ter ocorrido; recuperar como `UNKNOWN`, não como `NOT_SENT`. A janela conservadora é necessária porque não há uma transação atômica entre SQLite e um subprocesso externo.

Fencing do banco não cancela bytes de uma chamada antiga. Em `SENDING` ambíguo, bloquear nova execução e reconciliar o owner/process/peer; só liberar nova tentativa se comprovadamente não aceita ou protegida por dedupe nativo. PID/tempo de lease não são prova de que um efeito externo não ocorreu.

Uma lease de dispatch não cobre a duração inteira da inferência. Após aceitação ela encerra; a execução/claim continua acompanhada com seu mecanismo próprio. Não produzir retry só porque um modelo demorou mais que o prazo de transporte.

Reservar um slot limitado para cada tarefa bloqueante. Thread abandonada continua contando no limite até terminar ou o processo isolado ser encerrado. Se o adapter não pode ser cancelado com segurança, quarentenar e impedir novo envio nessa instância. `Future.cancel`/timeout não é uma primitive de interrupção da thread em execução.

Wakeup usa contador/generation para impedir dormir depois de perder um sinal: capturar generation, drenar due rows, armar espera, revalidar generation/deadline e então esperar. IPC local é autenticado/limitado e só acorda queries por store, não executa comandos. Nunca chamar harness a partir do callback do notifier.

Reconciliação proposta: no startup, reconexão, mudança de ownership, vencimento de deadline e varredura indexada de segurança a cada 30 segundos. Nenhum status polling do peer. O intervalo pode ser alterado por configuração; desabilitá-lo precisa deixar explícita a perda da recuperação de wakeup pós-commit enquanto o mesmo processo continua rodando.

## 11. Lifecycle de processo/sessão

Distinguir:

- **Tracked:** Nexus possui registro em memória; não prova que o peer está vivo.
- **Process observed alive:** handle/process identity observado; não prova que o harness aceita turnos.
- **Protocol ready:** handshake/compatibilidade concluídos; não prova execução de trabalho.
- **Stopped observed:** término do processo ou sessão observado de fato.
- **Detached:** Nexus encerrou seu binding; processo externo pode continuar.
- **Unknown/lost:** não há prova suficiente do estado.

Abrir segue: autenticar → validar configuração/binding → reservar registro STARTING → spawn/attach fora do UoW → handshake → persistir readiness/correlação/ownership → habilitar dispatch. Falha pós-spawn exige teardown/reconciliação, não criação de agente fantasma.

Um subprocesso gerenciado deve ser registrado no mecanismo de ownership desde seu nascimento, com handshake/barreira de inicialização ou recurso equivalente que elimine a dependência exclusiva de um snapshot periódico de `ps`. O watchdog recebe identidade do processo (não apenas PID) e o encerramento do owner. O método concreto deve ser validado por plataforma; nunca usar kill por nome genérico de processo.

Se o repo suporta POSIX e Windows, implementar primitives equivalentes ou declarar o adapter/proteção indisponível no sistema não suportado. Não alegar suporte Windows com testes Unix marcados N/A. Não adicionar dependências de plataforma sem justificativa e testes.

Close segue: negar novos comandos → stop_requested → solicitar fim quando suportado → drenar saídas/journal → observar stop/detach/unknown → atualizar presença desse binding → liberar recursos/registry. Pedidos repetidos retornam o mesmo estado; um processo inexistente conhecido não precisa gerar nova falha. Unknown não vira ENDED só porque o teardown lançou exceção.

Para processos multiplexados, fechar uma sessão não deve matar outras. Matar o processo só quando o owner confirma que todas as sessões a serem afetadas estão autorizadas para encerramento, ou numa recuperação explícita do processo inteiro com blast radius informado.

## 12. Journal de ingresso e projeção

### Formato e segurança

Implementar segmentos append-only com versão, identificador da instalação/store, session/connection, sequence/event_uid, comprimento, payload e checksum. Uma cauda incompleta após crash pode ser truncada no último registro íntegro; corrupção no meio não deve ser ignorada silenciosamente.

Criar arquivos/diretórios com permissões do usuário apropriadas, nomes não controlados por path livre, proteção contra symlink e substituição de arquivos, política de bytes/segmentos e redaction de credenciais. Persistir o máximo de fidelidade nativa possível sem guardar secrets de autenticação. Política/versão de redaction fica explícita.

O buffer de deltas é limitado. A cada terminal, flush/fsync também cobre eventos anteriores necessários para reconstituir a saída. O journal deve manter o conteúdo final materializado ou os fragmentos necessários para reconstruí-lo. Quando o sistema operacional/filesystem requer sincronizar diretório para garantir criação/rename, aplicar a primitive correspondente.

### Projeção atômica

```text
registro durable do journal
  → verificar integridade, origem/correlação e event_uid
  → UoW
      inserir evento se novo
      atualizar estado de transporte/runtime
      persistir resultado/refs ou marcador de resultado pendente
      aplicar transição canônica somente se claim/grant atual permitir
      criar intent de notificação autorizado, uma única vez
      avançar checkpoint/durable watermark correspondente
    commit
  → publicar evento projetado / wake dispatcher
```

Se for necessário gravar artifact em arquivo, fazê-lo antes do UoW por storage atômico/content-addressed, então referenciar no commit. Falha antes do commit pode deixar blob órfão recolhível; nunca uma linha confirmada apontando para um arquivo ainda não escrito. Não chamar `create_message` com um novo UoW dentro de outro: expor reuso transacional apropriado.

Guardar o evento autenticado não significa aceitar uma transição de negócio. Um resultado de claim antigo fica no histórico daquela execução, com estado de late/rejected projection, sem concluir o claim novo. Inbound data não decide actor/claim apenas pelo JSON.

SQLite ocupado não descarta o journal. Erro de policy no resultado pode restringir publicação ou criar approval pendente; o resultado original fica protegido por ACL, não é apagado. Native error é dado; synthetic error do Nexus tem `origin=nexus`, sem fingir que foi emitido pelo peer.

### Limites da garantia

Depois da confirmação durável no journal, crash do `serve` ou indisponibilidade transitória do SQLite não pode perder o resultado. Antes dessa captura, recuperação depende de replay/ACK do peer. Se isso não existir e o processo morrer, a execução fica `UNKNOWN`/`RESULT_UNAVAILABLE`, com lacuna explícita.

Disco cheio para journal e banco impede novas admissões. Não há como prometer retenção indefinida nesse caso: registrar alarme em canais ainda disponíveis, preservar registros íntegros, limitar buffers e interromper/pausar novos envios conforme capabilities. Não afirmar sucesso durável.

A modalidade durável de integração deve validar a configuração SQLite de todos os writers que possam confirmar intents. WAL com `synchronous=FULL`, filesystem adequado e fsync do journal é o default proposto para novos writes gerenciados. Uma mudança em defaults globais requer benchmark/documentação; não sobrescrever configuração legada silenciosamente nem afirmar garantia de power-loss com modo que não a oferece.

## 13. Handoff, consumo, resultados e approvals

Para pool competitivo:

```text
handoff OPEN + oferta visível aos elegíveis
  → claim canônico atômico de um agente
  → vínculo a endpoint/lane e ExecutionGrant
  → outbox de execução
  → runtime aceita e processa
  → resultado capturado
  → complete/verify/reject via services existentes
```

Não enviar payload executável a todos os elegíveis para eles “decidirem” quem vence. Oferta contém apenas o que as superfícies canônicas já permitem. A mensagem sintética de notificação não pode virar uma segunda intent `conversation` executora.

Quando o próprio runtime faz claim por MCP, a credencial/grant precisa resolvê-lo para a mesma identidade; o coordenador não cria outro agente representando o processo. Quando o dispatcher age por delegação, grava o mesmo claim com autoridade explícita e dentro das políticas existentes.

Não converter todo fim de turno em `handoff_complete`. Aceitar conclusão apenas de uma chamada autenticada do agente ou de um resultado estruturado cujo mapeamento e autoridade foram estabelecidos no despacho. Evidência faltante permanece pendente/falha de validação. Revisor/claimant separados continuam separados.

Native approvals têm correlation id próprio e estado pendente; mapear as operações suportadas para ApprovalService/HITL com request hash/turn/actor. Decisão duplicada é idempotente. Decisão tardia para turno encerrado não é enviada ao próximo turno. Revogação/negação deve chegar ao peer quando suportado; nenhuma autoaprovação por timeout.

Quando um adapter/perfil não suporta o approval flow exigido, ele não é elegível para aquele trabalho. Ainda pode servir conversa ou trabalho num perfil explicitamente compatível. Não alterar a política de segurança para encaixar um adapter.

## 14. Causalidade, relay e orçamento

Cada entrada nova autorizada inicia root novo; cada mensagem/resultado gerado a partir dela herda o root e referencia o pai. Parent/root/claim são resolvidos pelo servidor. Native output correlaciona pela operação registrada, mesmo se a sessão já recebeu outra atividade.

Defaults iniciais propostos, configuráveis por operador e testados:

```text
max_relay_depth = 4
max_generated_messages_per_root = 32
max_executions_per_root = 16
root_deadline_seconds = 1800
```

Deadline encerra a admissão de novos encaminhamentos automáticos do root; não reinicia contadores. Não cancela por si só um trabalho já aceito, não descarta seu resultado tardio e não substitui as regras próprias de validade do grant/claim. Captura/projeção de resultado previamente autorizado continua seguindo essas regras canônicas. Se uma conversa precisa continuar após o deadline, é necessária uma nova entrada autorizada e explícita, não uma reclassificação automática da resposta atrasada. Quotas por agente/workspace limitam um cliente que crie muitos roots legítimos ou maliciosos.

A reserva do orçamento ocorre atomicamente quando o filho nasce. Branches não leem todos o mesmo contador e só incrementam depois. Registrar orçamento configurado/snapshot para auditoria. Desativar `feature_trace` não desativa a causalidade de segurança.

Reentrada A→B→A é permitida dentro do orçamento configurado quando a conversa está autorizada. Self-loop automático de um resultado para a própria sessão é rejeitado. Erros/receipts/bloqueios de relay não geram novos turnos automaticamente. A intenção de relay precisa existir na configuração/pedido, e a audiência é reavaliada no momento da entrega.

O que antes era descrito como limite de 30 minutos “por hop” é tratado pela idade total do root. O teste deve incluir hops a cada dez minutos com profundidade quatro, restart entre hops, duas sessões para o mesmo Agent e fan-out concorrente.

## 15. Superfície pública e semântica de resposta

Preservar `harness_list`, `harness_open`, `harness_send`, `harness_steer`, `harness_interrupt`, `harness_close`, `harness_get` e `harness_event_list` como façades opcionais. Novas leituras por operation_id podem ampliar `harness_get` por alvo mutuamente exclusivo ou usar um resource/API de operação; não proliferar aliases sem necessidade.

Respostas de comandos gerenciados devem indicar:

```json
{
  "ok": true,
  "data": {
    "operation_id": "op_...",
    "session_id": "hsess_...",
    "state": "PENDING",
    "durable": true,
    "external_acceptance": "not_observed"
  }
}
```

REST pode retornar 202 para comando aceito, quando isso estiver versionado/documentado. MCP usa o envelope canônico. `open` pode continuar aguardando readiness por um prazo curto definido, mas deve produzir uma operação idempotente e jamais responder `RUNNING` enquanto só existe uma intenção STARTING.

Reads de eventos retornam `event_id`, `sequence`, `next_cursor`/`next_sequence`, `has_more`, watermark durável e indicador de gap/retention. Cursor é monotônico da origem escolhida; não depender de um dataclass que descarta `sequence` ao serializar. Limites numéricos inválidos são rejeitados segundo a gramática canônica.

Compatibilidade é dupla: feature OFF preserva o contrato legado acordado; feature ON preserva capacidades, com mudanças de segurança/semântica da PR explicitamente versionadas. Não prometer compatibilidade com o bypass de autorização ou com a criação implícita insegura de agentes.
