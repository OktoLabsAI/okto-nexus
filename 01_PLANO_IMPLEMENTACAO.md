# Plano de implementação — PR #34 do Okto Nexus

**Versão:** 1.0 · **Data:** 22/09/2026 · **Executor:** Codex

**Resultado esperado:** manter as capacidades da integração nativa de harnesses e corrigir sua incorporação a identidade, autorização, entrega, trabalho, persistência e operação do Nexus.

**Baseline de referência:** `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`. Este pacote especifica trabalho a implementar. Não representa código aplicado nem novos testes executados contra o repositório.

## 1. Escopo e limites

A implementação deve preservar Pi/RPC, Codex/app-server, Claude Code/stream-json e Claude Code/attach cc-socks. Preservar também sessões long-lived, conversas multi-turn, fluxo por eventos sem consultas de status por turno, steering/interrupt condicionados à capacidade, abertura sob demanda e declarada no boot, mensagens roteadas pela gramática existente, replay e limpeza de processos.

O objetivo não é fazer todos os protocolos parecerem idênticos. O objetivo é dar ao Nexus um modelo coerente para escolher e autorizar uma conexão, iniciar uma tentativa, observar o resultado e atualizar a entidade canônica correspondente.

MCP/pull permanece suportado. Um runtime sem determinados recursos continua útil para operações compatíveis. `cc-socks` não perde a capacidade de injetar mensagens em uma sessão já aberta só porque não pode confirmar recebimento; essa limitação passa a ser tratada explicitamente.

Não construir nesta remediação um gateway A2A real, um produto de Agent Cards, um gerenciador genérico de workflows, distribuição cloud, nem um broker externo. Implementar interfaces e projeções que permitam essa evolução sem nova migração da identidade.

## 2. Correções obrigatórias e oportunidades

| ID | Problema/oportunidade | Resultado verificável | Fases principais |
|---|---|---|---|
| F01 | Abertura sobrescreve capabilities/metadata do agente | Conectar/desconectar nunca modifica o perfil canônico | P01–P03 |
| F02 | MCP/REST divergem em autorização | Mesmo principal e ação têm a mesma decisão em todas as superfícies | P01, P04, P11 |
| F03 | Várias sessões recebem a mesma entrega | Um consumidor executor por entrega, seleção explícita de contexto/conexão | P02, P05–P07 |
| F04 | Ponte em memória não retoma envios | Intenção transacional, dispatcher, recuperação e tratamento de ambiguidade | P05–P06 |
| F05 | Resultado terminal pode desaparecer | Journal de ingresso, projeção idempotente e lacunas detectáveis | P08 |
| F06 | Só o corpo da mensagem chega ao runtime | Envelope canônico, origem e correlação preservados | P02, P07–P09 |
| F07 | Caminho paralelo de execução e conclusão | Trabalho vinculado a handoff/claim/grant, sem completar por texto livre | P04, P09 |
| F08 | Relay usa TTL/estado de sessão | Causalidade por operação, orçamento persistido e ramificações controladas | P10 |
| F09 | Extensão depende de enums/factories centrais | Registro de adaptadores e negociação de capacidades; plugin de teste | P02, P07 |
| F10 | Superfície sempre publicada/process ownership difuso | Opt-in, stdio leve, `serve` proprietário dos runtimes, APIs enxutas | P01, P06, P11 |
| F11 | Lifecycle/timeout/subscriptions/órfãos podem divergir da realidade | Ownership e shutdown verificáveis; nenhum encerramento inventado | P07, P12 |
| F12 | Descoberta/presença/capability/tag/broadcast incompletos | Perfil preservado, presença real e roteamento end-to-end | P03, P05, P11 |
| F13 | Backend/env/raw payload podem expor autoridade ou segredos | Perfis aprovados, credenciais protegidas, native passthrough restrito | P03–P04, P07 |
| F14 | Replay, evidências e documentação inconsistentes | Cursor íntegro, garantias explícitas e evidência referida ao SHA correto | P08, P11–P12 |

F01–F10 derivam diretamente da revisão anterior. F11–F14 detalham riscos e oportunidades ligados aos mesmos caminhos; o Codex deve confirmar a manifestação atual em P00, sem apresentá-los antecipadamente como bugs reproduzidos.

## 3. Arquitetura de destino

```text
Agent — identidade, habilidades, perfil e regras canônicas
  └── AgentEndpoint [1:N] — protocolo/adaptador/capacidades/escopo/saúde
        └── HarnessSession [0:N] — instância de runtime quando aplicável

MCP / REST / CLI / coordenação interna
  → RequestContext autenticado
  → casos de uso e políticas existentes
  → MessageDelivery ou Handoff/Claim
  → DeliveryIntent / RuntimeCommand na outbox
  → dispatcher + seleção/ownership
  → AdapterRegistry → conectores existentes
  ← ingresso de eventos → journal → projeção idempotente
  ← resultados/artefatos/notificações no core
```

`HarnessSession` pode continuar sendo o nome e a tabela existentes; não criar uma segunda tabela `RuntimeSession` com o mesmo propósito só por uniformidade de nomenclatura. Separar a sessão do processo físico: Codex pode multiplexar sessões por conexão de processo. O histórico `harness_events` também deve ser aproveitado e ampliado, não substituído por um event store paralelo sem necessidade.

A inbox é a fonte de verdade do recebimento lógico. A outbox rastreia transporte e não decide quem possui o trabalho. O journal é um buffer durável de ingestão/replay; não é uma terceira autoridade de workflow. O handoff continua decidindo claim, responsabilidade, entrega e verificação.

## 4. Decisões fechadas para a implementação

### 4.1 Identidade, perfil e autoridade

Abrir uma sessão exige um agente existente e acessível ao chamador. Criar um agente novo é uma operação canônica, explícita e autorizada. Não usar `AgentRepo.upsert` dentro do lifecycle de conexão para modificar role/capabilities/metadata.

O RequestContext vem do mecanismo de autenticação ou de um contexto interno comprovadamente confiável. `agent_id`, `owning_agent_id`, `from_agent_id`, `role`, IDs de sessão e campos JSON nunca constituem credencial por si sós.

Permissões efetivas combinam a autoridade do ator, uma delegação válida quando existente, políticas do agente representado e escopos aplicáveis à operação. Isso não é um OR entre privilégios. Um serviço de sistema não transforma uma solicitação negada em solicitação do operador.

### 4.2 Entrega e estados

Persistir intenção de entrega junto da mensagem/entrega/evento, ou junto da transição canônica de trabalho. Confirmar ao chamador a aceitação durável, não uma entrega externa ainda não observada.

Uma reserva de consumo lógico arbitra inbox/pull e push. Uma lease de dispatch coordena tentativas curtas de transporte. Uma lease de handoff coordena o trabalho. São mecanismos com objetivos diferentes; não reutilizar contadores e expiradores indiscriminadamente.

A unidade de deduplicação da operação é estável entre retries e troca segura de endpoint. `attempt_id` identifica uma tentativa; não deve virar uma nova identidade de trabalho.

Falha provadamente anterior ao envio permite retry/fallback. Envio possivelmente aceito exige reconciliação, deduplicação comprovada ou intervenção. Não trocar de endpoint nem liberar outra execução apenas porque uma lease venceu.

### 4.3 Push, polling e recuperação

O caminho nominal usa sinais em memória/IPC e leitura bloqueante dos streams nativos. Não introduzir polling de status do harness nem LLM para descobrir se terminou.

Um dispatcher durável precisa retomar intents após restart e recuperar sinais perdidos entre commit e notificação. Implementar reconciliação de recuperação limitada, inclusive entre processos, sem torná-la o caminho nominal. O default proposto é uma varredura indexada de segurança a cada 30 segundos, além de wakeups por commit, conexão e deadline. O intervalo deve ser configurável e explicitamente documentado como polling interno de recuperação, não chamado de “zero polling em todo o sistema”.

Mensagens criadas por processos stdio atualizados devem notificar o `serve` por IPC local depois do commit. Notificação não é entrega e não contém payload sensível. Falha do IPC não desfaz a transação nem perde a intenção. Sem `serve`, a inbox continua utilizável; envio nativo fica aguardando um proprietário válido ou é rejeitado antes do enqueue quando o contrato exige runtime ativo.

### 4.4 Durabilidade de saída

Preservar o fluxo nativo e a sequência. Deltas podem ser publicados como transitórios antes da confirmação durável, mas nunca anunciar um resultado final como durável antes de um write confirmado no journal ou banco. Um `turn_completed` precisa incluir o resultado materializado/correlacionado, não apenas metadados de encerramento.

Journal e projeção devem suportar restart, duplicidade, cauda truncada e falha de SQLite. O sistema precisa distinguir “não concluído”, “resultado capturado aguardando projeção” e “resultado não recuperável/estado desconhecido”. Não prometer recuperar bytes que o processo morreu antes de capturar, quando o protocolo não dispõe de replay/ACK.

### 4.5 Trabalho versus conversa

Mensagens diretas conversacionais podem iniciar resposta. Broadcast informativo, receipt e erro de infraestrutura não se tornam trabalho automaticamente. O comportamento de resposta/relay deve ser uma política estruturada, não classificação de segurança feita por LLM nem parsing de palavras no prompt.

Pedidos de trabalho entre agentes continuam usando handoff. Um controle administrativo direto de runtime pode existir para o operador e para delegações explícitas, com auditoria e contexto; não deve ser a fuga pela qual agentes ignoram handoff, quotas ou guardrails.

### 4.6 Preservação sem congelamento de defeitos

Manter os quatro conectores e seus testes de protocolo. Evoluir o port quando necessário usando uma fachada/versão compatível. Retirar do core o conhecimento de `text` versus `content` e métodos nativos. Não manter o antigo forwarding em paralelo depois que o dispatcher assumir a entrega: isso produziria double-send.

## 5. Fases executáveis

### P00 — Baseline, contratos reais e reprodução

**Objetivo:** converter os achados em evidência atual e mapear as dependências antes de refatorar.

Inspecionar `AGENTS.md` e instruções equivalentes, estado Git, migrações, configurações/feature flags, autenticação, services e a composição real. Ler ADR 0004, os planos originais e o índice de evidências, distinguindo declarações antigas de observações no SHA atual.

Mapear o caminho completo: autenticação → tool/rota → service → UoW → inbox/outbox → transporte → eventos → resultado. Incluir `handoff.py`, `inbox`/receipts, governance, approvals, artifacts, `serve` e stdio, não apenas o supervisor.

Reproduzir F01–F10 com fixtures controladas. Capturar falhas de autorização por MCP autenticado, não apenas chamadas diretas ao Python. Verificar quem cria a presença canônica dos harnesses e se broadcast/tag funcionam sem fixtures inserindo sessões diretamente no banco.

Capturar schemas, defaults, surface revision, config efetiva, contagens reais e versões dos binários disponíveis. Não usar o total de testes da descrição da PR como baseline executada. Testes que exigem credenciais não autorizadas ficam pendentes, com motivo.

**Artefatos:** `BASELINE.md`, `DEFECT_REGISTER.md`, `CONTRACT_MAP.md`, testes de regressão inicialmente vermelhos e snapshot dos contratos legados.

**Gate:** cada achado confirmado tem reprodução/observação; cada achado não reproduzido tem justificativa e teste que demonstre a ausência. Nenhuma correção destrutiva foi feita em perfis ou dados.

### P01 — Contenção: identidade, autorização mínima e publicação opt-in

**Objetivo:** fechar os caminhos perigosos antes da evolução estrutural.

Remover os efeitos colaterais sobre Agent em `HarnessSupervisor.open`. Negar abertura para agente inexistente com erro prescritivo, sem criar identidade implicitamente. Tratar parâmetros legados `role`/`metadata` sem alterar o perfil; metadata de conexão vai para conexão/sessão, role canônica conflitante gera erro/depreciação explícita.

Até a política completa de P04, aplicar autorização conservadora uniforme para controle de runtime: operador confiável e agentes com grant explicitamente permitido; não presumir que qualquer agente autenticado pode controlar qualquer sessão. Aplicar também às leituras de sessão, eventos e configuração.

Adicionar opt-in real para a integração e opt-in separado para attach não documentado. Desligado, não publicar as novas tools; manter o caminho antigo de mensagens/inbox. Instalar guardas runtime para clientes com schemas em cache.

Enquanto P05 não existir, impedir mais de um executor ativo por binding lógico e não manter dois forwarders concorrentes. Essa restrição é temporária e não deve virar a arquitetura final.

**Gate:** F01 e F02 reproduzidos passam; feature desligada preserva baseline; feature ligada continua abrindo cada conector no teste autorizado. Testar ambos os estados.

### P02 — Contratos de domínio, envelope e registro de adaptadores

**Objetivo:** estabelecer identidades estáveis de conexão/operação e as capacidades realmente necessárias.

Implementar os contratos de `02_CONTRATOS_E_ESTADOS.md`: AgentEndpoint, RequestContext, ExecutionGrant, DeliveryEnvelope, DispatchResult, correlação, eventos de transporte e lifecycle observável. Reaproveitar tipos existentes com interfaces versionadas quando apropriado.

Implementar AdapterRegistry no composition root, não um loader arbitrário de código remoto. Identificadores de adaptador são dados registrados/validados; o domínio não contém a lista fechada de produtos. O registro fornece descriptor, factory, validação de configuração, capacidades, schema e compatibilidade de versão.

Separar habilidades do agente, capacidades do endpoint e permissões. Expor capacidades efetivas por sessão sem elevar um campo anunciado pelo harness a autoridade. Capacidade desconhecida ou não verificada é falsa para operações que dependem dela.

Implementar envelope estruturado com IDs lógicos, ator autenticado/representado, workspace, conteúdo, artefatos, origem, causalidade, intent e budget. O adapter é responsável por representar esse envelope no protocolo real sem rebaixar dados não confiáveis a instruções privilegiadas.

**Gate:** testes puros de validação/serialização/transições e um quinto adaptador falso registrado sem editar branches de domínio/supervisor por nome de produto. Nenhum SDK externo importado pelo core.

### P03 — Persistência de bindings, perfis de execução, segredos e presença

**Objetivo:** materializar conexões sem apagar nem duplicar a identidade.

Criar migrações aditivas para endpoints, configuração segura, referência das sessões ao endpoint, ownership/generation, correlação e índices. Não fixar números de migração antes de olhar o HEAD real. Respeitar o parser de migração do projeto; não editar a 029 já aplicada.

Persistir configuração por referência e dados públicos necessários à seleção. Segredos não vão em `metadata`, retorno `backend.applied`, log, journal de eventos ou linha de comando visível. Preservar provider/model/env/extra_args como capacidades do produto, mas submetê-los a perfis aprovados e validação por adaptador. Agentes delegados escolhem perfis permitidos, não env/argv arbitrários.

Reutilizar `workspace_resolve` e a presença canônica. Uma sessão de runtime saudável sustenta presença verificável no workspace correspondente; não falsificar heartbeat de um processo morto e não fechar a presença de outras conexões do mesmo agente. Close/reap/restart precisam atualizar apenas o vínculo que possuem.

Migrar sessões históricas conservadoramente. Registro `RUNNING` antigo não prova liveness. Endpoint inferido fica desabilitado/pending-review se root, credencial ou perfil forem ambíguos. Não recriar capabilities/metadata já apagados por suposição; produzir diagnóstico recuperável por fonte confiável.

**Gate:** upgrade de base sem integração e com 029, idempotência do runner, integridade referencial, preservação de dados e roteamento real por role/capability/tag/broadcast. O recurso não depende de inserts manuais em fixtures de produção.

### P04 — Autorização uniforme, delegação e defesa das bordas

**Objetivo:** impedir impersonação, bypass de políticas e exposição de sessões/resultados.

Centralizar os casos de uso e as ações lógicas de autorização: descobrir endpoint, abrir, enviar conversa, despachar trabalho, steer, interrupt, close, replay e administrar binding/perfil. Aplicar autorização antes de construir um conector, resolver segredo ou tocar num processo.

RequestContext distingue ator, agente representado, endpoint/sessão, workspace, método de autenticação, grant e request id. REST de operador, MCP autenticado e CLI local entram pelo mesmo service. Stdio legado sem identidade verificável não recebe administração de runtime automaticamente; exigirá contexto local explícito e confiável, sem inferir operador pela ausência de chave.

Implementar/reaproveitar grants vinculados a ator/agente, ações, workspace, endpoint, handoff/claim, expiração, revogação e budget. O grant é uma restrição da autorização canônica, não um esquema alternativo que ignora keys/policies. Revalidar no enqueue e imediatamente antes do envio; registrar a revisão usada. Revogação não consegue desfazer efeitos externos já iniciados, mas bloqueia novos envios e projeções não autorizadas.

Não expor chaves de outros agentes nem do operador ao subprocesso. Quando o runtime precisar chamar tools Nexus, disponibilizar contexto restrito por sessão/grant usando os providers existentes ou extensão delegada compatível. Não confiar num `grant_id` enviado pelo modelo sem autenticação/binding. Permissões do sistema operacional e sandbox são defesa separada: uma policy Nexus não controla por si só um shell com acesso irrestrito.

Tratar consultas fora do escopo com erro opaco consistente, sem denunciar existência de sessão, paths, peers ou secrets. Validar limites de payload, artifacts e configurações nativas. Reutilizar governance/guardrails/approvals, inclusive resultados/notificações.

**Gate:** matriz negativa e positiva equivalente em REST, MCP HTTP, stdio configurado e chamadas internas. Negação produz zero envios/spawns/leituras secretas. Grant revogado ou expirado não executa.

### P05 — Outbox transacional, seleção de endpoint e exclusão de consumo

**Objetivo:** uma solicitação canônica gera uma intenção recuperável e um único consumidor executor.

Extrair funções transacionais de criação/projeção se necessário para reuso sem nested UoWs. Inserir intenção no mesmo commit de message/delivery/event ou da transição de handoff/claim que a autoriza. Pending approval não cria execução despachável. Aprovação posterior gera intenção uma única vez.

Selecionar primeiro o destinatário lógico pela gramática atual; depois, dentro dele, selecionar endpoint/session/lane por workspace, continuidade, capacidades, perfil e política. A selection policy deve ser determinística e auditável. Empate entre runtimes não intercambiáveis retorna ambiguidade, em vez de escolher a primeira entrada em memória.

Criar reserva de consumo lógico compartilhada com inbox/pull para entregas gerenciadas. Não consumir contadores de redelivery da inbox por falha de socket. Permitir peek/histórico, mas não entregar a mesma unidade simultaneamente ao pull e ao push. Expiração não libera automaticamente operação cujo envio é incerto.

Preservar legacy recipients: sem endpoint ativo ou com integração desligada, o caminho MCP mantém comportamento anterior. `mirror_only` não pode duplicar trabalho executável; só é permitido como espelhamento não executor explicitamente configurado ou quando todos os executores compartilham dedupe comprovado.

Introduzir chave estável de idempotência por operação/destinatário, hash do payload, uniqueness e conflito quando a chave é reutilizada para outro conteúdo. Respostas de `message_create` preservam `delivered_count` como contagem de inbox; uma extensão separada reporta aceitação/transport status quando habilitada. Não alterar seu significado silenciosamente.

**Gate:** rollback atômico, replay da mesma request, consumidores concorrentes, duas conexões do mesmo agente, dois workspaces, aprovação, desativação do endpoint e fallback seguro. Nenhuma chamada externa dentro do UoW.

### P06 — Dispatcher assíncrono, recuperação e backpressure

**Objetivo:** tirar espera por transporte da chamada do usuário sem perder confiabilidade.

Implementar dispatcher controlado pelo lifecycle de `serve`. O primeiro release mantém um proprietário ativo por store; usar o lock existente e epoch persistido, com fail-closed para proprietários concorrentes. Preparar claims duráveis, mas não vender HA/multiwriter de processos de runtime que não foi implementada.

O dispatcher faz claim por CAS/lease em transação curta, resolve credencial fora do UoW, revalida autorização/binding, registra send-intent, chama adaptador fora do UoW e grava a observação com fencing de tentativa. Um worker antigo não pode alterar estado após perder epoch. Fencing de banco não impede uma chamada externa tardia; a seção de ambiguidade deve ser implementada integralmente.

Implementar wakes em memória e IPC local, drainage em lotes, wake generation para evitar lost wakeup, timers por retry/deadline e reconciliação de segurança. Writers stdio não criam supervisores locais nem pipes duplicados. Eventos de wake não são payload nem authority.

Limitar inflight global/por endpoint/lane, backlog durável, bytes, threads/processos auxiliares e retenção. `send_turn` segue fila ordenada por lane; steer/interrupt/close usam controle prioritário, sem ultrapassar o fence/turno correto. Um harness lento não bloqueia o retorno de `message_create` nem o controle dos demais.

Classificar erros em definitivamente não enviado, rejeitado, aceito, resultado desconhecido e falha terminal. Backoff/jitter só para retries seguros. Circuit breaker/quarentena são por endpoint/process owner conforme blast radius, nunca um bloqueio global sem motivo.

**Gate:** commit antes de wake, sinal perdido, mensagem por stdio separado, restart, duas tentativas de ownership, transporte travado e pressão de fila. A latência de enqueue não escala com os timeouts dos destinatários.

### P07 — Conectores, controle de runtime e lifecycle robusto

**Objetivo:** adaptar sem perder recursos nativos nem criar processos zumbis.

Envolver os quatro conectores com os contratos canônicos. Dentro do adapter, mapear envelope para `text`, `content`, JSON-RPC e outras formas reais. Normalizar respostas/eventos sem perder IDs e raw/native attribution. Não manter ramos de protocolo no application service.

Para Codex, um processo/pipe possui um leitor e demultiplexação por conexão/thread/turn; duas sessões não podem disputar um gerador destrutivo de eventos. Para Pi, preservar o settle após abort e steering no momento realmente suportado. Para Claude stream, preservar conversas multi-turn e sessão estável. Para attach, preservar injeção explícita, sem inventar ACK, steering ou observação de encerramento.

Implementar serialização de comandos por lane, deadlines separados de connect/write/acceptance/turn/stop e correlação de respostas tardias. Cancelar espera não cancela execução. Se uma API bloqueante não puder ser interrompida, ocupar um slot limitado e quarentenar o endpoint; não criar uma thread nova a cada retry. Fechar apenas o processo que o Nexus efetivamente possui.

Abertura deve ser idempotente por request, reservar sessão STARTING antes dos efeitos externos e reconciliar spawn parcial. Registrar ownership de processo desde a criação, não apenas por varredura periódica de `ps`. Usar recursos de processo/grupo/handle disponíveis na plataforma e reforçar o watchdog existente. Proteger contra reutilização de PID. Attach nunca entra numa rotina que mata o processo externo do operador.

Close deve ser idempotente, com estados de stop solicitado, encerramento observado, detach e estado desconhecido distintos. Capturar eventos finais e drenar journal antes de remover correlação/subscriptions. Tratar subscribe/start/reap concorrentes e falhas de validação posteriores ao spawn com teardown apropriado.

Boot usa os mesmos casos de uso, com specs de IDs estáveis, startup budget global e isolamento por sessão. Não usar cada restart para criar agentes/sessões duplicados. Restaurar uma sessão só quando resume/reattach for suportado e o estado tiver sido reconciliado; nunca reenviar o último prompt cegamente.

**Gate:** suíte de contrato dos quatro adapters, multi-turn real, controles reais, multiplexação, write travado, falha de handshake, start timeout, close concorrente, SIGTERM e SIGKILL, incluindo sessões attach preservadas.

### P08 — Journal de eventos, resultados duráveis e replay correto

**Objetivo:** nenhum resultado capturado é descartado por uma falha transitória de projeção.

Implementar journal append-only local atrás de um port de infraestrutura. Dar event_uid e sequência estáveis no ingresso, antes da primeira persistência/repetição, incluindo escopo de processo/conexão quando o protocolo não fornece IDs únicos. Não deduplicar mensagens diferentes só porque possuem o mesmo texto.

Registrar o fluxo nativo com enquadramento, checksum, versionamento e política de redaction de segredos. Deltas podem usar group commit limitado; eventos terminais fazem flush/fsync de todos os registros anteriores relevantes antes da confirmação durável. Expor watermark durável e marcar dados transitórios separadamente.

O projector lê registros duráveis e, em UoW curto, insere o evento idempotentemente, atualiza estado/correlação, materializa resultado e registra intents de notificações. Guardrails/approvals podem deixar publicação pendente ou bloqueada; o resultado capturado não é apagado. Índice e checkpoint do journal devem ser seguros a replay após crash.

Tratar SQLite ocupado/indisponível, cauda truncada, disco cheio e quota. Parar admissão quando não houver condição de preservar novos resultados. Não depender de buffer RAM sem limite. Falha simultânea de storage/protocolo sem replay deve resultar em estado desconhecido e alerta, não `COMPLETED` fabricado.

Corrigir `harness_event_list`: sequência/event id/next cursor estão na resposta, limites validados, página estável sem duplicar/pular registros, autorização por audiência/workspace, comportamento definido para cursor expirado. Estado/replay do banco não prova que um processo está vivo.

**Gate:** falha em cada corte de crash, replay duplicado, finalização fora de ordem, truncamento e reinício. Zero eventos terminais capturados perdidos silenciosamente; lacunas anteriores à captura são detectadas e reportadas.

### P09 — Handoffs, bootstrap do agente e approvals

**Objetivo:** o runtime passa a executar trabalho do Nexus, não uma fila concorrente de prompts sem ownership.

No fluxo de trabalho, criar/usar handoff canônico, obter claim legítimo e vinculá-lo a um ExecutionGrant e a uma lane. Para pool competitivo, enviar apenas oferta/aviso não executor aos elegíveis; só o vencedor recebe payload executável. Coalescer mensagem sintética e dispatch para não criar dois trabalhos.

Inicializar o agente com identidade lógica, role/profile autorizado, workspace, capacidades e instruções de recepção/handoff. Obter esses dados dos services canônicos, sem copiar segredos, policies privadas ou perfis alheios. O agente precisa saber se está respondendo conversa, recebendo oferta ou executando claim.

Mapear resultado explícito/estruturado ou chamada autorizada do agente para os services `handoff_complete`/verify/reject equivalentes existentes. `turn_completed` encerra o turno, não aprova automaticamente a entrega. Preservar requisitos de evidência, verificação e separação de responsabilidades.

Integrar pedidos nativos de approval/input aos mecanismos de aprovação já existentes quando o protocolo os suportar. Não aprovar tudo nem configurar execução insegura por default para evitar implementar o fluxo. Descritores devem dizer se um perfil precisa de approvals ainda não suportadas; nesse caso, negar esse perfil, não fingir compatibilidade.

Interrupção/cancelamento valida a autoridade e o claim epoch. Pedido de interrupt aceito não equivale a aborto observado. Resultado tardio de claim cancelado/reatribuído fica registrado, mas não conclui o novo handoff. Reatribuição com execução anterior incerta exige decisão explícita/isolamento dos efeitos, não vencimento automático de lease.

**Gate:** pool de vários agentes e endpoints produz um executor; mensagem sintética não dispara segundo turno; conclusão/approval/verify seguem o core; actor/claim errados e respostas tardias não transitam a entidade.

### P10 — Relay com causalidade persistida e notificações seguras

**Objetivo:** manter colaboração entre harnesses sem loops reiniciados por TTL ou fan-out.

Transportar root_operation_id, causation_id, parent, hop count, deadline e budget em registros canônicos. Gerar filhos no servidor a partir de um pai autenticado; não aceitar depth/root fornecidos pelo modelo como autoridade.

Validar orçamento de profundidade e também orçamento total de mensagens/execuções por root, com reserva atômica para ramos concorrentes. Profundidade limitada sozinha não controla explosão em árvore. O orçamento exato é configurável; defaults propostos estão no contrato.

Tempo não redefine causalidade. Uma continuação de root expirado é bloqueada/encerrada; uma conversa nova legítima requer uma entrada nova autenticada/sem pai anterior, respeitando quotas. Não atribuir o root da última sessão a toda mensagem futura daquele agente.

Preservar A→B, A→B→C e conversas bidirecionais limitadas. A política de relay decide se saída gera nova entrada; resultados/receipts/erros não são executáveis por default. O destino padrão de resposta correlacionada é a audiência autorizada da conversa, não broadcast implícito de resultados.

`notify_target` continua suportando broadcast e demais estratégias quando explicitamente configurado e autorizado. Observadores recebem eventos, não comandos de trabalho. Bloqueio de relay gera um evento persistido não reencaminhável, evitando recursão no próprio tratamento de erro.

**Gate:** cadeia lenta, reinício, branches concorrentes, mesma identidade com várias sessões, conversas intercaladas, source spoofing, receipts e resposta tardia. Nenhuma continuação se torna root novo por expiração.

### P11 — Superfícies, descoberta, UX, documentação e compatibilidade

**Objetivo:** tornar a solução operável sem inflar desnecessariamente o MCP.

Manter os oito nomes de tools existentes atrás do opt-in quando possível, como façades dos mesmos services. Não criar duplicatas para cada adaptador. Preservar formas legadas `text`/`content` por normalização explícita na borda; duas versões conflitantes retornam erro. Campos nativos especiais ficam em namespace restrito, validados pelo adapter e por autorização.

Expor lista de adaptadores e bindings/sessões que o chamador pode ver. `harness_list` não deve se confundir com lista de instâncias; usar parâmetro/visão clara ou a API de endpoints. Disponibilizar estado de operação pelo operation_id, eventos push/SSE e replay, sem exigir status polling na recepção nominal.

Acrescentar gestão de endpoints, perfis e outbox pela superfície administrativa existente. Manter schema MCP pequeno, descrições curtas e detalhes em resources. Medir schema/docstring tokens ou bytes conforme a ferramenta já usada no repo; não esconder crescimento num desconto artificial de teste.

No dashboard/visão operacional, mostrar agente único, endpoints, runtimes, perfil efetivo redigido, capacidades, estado de conexão, reserva de entrega e ambiguidade. Diferenciar `queued`, `accepted`, `sent_unconfirmed`, `running`, `result_durable` e `handoff_completed`. Replay e resultados obedecem ACL.

Atualizar ADR, guia operacional, resources, surface revision, changelog e índice de evidências. Corrigir exemplos que prometem entrega garantida por socket ou polling como necessidade do novo push. Publicar matriz de plataforma/versão e limitações reais do attach.

**Gate:** mesmas decisões e envelopes nas superfícies, flag desligada equivalente à baseline acordada, contratos versionados ligados, UI funcional para diagnosticar casos desconhecidos, documentação não contradiz implementação.

### P12 — Campanha adversarial, desempenho e liberação

**Objetivo:** aprovar a integração inteira, não um conjunto de componentes isolados.

Executar a matriz de `03_MATRIZ_TESTES_E_ACEITE.md`, baseline completa e testes reais com os quatro conectores. Evidências de protocolo precisam indicar binário, versão, backend aprovado, SHA, intervalo de captura e correlação do caso. Redigir segredos antes de commit.

Testar falhas de UoW, IPC, journal, storage, processo, concorrência, auth e budget nos cortes especificados. Executar cenários black-box pela composição real para impedir que fixtures ad-hoc ocultem falta de wiring. Cada defeito exige teste de mecanismo e ao menos um caso integrado relevante.

Medir enqueue, commit→dispatch, first event, terminal→durable, backlog drain, overhead de journal e de autorização, CPU idle, memória/threads/FDs, shutdown e recuperação. Comparar com baseline no mesmo ambiente. Não prometer SLO universal baseado em máquina única; os limites de bloqueio e crescimento devem ser invariantes testáveis.

Provar no-polling do harness por trace classificado: consultas de status são zero no intervalo ativo; comandos legítimos de steer/approval/interrupt são permitidos e contados à parte. Não exigir zero bytes OUT se o protocolo demanda uma resposta de aprovação.

Executar dry-run de migração e rollback operacional; repetir kill sob carga de scheduler que realmente afete o processo. Zero falhas numa amostra é evidência, não prova matemática de ausência de race.

**Gate:** todos os requisitos obrigatórios resolvidos, nenhum conector removido/falseado, nenhuma execução duplicada silenciosa nos cenários gerenciados, auth/durabilidade verificadas, pendências externas explicitamente bloqueando apenas os gates que delas dependem. Não fazer merge automático.

## 6. Dependências e integração

Ordem recomendada: P00 → P01 → P02 → P03 → P04 → P05 → P06 → P07 → P08 → P09 → P10 → P11 → P12.

Contratos de P02 e testes negativos de P01 devem existir antes da paralelização pesada. P07 e P08 podem ser desenvolvidos em paralelo por portas estabilizadas, mas seu gate integrado precede P09. P10 depende de envelope/correlação e da projeção idempotente. P11 pode preparar documentação mais cedo, mas só fecha depois das decisões efetivamente implementadas.

Separação sugerida de trabalho: domínio/auth; persistência/delivery; adapters/lifecycle; ingress/resultados; integração/testes/documentação. O Codex coordenador mantém ownership de composition roots, migrações e versionamento de contratos. Nenhum subagente pode resolver um bug criando um service privado que não é usado pela aplicação real.

## 7. Mapa inicial de arquivos

| Arquivo/área atual | Modificação pretendida |
|---|---|
| `application/harness_supervisor.py` | Reduzir a lifecycle/coordenador operacional; remover profile mutation, callbacks de trabalho, TTL relay e best-effort terminal |
| `application/messages.py` | Planejamento transacional de intents; eliminar envio externo síncrono; reuso seguro na projeção |
| `application/handoff.py` e services equivalentes | Claim/grant/dispatch e resultados pelo ciclo canônico |
| Services de inbox e `sqlite/messages_repo.py` | Reserva lógica, pull/ack coordenados, sem misturar tentativas de transporte |
| `application/ports.py`, `domain/harness.py` | Contratos evolutivos; registro em vez de produtos codificados no domínio |
| `adapters/outbound/harness/*.py` | Tradução/negociação, IDs, deadlines, observação e protocolo nativo |
| `adapters/outbound/inbox_notifier.py` | Substituir função de transporte por wakeup; retirar caminho legado ao integrar dispatcher |
| `adapters/outbound/sqlite/identity_repo.py` | Não usar upsert de perfil no lifecycle; preservar semântica para chamadores canônicos |
| `adapters/outbound/sqlite/harness_repo.py` | Binding, epoch, correlação, sequência e projeção idempotente |
| `adapters/inbound/mcp/tools/harness.py` | RequestContext, façades autorizadas, schemas compactos e normalização legada |
| `adapters/inbound/http/routes.py` | Mesmo service/política, rotas operacionais e respostas assíncronas |
| `adapters/inbound/mcp/server.py` | Flags, publicação, composição compartilhada; stdio sem proprietário de runtime |
| `adapters/inbound/cli/serve.py` e watchdog | Dispatcher, IPC, journal recovery, boot e shutdown/ownership |
| `migrations/` | Próximas migrações aditivas, sem reescrever 029 |
| `tests/`, `docs/`, `plans/` | Matriz, regressão, exemplos, evidências por SHA e operação |

Novos módulos sugeridos: `domain/endpoints.py`, `domain/delivery.py`, `application/endpoints.py`, `application/delivery_dispatch.py`, `application/runtime_authorization.py`, `application/harness_results.py`, `adapters/outbound/harness/registry.py`, `adapters/outbound/file/harness_journal.py` e `adapters/outbound/local_wakeup.py`. Estes nomes são propostas, não alegação de que existam.

## 8. Definição final de pronto

O trabalho estará pronto quando o mesmo agente puder manter várias conexões, continuar usando MCP, receber trabalho por uma conexão adequada, conversar com outros harnesses e ter todos esses caminhos autorizados, correlacionados e recuperáveis.

A aprovação exige provar comportamento com feature ligada e desligada, manter os quatro conectores, preservar dados, impedir retries inseguros e demonstrar o caminho completo desde a chamada autenticada até o resultado durável/handoff. Contenção temporária, mocks isolados ou nova documentação sem mudança de runtime não satisfazem a definição de pronto.
