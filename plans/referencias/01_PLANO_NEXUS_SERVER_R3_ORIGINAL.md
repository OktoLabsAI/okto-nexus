# Plano 1 — Reestruturação do Nexus Server

**Destino:** Codex no repositório `OktoLabsAI/okto-nexus`.
**Base:** `feature/v0.2.0`, HEAD confirmado nesta elaboração: `7ed52c22865a92c3768bc32508ed9e35dc5efdc3` [R01].
**Data:** 25 de setembro de 2026. **Revisão:** 3, três projetos e MCP exclusivamente HTTP direto.
**Estado:** plano de implementação; código e testes do produto não foram executados nesta elaboração.
**Associação:** Plano 2 — Connector; Plano 3 — `nexus-connector-core`.

## 1. Mandato ao Codex

> **Correção normativa r3:** MCP existe somente como HTTP direto no Nexus Server. Remover MCP stdio do Nexus; não implementar MCP stdio/HTTP, fachada ou proxy no Connector/Core. Configurar o cliente do harness não significa intermediar chamadas. Stdio nativo de runtime permanece. Esta revisão substitui r2; ver A.13.1 e J31–J34.

Reestruture o Nexus existente para conexões nativas e distribuídas sem atrito recorrente. Preserve seu domínio, dados, autenticação centrada no agente, MCP HTTP direto e garantias de entrega. Use o Core independente como dependência para executar harnesses locais; implemente a autoridade e o lado servidor do canal remoto do Connector.

Este documento substitui o Plano 1 anterior e a atribuição antiga dos contratos/biblioteca ao repositório do Connector. Não é instrução para reescrever o Nexus, criar uma camada de login de usuário ou migrar para outra stack. Leia os Anexos A e B integralmente antes de alterar contratos. O Anexo A é normativo e idêntico nos três planos.

```text
Implemente este plano no Nexus. Registre branch/HEAD/working tree efetivos;
não presuma que o SHA de referência continua sendo o mais recente.
Faça N00 antes de mudar comportamento e use contratos/wheels do projeto
nexus-connector-core. Não importe a aplicação Connector nem copie seus módulos.

Crie backlog e evidência por tarefa. Execute fases com dependências satisfeitas.
Dependência externa bloqueada não autoriza criar uma implementação paralela;
use peers de contrato para desenvolver e mantenha gates reais pendentes.

Preserve mudanças do usuário e histórico. Não use reset --hard, clean destrutivo,
force-push, publicação ou criação de repositório remoto sem autorização.
Não execute providers/contas/hosts de produção sem autorização específica.
Não marque PASS sem execução no código atual. Entregue código, testes e evidência,
não somente outro plano.
```

Criar `plans/agent-centric-connections-v2/{IMPLEMENTATION_STATUS.md,BACKLOG.json,DECISIONS.md,TEST_MATRIX.md,evidence/}`. Tarefas: `PENDING`, `IN_PROGRESS`, `BLOCKED_EXTERNAL`, `DONE`. Testes: `NOT_RUN`, `PASS`, `FAIL`; motivo de bloqueio em campo próprio. O pacote entregue inclui sementes de backlog; adapte caminhos, não os critérios obrigatórios.

## 2. Resultado esperado

Um Nexus em A, sem os binários, credenciais de providers e checkouts de B/C, coordena runtimes desses hosts por Connector. Na mesma instalação, quando existir harness local, `okto-nexus serve` hospeda o executor embutido do Core. Local e remoto usam as mesmas identidades, casos de uso, regras e normalização de eventos.

MCP HTTP existente continua funcionando sem instalar Connector. MCP stdio deve ser removido, sem caminho legado. A tela do agente oferece conexão local/remota a partir da identidade existente. Importar sua chave no Connector não exige login Nexus de pessoa nem criação de outro agente. Uma identidade pode usar MCP e runtime sem duplicar automaticamente uma entrega.

### 2.1. Contrato de experiência

| Situação | Experiência exigida |
|---|---|
| Primeiro runtime local | Escolher agente, harness/projeto quando necessário, aprovar escopo real; produto prepara o restante |
| Uso local recorrente | `okto-nexus runtime start <agente>` na pasta; reutilizar binding e sessão compatível |
| Primeiro host remoto | Na tela do agente, copiar comando do Connector; importar a chave existente, selecionar harness local e aprovar o vínculo |
| Remoto recorrente | CLI remota ou painel solicita iniciar; sem nova configuração de endpoint/perfil/token |
| Agente tem 2 hosts | Mostrar host/binding; respeitar preferência aprovada ou pedir escolha se ambíguo; nunca failover silencioso de trabalho incerto |
| Provider não autenticado | Diagnóstico acionável no executor; não solicitar segredo de provider ao Server |
| Política proíbe operação | Explicar a aprovação real necessária; não expor cinco telas técnicas para resolver um único escopo |
| Servidor com 100 mil agentes | Resolver a chave/identidade por índice; não exigir lista global de agentes para conectar um deles |

A interface avançada pode mostrar IDs, perfis e endpoints para diagnóstico. Ela não é pré-requisito do fluxo normal. Defaults não anulam negações explícitas existentes.

## 3. Baseline e lacunas

O commit foi confirmado, e `pyproject.toml`, `application/auth.py` e `application/identity.py` foram relidos nesta elaboração [R01–R04]. As demais âncoras abaixo são provenientes da revisão/plano anterior; N00 deve reproduzi-las no HEAD efetivo antes de tratá-las como defeitos ainda abertos. Não confundir este planejamento com uma nova execução de toda a suíte.

| Gap | Tratamento obrigatório |
|---|---|
| G01 — `RuntimeOpenService` constrói processo no owner de `serve` | Separar admissão de execução; `EmbeddedExecutor` ou `RemoteExecutorPort` após autorização |
| G02 — owner client de finalidade loopback/local | Manter privado; não transformar remoção de restrição em protocolo remoto |
| G03 — `project_root`/hash do path resolvidos no Server | Workspace lógico + binding físico no executor; compatibilidade aditiva |
| G04 — descoberta usa plataforma central | Inventário/capacidades do executor escolhido |
| G05 — métodos, endpoint, perfil, grants e chave manual recorrente | Fluxo por intenção com aplicação idempotente e aprovação agregada |
| G06 — UI envia apenas executável quando adapter exige argv adicional | Executável separado de argumentos; Core monta argv |
| G07 — autorização de abertura MCP por uma hora | Preservar política; vínculo aprovado + tickets curtos automáticos, sem ritual manual por sessão |
| G08 — provider home/login exigem edição técnica | Preparação pelo Core no host; nenhuma chave de provider centralizada |
| G09 — supervisor mistura processos e domínio | Extrair física para Core; Server mantém projeção, autorização e entrega |
| G10 — abrir runtime confundido com adotar conversa | Intenções `tools-only`, `managed`, `attach` explícitas |
| G11 — limites dos quatro adapters | Matriz real e qualificação via Core; sem capability fictícia |
| G12 — reconciliação remota só planejada | Journal, ACK durável, gerações, lease, resultado incerto e limites |
| G13 — MCP e runtime concorrentes | Mesmo claim/consumo exclusivo; sem duplo turno/handoff |
| G14 — dependência de ciclo de vida de stdio | Remover MCP stdio e proxies; ferramentas usam MCP HTTP direto no Server, sem fachada local |
| G15 — planos antigos concorrentes | Matriz de substituição; preservar evidência, um backlog ativo |
| G16 — desenho anterior pressupõe usuário/pareamento central de máquina | Raiz de autenticação é a chave do agente existente; máquina é entidade técnica limitada |
| G17 — chave não recuperável do hash | Importar existente; nunca reemitir silenciosamente para copiar comando |
| G18 — risco de Core dentro do Connector | Terceiro repo/wheel e dependências acíclicas |
| G19 — `start` ambíguo | Namespace `runtime` no Nexus; CLI do daemon separada no Connector |
| G20 — escala de identidades e cache sem limite | Queries indexadas, paginação, cache bounded e invalidação; não enumerar catálogo no onboarding |

## 4. Arquitetura-alvo do Server

### 4.1. Domínio preservado

`AgentKeyAuthService` continua resolvendo chave → agente. Estender sua invalidação para tickets/lanes/capabilities, sem criar resolvedor paralelo e sem gravar plaintext. `RuntimeOpenService`, `RuntimeControlService`, planejamento de entrega e dispatcher continuam pontos canônicos, agora despachando por porta de execução.

REST, MCP, CLI local e eventos do Connector chamam os mesmos casos de uso. A identidade vinda do payload jamais substitui o principal autenticado. Uma operação administrativa autorizada pode agir sobre o agente-alvo e registrar ambos os papéis; ela não entrega sua própria credencial ao processo filho.

### 4.2. Composição local/remota

`EmbeddedExecutor` adapta a API pública do Core e recebe journal/event sink/auth context. `RemoteExecutorPort` transforma operação autorizada em NXL e recebe fatos duráveis. Nenhum deles decide handoff, altera perfil do Agent ou autoriza escalada.

Importar metadados do Core não inicia binários. Um Server central sem provider instalado precisa montar API/dashboard e negociar conexões normalmente. Dependências nativas/bridge são carregadas de forma explícita, com extras automaticamente presentes nas instalações `serve`/`serve-lite` que prometem uso local.

O owner de `serve` é o proprietário do executor embutido. Shutting down o Server encerra recursos locais próprios; perder o Server não mata instantaneamente runtimes remotos, que seguem lease/disconnect policy.

### 4.3. Modelo persistente aditivo

Reutilizar tabelas/entidades existentes quando representarem corretamente o fato. Nomes abaixo são conceitos, não obrigação de duplicar tabelas:

| Conceito | Chaves/revisões e invariantes |
|---|---|
| Executor | ID canônico, tipo local/remoto, connector_id técnico, estado de controle, geração; sem user_id |
| Binding de conexão | agente + executor + adapter + template; revisão/autorização; única realização aprovada por fingerprint/intenção |
| Binding de workspace | workspace lógico + executor + handle físico/revisão; path nunca resolvido no host errado |
| Ticket | Hash/identificador opaco, subject agente/binding, epoch, expiry; segredo não persistido em plaintext |
| Operação | operation_id + intent_hash + escopo + estágio + recibo; conflito de ID/payload detectado |
| Ingresso de eventos | identidade estável/seq/hash + watermark; ACK apenas depois do commit |
| Presença | fatos derivados de sessão/controle/atividade real, separados de heartbeat do daemon |
| Aprovação | pedido/decisão, scope/revision, authority existente; CAS e expiry |

Migrar endpoints legados para executor local embutido sem alterar agent_id/workspace_id históricos. Criar índices antes de colocar novas queries no caminho quente. Backfill retomável; backups consistentes incluem WAL por método apropriado, não cópia solta de arquivo aberto. Evitar drop de colunas para permitir rollback de aplicação enquanto seguro.

### 4.4. Provisionamento por intenção

Pipeline: autenticar → resolver intenção/binding → solicitar descoberta/preparo no executor → calcular diff de confiança → aprovar quando necessário → aplicar configuração em transação → registrar intenção de abertura → despachar. `prepare` não faz spawn nem muda permissões. A UI pode encadear etapas, mas deve haver recibos idempotentes e retomada após falha parcial.

Não exigir que o usuário informe `executor_id` ou `workspace_binding_id` quando contexto/preferência já tornam a escolha inequívoca. Se aparecer outro host com configuração semelhante, não adotá-lo como substituto automático.

Permissões existentes prevalecem: a chave de agente prova identidade, não direito de habilitar método proibido. Políticas explícitas de auto-start podem autorizar entrega iniciar runtime. Um agente não pode instalar binário, alterar root ou aprovar sua própria escalada por tool call.

### 4.5. Gestão/CLI/dashboard

Na tela do agente, resumir conexões em cartões: modo, host, projeto, estado, capacidades e ação necessária. Mostrar “vinculado”, “daemon online”, “iniciando”, “runtime pronto”, “aguardando aprovação”, “resultado incerto” distintamente. Mostrar último erro sem segredos.

O botão remoto gera comando protegido para a identidade atual; nunca gera chave nova em silêncio. O local usa Core do Server e não oferece “instale Connector” como solução padrão. Retirar formulários de JSON/command/grant do caminho principal; mantê-los somente avançados quando justificáveis.

CLI de runtime: `discover`, `start`, `status`, `interrupt`, `stop`, `logs`, `doctor`, `bindings`. Operações usam os mesmos contratos/recibos da API; acompanhamento de logs não é proprietário da sessão. Erros headless possuem código e ação corretiva; UI não determina autoridade sozinha.

### 4.6. Compatibilidade que deve sobreviver

Preservar `okto-nexus serve`, MCP HTTP direto, APIs de domínio, permissões, IDs, inbox, eventos e handoffs. Remover o MCP stdio introduzido indevidamente, incluindo entrypoints, módulos, documentação, configuração e testes de manutenção; não manter shim ou fallback. Não migrar SDK MCP major como efeito deste trabalho. Novas tools de conexão devem ser compactas e não uma duplicação do CRUD de infraestrutura. Catálogo/schemas não devem crescer proporcionalmente ao número de hosts.

A2A pode usar futuramente as mesmas identidades/ports; implementar A2A completo, scheduler cloud, sincronização de código e HA de banco está fora deste plano. Não usar essas futuras possibilidades como dependências de conexão remota.

## 5. Âncoras de alteração

| Área atual | Alteração esperada |
|---|---|
| `application/auth.py`, guards de HTTP/MCP | Chave canônica, escopo self, invalidação de derivados e lane por agente |
| `application/identity.py`, `domain/ids.py` | Caminho legado adaptado; novo workspace lógico + binding físico |
| `application/runtime_open.py`, `runtime_control.py` | Retirar construção física direta; selecionar porta, preservar recibos/claims |
| `application/runtime_dispatcher.py`, `runtime_delivery.py` | Consumo exclusivo, quotas, reconciliação e geração |
| `application/endpoints.py`, `agent_connections.py`, `runtime_access.py` | Provisionamento por intenção e capacidade do executor |
| `application/harness_supervisor.py`, `adapter_registry.py` | Separar projeção canônica e adaptadores consumidos do Core |
| `adapters/outbound/harness/*` | Extração rastreada para Core; wrappers transitórios finos; remoção da cópia final |
| Rotas HTTP, composição de serve, CLI e tools MCP de harness | Contratos compartilhados e owner correto |
| Repositórios SQLite/migrações de runtime/endpoints | Dados/revisões/índices/ingresso durável |
| `AgentConnectionsPanel.tsx`, `AgentEndpointSetup.tsx`, `api.ts` | Localizar arquivos no HEAD e substituir fluxo principal |
| `pyproject.toml`, CI/build/package-data | Dependência do Core, compatibilidade e assets; sem dependência Connector |

Caminhos são âncoras da revisão, não instrução de criar arquivo duplicado se o símbolo mudou de lugar. Cada tarefa registra os caminhos reais modificados.

## 6. Plano de execução por fases

### N00 — Fixar baseline, reconciliar planos e reproduzir gaps

**Dependências:** Nenhuma; pode iniciar imediatamente.

**Superfícies/entregáveis:** Git/pyproject, plans existentes, auth/identity, adapters, UI e suíte atual.

| Tarefa | Implementação exigida |
|---|---|
| N00.1 | Registrar HEAD/branch/working tree, versões Python/MCP/schema, comandos de build e testes; preservar arquivos modificados e falhas preexistentes separadas. |
| N00.2 | Ler os dois planos anteriores, PR34 e remote-executors; criar crosswalk G01–G20 e marcar cada requisito como preservado, substituído, já implementado ou a investigar. |
| N00.3 | Inspecionar fluxo de chave, cache, middleware, operador reservado, grants e self-open; demonstrar que chave resolve agente e que emitir nova chave invalida a anterior. |
| N00.4 | Reproduzir setup local e bugs de argv/path/plataforma no HEAD; criar regressões para os confirmados, sem tratar comentários/planos como evidência de execução. |
| N00.5 | Inventariar realpath, spawn, ownership, delivery, approvals, boot e todo MCP stdio (entrypoints/config/módulos/docs/testes); medir baseline MCP HTTP e instalar backlog/status/evidência da revisão 3. |

**Gate de saída:** Baseline verificável, matriz de gaps e regressões; nenhum requisito antigo desaparece sem decisão rastreada.

**Testes vinculados:** TN-01, TN-02.

### N01 — Integrar contrato do Core e preparar migrações aditivas

**Dependências:** N00, K01

**Superfícies/entregáveis:** Domain/ports, persistence, migrations, contrato/OpenAPI.

| Tarefa | Implementação exigida |
|---|---|
| N01.1 | Consumir bundle imutável K01 com manifest/hash; integrar tipos via API pública sem manter cópia autoral de NXL no Server. |
| N01.2 | Modelar executor/binding/workspace binding, credential epoch, auth/config revision, operações e eventos; preservar IDs e serviços existentes onde possível. |
| N01.3 | Criar migrações aditivas idempotentes e índices por key hash, agente/binding/executor/workspace e operation/event IDs; definir backfill retomável. |
| N01.4 | Definir porta de execução embutida/remota, contexto autenticado e rotas do Anexo A no OpenAPI do produto; fechar validação de entrada/erro antes de efeitos. |
| N01.5 | Construir reader/writer fixtures legado-novo, testes de boundary e de conflito; registrar política de rollback e incompatibilidade de schema sem downgrade destrutivo. |

**Gate de saída:** Schema/ports e migrações passam em DB novo e legado; contrato não exige usuário Nexus nem path físico remoto no Server.

**Testes vinculados:** TN-03, TN-04, TN-05.

### N02 — Autenticação por agente e onboarding sem rotação oculta

**Dependências:** N01

**Superfícies/entregáveis:** AgentKeyAuthService, guards, binding prepare/apply/ticket, UI API.

| Tarefa | Implementação exigida |
|---|---|
| N02.1 | Implementar /connections/me utilizando o resolvedor de chave existente; comparar agent hint e negar spoofing sem enumerar agentes. |
| N02.2 | Implementar prepare/apply de binding próprio com CAS, políticas existentes e aprovação agregada; agente não pode habilitar método negado ou se autoaprovar escalada. |
| N02.3 | Emitir tickets opacos curtos escopados em agente/executor/binding/epoch e capacidades de sessão; não adicionar login de usuário nem chave raiz obrigatória de Connector. |
| N02.4 | Propagar rotação/revogação para tickets NXL, capabilities MCP HTTP diretas, caches, lanes, leases e bridges não MCP; validar cada audiência sem permitir bypass quando apenas um canal estiver conectado. |
| N02.5 | Gerar contrato de comando de conexão da tela do agente; importar chave existente por entrada protegida e nunca emitir outra para contornar hash-only; testar comando em shells suportados. |

**Gate de saída:** Mesmo agente/chave que já usa MCP configura binding remoto; nenhum novo Agent/user, segredo exposto ou MCP invalidado pela configuração.

**Testes vinculados:** TN-06, TN-07, TN-08, TN-09.

### N03 — Executor local embutido no proprietário de serve

**Dependências:** N01, K03, K04

**Superfícies/entregáveis:** Composition root serve/serve-lite, supervisor, executor port, pyproject.

| Tarefa | Implementação exigida |
|---|---|
| N03.1 | Integrar wheel incremental do Core ao serve e serve-lite; montagem de API/dashboard sem provider/binário local continua válida. |
| N03.2 | Criar EmbeddedExecutor adaptando journal/event sink/secret resolver e contexto autorizado; não usar WSS/Connector app para executar localmente. |
| N03.3 | Substituir construção nativa em RuntimeOpen/Control pelo despacho da porta; preservar recibos, reserva idempotente e claims existentes. |
| N03.4 | Separar supervisor canônico de processo físico; manter wrappers de compatibilidade temporários e eliminar duplicação de adapters após comparação rastreada. |
| N03.5 | Integrar startup/shutdown do Core ao owner de serve, contenção, readiness e cleanup; CLI/cliente MCP HTTP não são donos de runtime e nenhum processo MCP stdio inicia o Server. |

**Gate de saída:** Instalação limpa só com Nexus + dependência Core abre/encerra runtime local; nenhum daemon Connector/pareamento/WSS local obrigatório.

**Testes vinculados:** TN-10, TN-11, TN-12.

### N04 — Provisionar por intenção e separar workspaces

**Dependências:** N02, N03

**Superfícies/entregáveis:** Identity/workspace, endpoints, agent_connections, profile realization.

| Tarefa | Implementação exigida |
|---|---|
| N04.1 | Usar discovery/prepare do Core no executor certo; Server central consulta inventário remoto e nunca qualifica peer pelo próprio os.name. |
| N04.2 | Implementar criação/resolução de workspace lógico e vínculo físico local com validação no executor; manter aliases de IDs legados e compatibilidade de APIs. |
| N04.3 | Criar fluxo resolve–diff de confiança–approve/apply–start com etapas reexecutáveis; gerar endpoint/perfil/argv sem pedir ao usuário sua estrutura interna. |
| N04.4 | Reutilizar binding e sessão compatível, com ambiguidade explícita e intenção nova para --new-session; mudança de root/perfil/harness não amplia escopo silenciosamente. |
| N04.5 | Corrigir fluxo do campo Executável para consumir templates de Core; segredos/provider home são refs locais e login ausente retorna ação no host adequado. |

**Gate de saída:** Primeiro e segundo uso passam sem JSON/argv/grant manual; paths Windows remotos não são resolvidos como Linux central.

**Testes vinculados:** TN-13, TN-14, TN-15, TN-16.

### N05 — Implementar ingresso WSS e lanes autenticadas

**Dependências:** N02, K01

**Superfícies/entregáveis:** Rotas HTTP/WSS, middleware, connection registry e controle de gerações.

| Tarefa | Implementação exigida |
|---|---|
| N05.1 | Implementar upgrade WSS com TLS no deployment, ticket em header, subprotocolo nxl.v1, negociação de limites e erro antes de efeitos para versão incompatível. |
| N05.2 | Registrar connector/executor como entidades técnicas; autenticar lane inicial e binding.attach adicional com prova de agente independente por ticket. |
| N05.3 | Gerir geração/ownership de canal por CAS, reconnect, heartbeat, lease autenticado e conflito entre instâncias; não converter WSS ativo em runtime pronto. |
| N05.4 | Implementar inventory snapshot/delta, filtros por binding e estado de controle; não aceitar atualização global de identidade/permissões vinda do executor. |
| N05.5 | Adicionar prioridades, limites de bytes/frames, redaction e backpressure; validar proxy reverso e fechamento/deauth por agente sem conceder outra lane. |

**Gate de saída:** Peer de contrato prova WSS bidirecional autenticado e isolamento de lanes; teste real com Connector é gate posterior, não presumido.

**Testes vinculados:** TN-17, TN-18, TN-19, TN-20.

### N06 — Entrega durável, ingresso de eventos e reconciliação

**Dependências:** N03, N05

**Superfícies/entregáveis:** Runtime delivery/dispatcher, operations repo, events ingress e outbox.

| Tarefa | Implementação exigida |
|---|---|
| N06.1 | Reservar operação/outbox com ID/hash antes do envio; mesma intenção retorna recibo, payload conflitante é negado; rede/spawn nunca dentro da transação. |
| N06.2 | Ingressar eventos com identidade/sequence/hash e ACK pós-commit; projetar fatos idempotentemente e lidar com terminal antes de ACK intermediário. |
| N06.3 | Reconciliar cursores, operações, sessões e ownership após reconnect/restart; conservar unknown e evitar repetição automática ou realocação para outro executor. |
| N06.4 | Aplicar mecanismo de consumo exclusivo comum a MCP/local/remoto; preservar quotas, leases, causalidade e budgets ao reconectar. |
| N06.5 | Testar queda em cada fronteira de commit/envio/aceitação/evento/ACK, evento atrasado e geração antiga; diferenciar evidência histórica de autoridade ativa. |

**Gate de saída:** Sem trabalho duplicado por transporte/reconnect; ACK só após durabilidade e unknown nunca reclassificado como retry seguro sem prova.

**Testes vinculados:** TN-21, TN-22, TN-23, TN-24, TN-25.

### N07 — Ferramentas diretas, bridges nativas não MCP e governança

**Dependências:** N06, K09

**Superfícies/entregáveis:** Casos de uso inbox/handoff/approval, auth de MCP HTTP direto, capability de sessão e backend de bridge nativa não MCP.

| Tarefa | Implementação exigida |
|---|---|
| N07.1 | MCP HTTP do Server e bridges nativas não MCP chamam os mesmos casos de uso; Core não importa MessageService nem concede grants. Não criar fachada MCP local/remota. |
| N07.2 | Emitir capability de sessão aceita diretamente pelo MCP HTTP com agente/workspace/binding/sessão/ações/validade; qualificar renovação e expiração sem proxy/hot-reload presumido, nem chave administrativa no harness. |
| N07.3 | Distinguir fim de turno de handoff complete; preservar claim, reply target, contexto, evidência, root/parent/correlation e orçamento de relay. |
| N07.4 | Normalizar pedidos HITL com sessão/turno/request/geração/expiry; aplicar decisão uma vez por CAS e validar autoridade existente de aprovador. |
| N07.5 | Classificar execute_work somente após caminho de ferramentas comprovado; MCP HTTP direto é padrão para cliente compatível. Pi sem esse cliente usa extensão nativa não MCP qualificada, nunca servidor/proxy MCP. |

**Gate de saída:** Trabalho nativo local/remoto tem mesma governança MCP; approval negada/tardia não executa e turno final não conclui handoff sozinho.

**Testes vinculados:** TN-26, TN-27, TN-28, J34.

### N08 — API, MCP e CLI compactos e consistentes

**Dependências:** N04, N07

**Superfícies/entregáveis:** MCP tools/resources, HTTP APIs, CLI runtime e owner client.

| Tarefa | Implementação exigida |
|---|---|
| N08.1 | Expor operações por intenção nas superfícies existentes, compartilhando validação/autorização; evitar tool por host/adapter/CRUD interno. |
| N08.2 | Implementar namespace CLI runtime com discover/start/status/interrupt/stop/logs/doctor e recibos JSON; não sobrecarregar start como daemon e harness. |
| N08.3 | Remover MCP stdio, entrypoints e shims legados do Nexus; migrar configuração selecionada para MCP HTTP direto sem rotação de key/novo agente. Preservar outras entradas e SDK major; roots/hints não autorizam filesystem/identidade. |
| N08.4 | Gerar configuração do cliente MCP HTTP para a URL do Server e capability limitada de sessão, inclusive local nativo. Não exigir Connector ou publicar fachada/backend MCP adicional; validar alcance a partir do harness/sandbox. |
| N08.5 | Medir catálogo/tokens antes/depois e corrigir crescimento desnecessário; erros de auth/projeto/unknown são prescritivos sem rotinas manuais de grants. |

**Gate de saída:** API/CLI/MCP HTTP compartilham domínio; MCP stdio foi removido sem shim. Cliente HTTP acessa o Server diretamente, inclusive local, sem instalação adicional e sem catálogo por conexão.

**Testes vinculados:** TN-29, TN-30, TN-31, J31, J32.

### N09 — Substituir configuração técnica no dashboard

**Dependências:** N02, N04, N08

**Superfícies/entregáveis:** AgentConnectionsPanel, AgentEndpointSetup, cliente API e testes UI.

| Tarefa | Implementação exigida |
|---|---|
| N09.1 | Criar visão por agente com local/remoto/tools-only/managed/attach e host/projeto/status; não adicionar painel de conta de usuário Nexus. |
| N09.2 | Implementar gerar comando protegido para Connector e fluxo local nativo; renderizar política/aprovação agregada em linguagem de intenção. |
| N09.3 | Retirar JSON, nomes/IDs de endpoint/perfil, argumentos e token de uma hora do caminho normal; avançado apenas para diagnóstico e opções justificadas. |
| N09.4 | Implementar start/reuse/interrupt/stop/inspeção/logs com recibos e estado de operação; timeout não dispara nova sessão automaticamente. |
| N09.5 | Mostrar desconhecido/offline/auth_required/drift/approval por camada e capabilities reais; testar UI em locale/shell/path com espaços e preservação de config MCP. |

**Gate de saída:** Jornada first-use/second-use verificável, sem reemissão de chave ou confusão entre conversa já aberta e runtime headless.

**Testes vinculados:** TN-32, TN-33, TN-34.

### N10 — Segurança, revogação e falhas adversariais

**Dependências:** N05, N06, N07

**Superfícies/entregáveis:** Threat model, fault injection, cache/authorizer, ingress limits.

| Tarefa | Implementação exigida |
|---|---|
| N10.1 | Executar testes de spoof de agente/Server/executor, replay de ticket, lane não autenticada, mutation de escopo e tentativa de plugin/shell remoto. |
| N10.2 | Validar invalidation de chave em trânsito e revogação durante turno/approval; impedir renovação após revogação e mostrar limite real de partição/lease. |
| N10.3 | Exercitar frame/journal flood, slow consumer, disco cheio e controle urgente; recursos finitos e isolamento por binding/Server são obrigatórios. |
| N10.4 | Validar restart do owner, morte do executor local e reconnect remoto com operações desconhecidas; não converter heartbeat em prova de processo vivo/morto. |
| N10.5 | Auditar logs/metrics/export/UI para secrets e roots indevidos; separar dados históricos de geração antiga de nova autoridade e registrar findings resolvidos. |

**Gate de saída:** Matriz negativa passa em domínio e wire; nenhuma simplificação remove sandbox, identidade, approval ou incerteza.

**Testes vinculados:** TN-35, TN-36, TN-37.

### N11 — Escala, migração operacional e limpeza de legado

**Dependências:** N09, N10

**Superfícies/entregáveis:** Índices/cache, bench, migrations/backfill e docs legadas.

| Tarefa | Implementação exigida |
|---|---|
| N11.1 | Executar cenário sintético de 100 mil agentes sem providers: onboarding por key index, paginação, sem full enumeration ou estruturas por identidade offline. |
| N11.2 | Limitar cache positivo por tamanho/TTL com invalidação síncrona; medir touch/queries no hot path e evitar escrita por delta de streaming. |
| N11.3 | Migrar instalação legada, permissões e endpoints para executor local; comparar dados/IDs/inbox/handoff antes/depois e retomar backfill interrompido. |
| N11.4 | Remover código nativo duplicado após paridade, referências ao Core hospedado no Connector e onboarding user-centric; marcar planos antigos superseded preservando evidência. |
| N11.5 | Entregar runbooks de backup/restore/rollback e upgrade com drain; não indicar downgrade de schema irreversível como seguro. |

**Gate de saída:** Histórico/negações preservados; busca de identidade não escala linearmente com catálogo; um único owner de adapters.

**Testes vinculados:** TN-38, TN-39, TN-40.

### N12 — Build de integração e gate local completo

**Dependências:** N03, N08, N11, K11

**Superfícies/entregáveis:** Wheels, CI, serve/serve-lite install, releases e documentação.

| Tarefa | Implementação exigida |
|---|---|
| N12.1 | Gerar wheel/sdist de Nexus com dependência Core versionada e assets corretos; instalação limpa sem clone do Connector. |
| N12.2 | Rodar suíte unitária/contrato/migração e gate local com Core real; registrar versões dos harnesses e capacidades testadas por SO. |
| N12.3 | Validar Server central sem binários/providers/dirs, preparando artefato para campanha remota; falhas locais do provider não impedem serving de modo remoto. |
| N12.4 | Publicar documentação de API/CLI/UX e matriz de compatibilidade, sem comandos fictícios marcados como já existentes antes da implementação. |
| N12.5 | Entregar build imutável de integração, SHA e hash para C11/N13; preparar release/rollback sem publicar automaticamente. |

**Gate de saída:** Artefato local funcional e reproduzível, pronto para teste cruzado; release distribuído permanece bloqueado até campanha conjunta.

**Testes vinculados:** TN-41, TN-42.

### N13 — Aceite conjunto dos três projetos

**Dependências:** N12, C10, K11

**Superfícies/entregáveis:** Topologia A/B/C, testes J e release evidence.

| Tarefa | Implementação exigida |
|---|---|
| N13.1 | Montar Nexus A sem runtimes e hosts B/C com Connector/Core, ao menos uma combinação heterogênea; incluir cenário Nexus local separado. |
| N13.2 | Executar J01–J34 com SHAs e wheels reais; fakes não contam nos casos explicitamente multi-host/provider/SO. |
| N13.3 | Validar first-use/second-use, chave MCP reutilizada, mesma identidade, múltiplos bindings e ausência de usuário Nexus em todas as superfícies. |
| N13.4 | Injetar partições/restart/revogação/ACK perdido e provar não duplicação, cleanup e governança; registrar limitações por capacidade real. |
| N13.5 | Consolidar matriz conjunta idêntica à do Connector/Core, blockers e release checklist; concluir somente gates demonstrados sem merge/publicação implícitos. |

**Gate de saída:** Mesma evidência fecha N13/C11 e qualificação consumidora do Core; nenhuma declaração distribuída completa apenas com localhost/mocks.

**Testes vinculados:** TN-43, TN-44, TN-45, J01, J02, J03, J04, J05, J06, J07, J08, J09, J10, J11, J12, J13, J14, J15, J16, J17, J18, J19, J20, J21, J22, J23, J24, J25, J26, J27, J28, J29, J30, J31, J32, J33, J34.

## 7. Matriz de testes específica

Todos os casos começam `NOT_RUN`. Testes de contrato/unitários e testes reais possuem registros separados quando dependem de ambientes diferentes. Nenhuma inferência a partir de mocks encerra gate nativo/multi-host.

| ID | Caso | Preparação/ação | Resultado exigido |
|---|---|---|---|
| TN-01 | Baseline | Executar build/testes existentes no HEAD efetivo e comparar com referência. | Falhas anteriores separadas; novos testes de regressão rastreados. |
| TN-02 | Crosswalk | Comparar dois planos antigos, PR34 e remote-executors com G01–G20. | Todo requisito preservado/substituído/descartado tem justificativa; sem dois backlogs concorrentes. |
| TN-03 | Migração nova/legada | Aplicar migrações em DB vazio e snapshot legado, repetir e interromper backfill. | Retomada idempotente; agent/workspace IDs e histórico preservados. |
| TN-04 | Contrato único | Alterar hash/schema de consumidor e tentar major incompatível. | CI/negociação detecta divergência antes de efeitos. |
| TN-05 | Boundary | Importar Server sem Connector/provider local; inspecionar árvore de imports. | Server funciona; física nativa só no Core e sem ciclos de dependência. |
| TN-06 | Identidade chave | Autenticar A e enviar hint/payload com agent_id B. | Negação antes de bind/spawn; nenhum Agent criado ou identidade alterada. |
| TN-07 | Importação sem rotação | Configurar Connector com chave já usada por MCP; chamar MCP novamente. | Mesma identidade e chave continuam válidas; issue_key não é acionado. |
| TN-08 | Revogação e dois canais | Rotacionar/revogar key e capability MCP HTTP com WSS/HTTP ativos ou particionados separadamente. | Invalidação/expiry bloqueiam efeitos da sessão em qualquer caminho; tickets NXL não ampliam escopo MCP. |
| TN-09 | Self permission | Agente autenticado tenta bind/grant de outro ou habilitar método negado. | Políticas existentes preservadas; nenhum autoapprove de escalada. |
| TN-10 | Local nativo | Instalar Nexus + Core, sem aplicação Connector, e abrir Codex qualificado local. | Serve hospeda executor e controla runtime sem WSS/pareamento local. |
| TN-11 | Owner local | Duas CLIs e cliente MCP HTTP pedem abertura com mesma chave idempotente; fechar clientes. | Owner único e execução idempotente; runtimes independentes continuam, sem processo MCP stdio. |
| TN-12 | Shutdown Server | Encerrar serve com runtime próprio e alvo externo anexado. | Core drena/encerra árvore própria e desanexa externo; relatório por sessão. |
| TN-13 | Path remoto | Server Linux recebe vínculo de diretório Windows validado pelo Connector. | Nenhum realpath/isdir local sobre path remoto; identidade lógica correta. |
| TN-14 | Workspace equivalência | Mesmo Git/path em hosts diferentes e manifesto falsificado. | Não mescla/autoriza automaticamente; binding explícito e escopado. |
| TN-15 | Setup sem argv | Selecionar binários Codex/Pi com espaços via UI normal. | Core adiciona argumentos obrigatórios; usuário não edita JSON. |
| TN-16 | Reuso e drift | Repetir start aprovado, depois trocar root/binário/permissão. | Primeiro reutiliza; mudança relevante exige reprepare/approval, não expansão silenciosa. |
| TN-17 | Canal WSS | Negociar TLS/protocolo com peer e depois Connector real. | Saída remota bidirecional, sem callback/porta entrante no host. |
| TN-18 | Lanes | Autenticar lane A; tentar operações B; anexar B com própria prova. | B só disponível após ticket válido; revoke A não empresta sua autoridade a B. |
| TN-19 | Instâncias concorrentes | Abrir canais conflitantes da mesma instalação e reenviar geração antiga. | CAS/fencing impede dois owners ativos ou takeover silencioso. |
| TN-20 | Controle sob carga | Inundar texto enquanto chega interrupt/revoke. | Limites/priority preservam controle; métricas de fila em bytes disponíveis. |
| TN-21 | Idempotência | Repetir operation_id/hash e depois alterar payload. | Primeiro devolve recibo sem efeito novo; segundo OPERATION_CONFLICT. |
| TN-22 | ACK durável | Cair antes/depois do commit de evento e antes do ACK. | Replay deduplicado; watermark só confirma persistido. |
| TN-23 | Unknown | Perder confirmação depois de write possível no harness. | OUTCOME_UNKNOWN consultável; nenhum novo turno/host automático. |
| TN-24 | Consumo exclusivo | MCP pull, runtime local e remoto competem pela mesma entrega. | Um consumidor de execução; outbox não cria outra tarefa. |
| TN-25 | Eventos fora de ordem | Terminal chega antes de ACK, duplicatas/gaps/geração antiga. | Reducer conserva fatos; gaps explícitos; histórico não autoriza novo efeito. |
| TN-26 | Ferramentas canônicas | Executar via MCP HTTP direto local/remoto e bridge nativa não MCP com o mesmo agente. | Mesmos casos de uso/grants/claims e auth; nenhum proxy/fachada MCP no caminho. |
| TN-27 | Handoff | Finalizar turno sem complete governado e depois emitir complete válido. | Primeiro não completa handoff; segundo preserva evidência/correlação/budget. |
| TN-28 | HITL | Duas interfaces decidem, chega decisão tardia e agente tenta se autoaprovar. | CAS único, turno/request corretos e autoridade existente exigida. |
| TN-29 | MCP HTTP e remoção stdio | Upgrade com MCP HTTP e antiga entrada Nexus stdio selecionada; invocar entrypoint removido. | HTTP preservado; migração orientada sem key nova; stdio ausente/erro prescritivo sem transporte ou shim; outras entradas intactas. |
| TN-30 | Superfície compacta | Comparar catálogo/schema/tokens com baseline e adicionar muitos hosts. | Catálogo não replica tools por conexão; diferença justificada/medida. |
| TN-31 | CLI consistente | Start/status/interrupt/stop/logs com JSON e timeout. | Mesmo domínio/recibo da API; timeout de espera não reenfileira efeito. |
| TN-32 | UI primeiro/segundo uso | Completar fluxo local e remoto duas vezes. | Sem endpoint/profile/JSON/token manual recorrente; escopo compreensível. |
| TN-33 | Modo explícito | Escolher tools-only, managed e attach. | UI informa sessão criada/reutilizada/anexada; não promete adotar conversa atual. |
| TN-34 | Estados honestos | Daemon online, provider ausente, approval pendente e resultado unknown. | Cada condição aparece distintamente; nenhuma marcada como runtime pronto. |
| TN-35 | Input hostil | Enviar paths/plugins/argv/env e identidade forjados pelo wire. | Validação/autoridade impede execução/configuração fora do binding. |
| TN-36 | Partição/lease | Desconectar runtime durante revoke; alterar relógio; restaurar canal. | Sem novas autorizações offline; limite de lease respeitado e reconciliação anterior à admissão. |
| TN-37 | Secrets | Inspecionar logs/UI/exports/headers de erro/métricas. | Sem chave/ticket/provider secret; cardinalidade de labels limitada. |
| TN-38 | 100 mil identidades | Sem provider, popular 100 mil agentes e conectar um por chave. | Lookup indexado e retorno escopado; nenhuma enumeração global ou thread por agente. |
| TN-39 | Cache bounded | Exercer muitas chaves e revogar em cache; simular churn. | Memória limitada e invalidação síncrona; epoch não permanece autorizado. |
| TN-40 | Rollback dados | Restaurar snapshot/versão suportada após backfill e execução controlada. | Dados e políticas preservados; rollback inseguro recusado/explicado. |
| TN-41 | Build limpo | Instalar wheel Nexus serve/serve-lite e Core fixado sem clones irmãos. | Assets/dependências corretos e modo local disponível. |
| TN-42 | Server sem harnesses | Subir A sem binários, provider keys ou diretórios de B/C. | API/recepção remota funcionam; não solicita instalação local de provider. |
| TN-43 | Multihost | Executar campanha J com A/B/C e mesmo Core wheel. | Controles/eventos/HITL e identidade independem do host central. |
| TN-44 | Fault conjunto | Executar partições, crash e ACK perdido nos três artefatos reais. | Resultados correspondem a efeitos possíveis e sem execução duplicada. |
| TN-45 | Release gate | Revisar evidências com SHAs/versões e casos ainda NOT_RUN. | Somente capacidades demonstradas qualificadas; bloqueios externos explícitos. |

## 8. Migração, liberação e definição de pronto

### 8.1. Estratégia de migração

Primeiro adicionar esquema/ports com leitura do legado. Em seguida integrar Core no modo local com regressões de equivalência. Só depois habilitar bindings/canal remoto conforme autorização. Migração associa endpoints existentes ao executor embutido e mantém suas negações/limites. Não substituir IDs históricos de workspace/agent por novos hashes e não apagar chaves para forçar onboarding.

Feature flags podem proteger rollout técnico, mas não virar seis novos passos obrigatórios de configuração. Defaults de instalações novas não anulam políticas existentes. A migração nunca habilita ambiente irrestrito para fazer o adapter passar.

Rollback antes de efeitos novos usa snapshot consistente e binário compatível. Depois de operações remotas, reconciliar/drain antes de voltar binário; não eliminar journal/eventos para fazer schema antigo abrir. Documentar pontos sem downgrade seguro e recovery correspondente. Não redesenhar HA/SQLite distribuído nesta entrega.

### 8.2. Definition of Done do Server

Server local funciona sem aplicativo Connector e usa o mesmo Core qualificado que o remoto. Server remoto funciona sem binários/credenciais/providers/paths de projetos. Agente conserva sua identidade e chave; onboarding não cria usuário e não rotaciona key sem decisão explícita. Endpoints/perfis/argv/tickets são resolvidos pelo produto, enquanto permissões e aprovações reais permanecem.

MCP HTTP direto e histórico continuam; MCP stdio e qualquer shim foram removidos; consumo exclusivo, handoff, eventos e reply routing não regrediram. Operações incertas não repetem por timeout/reconnect; duas lanes não representam outra identidade sem prova. UI/CLI distinguem camadas/modes e o encerramento é supervisionado. G01–G20 têm desfecho evidenciado.

N00–N12 concluídos não bastam para anunciar capacidade distribuída qualificada: N13/C11/J dependem dos artefatos reais. Quando um provider/host não estiver disponível, entregar mudanças independentes e declarar gate BLOCKED_EXTERNAL; não substituir por PASS sintético.

### 8.3. Entrega final do Codex

Código/migrações/assets; testes executados e falhas/bloqueios; wheels/hashes; documentação de uso/upgrade/recuperação; matriz de compatibilidade; crosswalk dos planos antigos; lista dos wrappers/cópias removidos; evidência dos SHAs de três projetos. Apresentar caminho comum local/remoto executável e exemplos sem segredo. Commit/PR/publicação seguem autorização do operador do repositório.

---

# Anexo A — Contrato comum dos três projetos

**Revisão normativa:** `nxl-1-agent-centric-http-only-2026-09-25-r3`.
**Status:** especificação de implementação, não protocolo já disponível.
**Fonte única futura:** repositório independente `nexus-connector-core`, em `contracts/nxl/v1/`. Os três planos reproduzem este anexo a partir do mesmo texto; o manifesto do pacote registra seu SHA-256.

## A.1. Decisões que não podem ser reinterpretadas

1. O sujeito de colaboração e autorização do Nexus é o **agente canônico**. Não introduzir cadastro, login, tenant ou propriedade por usuário humano para fazer o Connector funcionar. A conta do sistema operacional que executa um serviço é apenas uma fronteira local de permissões.
2. A chave de agente já utilizada pelo MCP autentica a mesma identidade no onboarding remoto. Importar uma chave não cria um agente; escolher Codex/Pi/Claude não troca seu `agent_id`. Um identificador de Connector/executor não é um novo agente nem uma chave mestra.
3. O Nexus Server usa `nexus-connector-core` diretamente para runtimes locais. Não depende da aplicação Connector, de pareamento remoto ou de WSS em loopback. O Connector usa a mesma biblioteca para runtimes remotos.
4. Core é **terceiro projeto e distribuição Python independente**, não subpasta publicada a partir do Connector. A distribuição proposta é `nexus-connector-core`; o import é `nexus_connector_core`. Confirmar disponibilidade dos nomes antes de publicação autorizada; não mudar o limite arquitetural por conflito de nome.
5. O Connector inicia WSS para o servidor. O canal é bidirecional e controla runtimes. O único MCP do produto é o **MCP HTTP direto no Nexus Server** (Streamable HTTP compatível com o SDK/protocolo adotado). HTTPS do Connector atende autenticação/configuração, operações consultáveis, recursos e APIs canônicas não MCP; não encaminha MCP. WSS NXL não transporta nem encapsula MCP. SSE do dashboard e mecanismos HTTP existentes não precisam ser removidos.
6. `agent_id`, conexão, sessão de runtime e conversa nativa são entidades diferentes. A mesma identidade pode usar vários meios; isso não concede memória compartilhada, concorrência irrestrita ou execução duplicada de uma entrega.
7. Inbox, outbox canônica, handoffs, identidades, grants e decisões de aprovação ficam no Server. O journal técnico do executor não é outra inbox nem autoriza trabalho offline.
8. O caminho comum é configurar uma vez, reutilizar depois. Não exigir JSON, argumentos nativos, IDs de endpoint/perfil ou renovação manual de tickets por sessão. Decisões reais de segurança, instalação ausente, login de provider e mudança de escopo continuam explícitas.
9. Não desfazer trabalho posterior na branch, mudar licença, publicar pacotes ou criar repositórios remotos como efeito implícito de implementar estes planos.
10. **Remover o MCP stdio introduzido na v0.2.0 do Nexus; não preservar como legado, opcional ou fallback.** Connector e Core não oferecem servidor, fachada, proxy ou relay MCP, seja stdio ou HTTP. Quem consome MCP HTTP se conecta ao Nexus Server diretamente, inclusive no modo local.
11. Stdio de protocolos nativos de runtime permanece permitido. O transporte stdin/stdout de um adapter não se torna MCP por compartilhar esse mecanismo. Não apagar adapters nativos ao retirar o MCP stdio.
12. Configurar automaticamente o cliente MCP HTTP do harness não é intermediar suas chamadas. Nenhuma chamada MCP pode depender de processo-fachada, porta MCP do Connector, IPC do daemon ou túnel NXL. Clientes sem suporte HTTP não recebem fallback MCP stdio; diagnosticar a capacidade não suportada.

## A.2. Repositórios, dependências e responsabilidades

| Projeto | Conteúdo obrigatório | Conteúdo proibido |
|---|---|---|
| `OktoLabsAI/okto-nexus` | Domínio canônico; admissão/autorização; roteamento; executor embutido; ingresso WSS; API/MCP HTTP/CLI/dashboard; migração e remoção de MCP stdio | Implementação paralela dos protocolos nativos; dependência da aplicação Connector; resolução de paths remotos no host central; servidor MCP stdio ou shim de compatibilidade |
| `okto-nexus-connector` — novo repositório proposto | CLI; daemon; serviço de SO; armazenamento das credenciais importadas; IPC privado; cliente WSS/HTTPS para gestão; configuração do cliente MCP HTTP direto do harness | Cadastro de agentes independente; autorização de handoff offline; cópia dos adapters ou do kernel; login de usuário Nexus; servidor/fachada/proxy/relay MCP de qualquer transporte |
| `nexus-connector-core` — novo repositório | Tipos/contratos NXL; descoberta; templates; adaptadores; supervisão física; journal técnico; normalização; configuração declarativa de MCP HTTP direto; bridges nativas não MCP | Servidor Nexus; UI; daemon; autenticação canônica; WSS/HTTP de produto; política de inbox/handoff; implementação de servidor/proxy MCP ou extra MCP de fachada |

Dependências de instalação: `Nexus → Core` e `Connector → Core`. O Core não importa nenhuma das aplicações. O Server nunca importa o Connector. O Core não possui efeito colateral de abrir portas, iniciar threads/processos ou ler credenciais ao ser importado.

A implementação dos clientes WSS e das rotas HTTP pertence às aplicações; modelos, codecs, reducers e fixtures são compartilhados no Core. O armazenamento técnico possui uma implementação SQLite de referência no Core, via porta substituível. No modo embutido, o Server pode adaptar seu próprio UoW para evitar cópias desnecessárias; não misturar efeitos de processo/rede dentro de transações SQL.

## A.3. Identidade, chave e credenciais: significado exato

| Elemento | Significado e autoridade |
|---|---|
| `server_id` | Identidade persistida da instalação Nexus; não inferida somente do hostname |
| `agent_id` | Identidade canônica já existente; determinada pela credencial autenticada, não pelo JSON |
| Chave canônica do agente | A mesma credencial usada pelo MCP; armazenada no cofre local do Connector quando importada; só enviada ao servidor autorizado |
| `connector_id` | Identificador técnico persistente da instalação remota; não autentica nada por si só |
| `executor_id` | Local de execução cadastrado pelo Server; pode ser embutido ou remoto; admite apenas bindings autorizados |
| `binding_id` | Vínculo entre agente, executor, adaptador e intenção de configuração aprovada |
| `workspace_id` | Escopo lógico canônico de colaboração |
| `workspace_binding_id` | Vínculo do workspace com um diretório validado em um executor |
| `session_id` | Sessão governada de runtime; não substituir IDs de sessões históricas sem migração explícita |
| `native_session_id` / `native_turn_id` | Identificadores do protocolo do harness, subordinados à sessão governada |
| Ticket operacional | Segredo curto e limitado, emitido após autenticar a chave do agente; não nova identidade nem chave administrativa |
| Capability de sessão | Autorização limitada para MCP HTTP direto ou ações nativas não MCP; o Server valida agente, sessão e escopo. Nunca a chave canônica dentro do prompt |
| Credencial do provider | Login/API key do Codex/Claude/Pi, diferente da chave Nexus; permanece no host do harness |

O Server inspecionado guarda hash e retorna plaintext apenas ao emitir/rotacionar a chave [R03]. Portanto, **não é possível recuperar a chave atual a partir do hash**. A tela nunca deve rotacioná-la para montar um comando de conexão sem informar e obter a autorização já exigida pela gestão de chaves. Isso quebraria os MCPs que usam a chave anterior.

O fluxo obrigatório aceita importação protegida da chave existente, inclusive de uma entrada MCP explicitamente selecionada pelo operador. Não varrer arquivos, keychains ou históricos procurando segredos. Descobrir instalações/configurações candidatas não equivale a descobrir ou conceder credenciais.

Não tornar par de chaves de máquina, OAuth de usuário, SSO, conta de operador ou segunda chave persistente de agente pré-requisitos desta versão. Tickets de transporte e capabilities de sessão são detalhes internos, renovados enquanto a chave, o agente e o vínculo continuarem válidos. Rotação/revogação da chave canônica exige nova credencial válida: isso não pode ser reparado por uma renovação automática que contorne a revogação.

Preservar as superfícies administrativas existentes, inclusive eventual identidade reservada de operador. Isso não cria entidade de usuário Nexus nem autoriza entregar credencial administrativa aos harnesses.

## A.4. Fluxos normativos de configuração e uso

### A.4.1. Remoto: comando do agente para o Connector

A tela de um agente existente oferece “Conectar harness em outra máquina”. Gera comando adequado ao shell com endereço e hint do agente, sem embutir chave de longa duração em argv:

```bash
okto-nexus-connector connect --server https://nexus.exemplo --agent ag_123
```

O comando é proposto para implementação. A CLI pede a chave em entrada mascarada, aceita `--credential-stdin` para automação segura ou uma entrada MCP escolhida explicitamente. Se a interface possui a chave em memória no momento legítimo de emissão/importação, pode oferecer transferência protegida; isso não pode exigir persistir plaintext no Server nem simular recuperação do hash. O caminho garantido é chave existente por entrada protegida; não é obrigatório construir um broker de transferência de segredos nesta entrega.

O Connector valida TLS/origem, resolve `/me` pelo mecanismo de chave existente e compara a identidade retornada com o hint. Em divergência, aborta: não muda o alvo nem registra novo agente. Não baixa uma lista global de agentes. Descobre binários/configurações locais, pede seleção quando houver ambiguidade, resolve o projeto atual e apresenta **uma confirmação agregada** de agente + harness + host + projeto + permissões. Configuração técnica, perfil e endpoint são gerados de modo idempotente.

A chave é guardada como referência em cofre local, namespaced por `server_id + agent_id`; aliases são apenas nomes locais. Várias identidades podem apontar para a mesma instalação de Codex, mantendo sessões/ambientes isolados. O mesmo agente pode ter bindings distintos aprovados; isso não habilita broadcast de trabalho a todos.

`connect` pode iniciar o daemon automaticamente. Não inicia um harness apenas por descobrir ou importar a chave. `--start` ou a escolha explícita “conectar e iniciar” acrescenta a intenção de abrir runtime.

Uso recorrente, dentro da pasta do projeto:

```bash
okto-nexus-connector runtime start meu-codex
```

Sem novo cadastro, JSON ou emissão de chave. Uma troca de diretório exige apenas o consentimento definido pela política de roots, não toda a configuração novamente. Em headless, não escolher silenciosamente um agente/harness ambíguo; retornar erro acionável.

### A.4.2. Local nativo

```bash
okto-nexus serve
# Em outro terminal, no projeto:
okto-nexus runtime start ag_123 --harness codex
```

A CLI utiliza o proprietário local existente, autenticado pelo mecanismo administrativo/IPC local já confiável, e o Server produz uma execução **como o agente escolhido**, com verificação de permissões e auditoria. Não pedir que o Server recupere uma chave cujo plaintext não possui. A chave administrativa não é repassada ao runtime; gerar capability de sessão limitada.

Subcomandos de runtime podem reutilizar `--ensure-server` explicitamente aprovado para iniciar o Server quando ausente; não ativar um listener público ou configurar autostart como efeito de uma chamada MCP. Instalar o Core como dependência de `serve` e `serve-lite`; nada de instalar/parear o aplicativo Connector no mesmo host.

### A.4.3. Três intenções diferentes

`tools-only`: o próprio harness acessa diretamente o MCP HTTP do Nexus Server; não exige instalar ou executar Connector/Core. O Connector pode ajudar a escrever essa configuração, mas não participa de suas chamadas. `managed`: iniciar/reutilizar processo e sessão administrados pelo Core. `attach`: conectar-se a uma sessão existente apenas por mecanismo suportado e aprovado. A UI mostra qual ocorreu; configurar MCP HTTP não adota a conversa nativa nem transfere sua memória.

## A.5. Autorização e multiplexação no canal remoto

A autenticação de agente reaproveita o guard existente. Propor rotas HTTP abaixo, adaptando ao prefixo real sem manter serviços duplicados:

| Método/rota proposta | Entrada e efeito |
|---|---|
| `GET /v1/connections/me` | Chave de agente; retorna só identidade autenticada, permissões de conexão e revisões pertinentes |
| `POST /v1/connections/bindings:prepare` | Intenção própria, executor técnico e inventário redigido; proposta sem spawn |
| `POST /v1/connections/bindings:apply` | Proposta, revisão e aprovação autorizada; cria/reutiliza binding/endpoint/perfil em transação |
| `POST /v1/connections/bindings/{id}/ticket` | Chave do mesmo agente; ticket curto limitado ao binding e ao executor |
| `POST /v1/runtime/intents:resolve` | Binding/projeto/intenção; retorna plano de realização e status, sem executar |
| `POST /v1/runtime/operations` | Operação idempotente autorizada; 202 + recibo durável ou resultado já conhecido |
| `GET /v1/runtime/operations/{id}` | Consulta escopada; não reenvia um efeito |
| `GET /v1/runtime/executors/{id}/link` | Upgrade WSS, autenticado com ticket; subprotocolo `nxl.v1` |
| `POST /v1/runtime/approval-decisions` | Decisão autorizada e correlacionada a pedido pendente; CAS |

O Server deriva o `agent_id` da autenticação; campos de payload são hints ou assertions comparadas, nunca substitutos. Criação automática de binding só é permitida para a própria identidade e segundo políticas existentes. Ter a chave identifica o agente, mas não concede sandbox mais amplo nem desativa negações explícitas.

Por instalação/executor e Server, manter preferencialmente um WSS com lanes lógicas por binding. O primeiro ticket autentica a abertura; `binding.attach` adiciona outra lane **somente com ticket obtido pela chave daquele agente**. O canal inicialmente não conhece outros agentes. Revogar A remove autoridade de A sem conceder B nem derrubar suas sessões por acidente. Tickets não aparecem em URLs, logs, snapshots, métricas ou journal; a mensagem de attach é classificada como sensível e redigida.

Um daemon pode atender múltiplos Servers, com canais, cofres, namespaces, quotas e processos isolados por `server_id`. A implementação inicial deve suportar ao menos dois perfis de servidor na mesma máquina, sem trocar um pelo outro nem duplicar daemon. Não compartilhar credenciais entre origens; redirects de credenciais para outra origem são recusados.

Persistir `credential_epoch` e `authorization_revision` de cada binding; revogação/rotação cancela emissão e uso de tickets antigos, marca sessões sem autoridade e interrompe novas admissões. No Server online, invalidação síncrona alcança cache, lanes WSS e capacidades delegadas. Na partição, o limite é o lease local, não uma promessa de revogação instantânea.

## A.6. Workspace lógico e realização local

O path físico só é resolvido pelo host que o possui. O vínculo armazena `workspace_id`, `executor_id`, `workspace_binding_id`, `binding_revision`, root canônico local e evidência de validação. Root pode ser mantido no executor e representado por handle no Server; se for exibido, respeitar permissão e redigir nos logs gerais.

Um projeto novo pode criar workspace lógico automaticamente quando a identidade estiver autorizada. Um checkout do mesmo repositório em outro host é candidato de associação, não prova de acesso: pedir seleção/aprovação única ou usar vínculo explícito já aprovado. Git remote, branch, nome de pasta e manifestos não são identidade confiável. Não mesclar dois workspaces porque seus paths ou remotes são iguais.

Preservar IDs legados baseados em path e criar aliases/vínculos aditivos. Não re-hashear histórico nem exigir migração destrutiva para IDs UUID. Novos IDs são opacos e gerados pelo Server. APIs antigas com `project_root` local continuam por adaptador de compatibilidade; paths vindos de um cliente remoto não passam por `realpath()` no Server.

Cwd, symlinks, mudança de root, wrappers, provider homes e executable drift são verificados de novo antes de spawn, não apenas no onboarding. Root aprovado restringe realização; não equivale a sandbox do sistema operacional. Informar honestamente as restrições efetivas do harness e do SO.

## A.7. API pública mínima do Core

A API final deve ser tipada e documentada; esta é a semântica obrigatória, não implementação pronta:

```python
class RuntimeCore(Protocol):
    async def discover(self, request: DiscoveryRequest) -> Inventory: ...
    async def prepare(self, intent: LaunchIntent, context: ExecutionContext) -> PreparedLaunch: ...
    async def open(self, operation: OpenOperation, context: ExecutionContext) -> OperationReceipt: ...
    async def submit(self, operation: TurnOperation, context: ExecutionContext) -> OperationReceipt: ...
    async def control(self, operation: ControlOperation, context: ExecutionContext) -> OperationReceipt: ...
    def events(self, cursor: EventCursor) -> AsyncIterator[RuntimeEvent]: ...
    async def inspect(self, session_id: str) -> RuntimeSnapshot: ...
    async def reconcile(self, request: ReconcileRequest) -> ReconcileReport: ...
    async def close(self, operation: CloseOperation, context: ExecutionContext) -> OperationReceipt: ...
    async def shutdown(self, policy: ShutdownPolicy) -> ShutdownReport: ...
```

`ExecutionContext` é fornecido pelo host confiável após autorização canônica e inclui os limites aplicáveis, binding/revisões/lease e prova de ownership. O Core não recebe `agent_id` livre do modelo como autoridade nem valida a API key canônica. Ele aplica a interseção entre limites recebidos, aprovação local e capacidades reais.

Ports obrigatórias: relógio monotônico/parede, journal transacional, process backend, secret resolver local, event sink, approval/work bridge e resolução de artefatos. Implementações default não dependem das aplicações. `PreparedLaunch` contém argv estruturado e refs de segredo locais; nunca `shell=True` ou código executável vindo do Server. Não expor classes internas de adapter como contrato público.

O Core gera dados de configuração para o cliente MCP HTTP do harness: URL do Server e referência segura de credencial/capability. Não recebe nem encaminha mensagens MCP, não hospeda MCP e não inclui extra de fachada ou dependência MCP para esse fim. Para harness sem cliente MCP HTTP e com extensão nativa comprovada, oferece bridge estruturada **não MCP**, limitada a ações explícitas de domínio. O Server injeta backend canônico local; o Connector pode chamar as APIs HTTPS canônicas para essas ações. Essa exceção não aceita envelopes/catálogos MCP, não se aplica ao caminho de um cliente MCP HTTP e não implementa outro motor de claim/complete/approval.

## A.8. Mensagens NXL e compatibilidade

Negociar `protocol_major=1`, revisão do contrato, versão de Core, tipos de evento, limites e capacidades efetivas. Durante o desenvolvimento pré-release, exigir a revisão exata `nxl-1-agent-centric-http-only-2026-09-25-r3`; o draft anterior r1 não é aceito por possuir o mesmo major. Compatibilidade entre revisões só existe após implementação/fixtures explícitas. Major incompatível falha antes de qualquer efeito. Minor adiciona campos opcionais/tipos negociados; permissões e ações desconhecidas falham fechadas. Não atualizar automaticamente o harness ou baixar schemas de `main` em runtime.

Famílias de frame: `hello`, `welcome`, `binding.attach`, `binding.detach`, `inventory.snapshot`, `inventory.delta`, `operation.submit`, `operation.receipt`, `operation.query`, `event.batch`, `event.ack`, `reconcile.request`, `reconcile.report`, `lease.renew`, `lease.granted`, `approval.request`, `approval.decision`, `heartbeat`, `error`, `goaway`.

Envelope de operação ilustrativo (campos sensíveis não estão neste exemplo):

```json
{
  "protocol_major": 1,
  "type": "operation.submit",
  "server_id": "srv_A",
  "executor_id": "exe_B",
  "binding_id": "bind_codex",
  "agent_id": "ag_123",
  "workspace_id": "ws_456",
  "workspace_binding_id": "wb_789",
  "session_id": "rs_321",
  "operation_id": "op_abc",
  "action": "turn.submit",
  "connection_generation": 7,
  "authorization_revision": 3,
  "configuration_revision": 4,
  "intent_hash": "sha256:<64-hex>",
  "payload": {"text": "Execute o trabalho autorizado", "delivery_id": "dlv_001"}
}
```

Gerar JSON Schemas de todos os frames, intents, eventos, erros, inventário, gates de capacidade e respostas HTTP; publicar fixtures positivas/negativas. Os exemplos não substituem schema executável. Artefatos grandes usam refs autorizadas e limitadas; não interpretar URLs arbitrárias como instruções de fetch sem política de origem, tamanho e workspace.

O WSS é um canal customizado de controle do produto. O MCP HTTP direto existente permanece no SDK/protocolo já utilizado; a consulta de especificações atuais não autoriza migrar implicitamente `mcp>=1,<2` para outro major.

## A.9. Operações, deduplicação e efeito incerto

Cada intenção mutável recebe `operation_id` persistente **antes do primeiro envio**. O Server reserva operação/outbox em transação; só depois despacha. O executor grava recebimento/intenção em seu journal antes do efeito nativo. Nenhuma dessas gravações torna spawn/write nativo atomicamente transacional.

Calcular `intent_hash = SHA-256(JCS(intent))`, por implementação testada de canonicalização. O objeto semântico inclui Server/agente/binding/executor/workspace/sessão/ação/payload/revisão de configuração/turno esperado. Exclui número de tentativa, ticket, prazo de renovação e geração do canal; reconectar não muda a intenção. Não aceitar NaN, infinitos, chaves JSON duplicadas ou campos semanticamente ambíguos. Gerar vetores de hash, inclusive Unicode e ordem de campos.

Mesmo ID e mesmo hash retornam o recibo/estado conhecido, sem repetir o efeito. Mesmo ID com hash distinto gera `OPERATION_CONFLICT`. Receber um erro de rede após admissão leva a consulta/reconciliação pelo mesmo ID, nunca a novo ID automático. Trocar configuração ou pedir nova execução é uma intenção nova explicitamente autorizada.

Estágios mínimos: `RECEIVED_DURABLE`, `PREPARED`, `SUBMISSION_STARTED`, `SUBMITTED`, `ACCEPTED` quando demonstrável, `RUNNING`, `WAITING_INPUT`, e terminais `SUCCEEDED`, `FAILED`, `CANCELLED`. `OUTCOME_UNKNOWN` expressa efeito possível sem comprovação e bloqueia replay automático; não é sinônimo de falha segura para tentar novamente.

ACK WSS, write/drain de pipe, aceitação nativa, final de turno e conclusão de handoff são fatos diferentes. Se um protocolo não emite ACK de aceitação, não inventá-lo. Eventos finais podem provar conclusão mesmo que ACK intermediário tenha sido perdido; reducer aceita essa ordem sem fabricar transições observadas.

Reconciliar pode resolver um estado incerto com evidência nova; não pode declarar “não executou” apenas por timeout. Não prometer exactly-once de efeitos externos. Retry por deduplicação nativa só é permitido quando a versão do protocolo comprovar essa garantia.

## A.10. Eventos duráveis e controle sob carga

Evento recebe identidade estável `(server_id, executor_id, session_id, stream_epoch, sequence)` antes do envio. `sequence` é monotônica e persistida; `stream_epoch` não muda ao reconectar WSS. Duplicatas mantêm identidade/hash. Novo processo/sessão pode criar outro epoch explicitamente; nunca reiniciar sequência fingindo continuidade.

Categorias normalizadas: lifecycle, estado de turno, text delta/snapshot, atividade de ferramenta, approval/input request, métricas de uso disponíveis, aviso de sistema/rate limit, erro e evento nativo desconhecido. Preservar `native_type` e metadados limitados, sem rotular tudo como atividade de ferramenta. Não inventar conteúdo interno de raciocínio ausente; não armazenar segredos por diagnóstico.

ACK de eventos significa commit no ingresso durável do Server, não entrega à UI. Watermark somente contíguo; gaps pedem replay ou são explicitamente registrados quando irrecuperáveis. Projeção canônica posterior é idempotente. Após revogação, eventos antigos autenticáveis podem ser tratados como evidência histórica conforme política restrita, nunca como nova autoridade ou início de outra entrega.

Filas possuem limites por bytes e itens; fairness por binding. Reservar orçamento para interrupt, revoke, approval, ACK e terminais. Fragmentar batches de texto para que controle não aguarde frames enormes. Saturação/disk full fecha novas admissões e produz estado honesto; não descartar silenciosamente finais. Deltas podem ser compactados em snapshot com marcação explícita; dados críticos não são tratados como descartáveis.

## A.11. Ciclos de vida: daemon, runtime e turno

CLI canônica do Connector: `daemon start`, `daemon run` (foreground), `daemon status`, `daemon stop`, `service install`, `service uninstall`, `runtime start`, `runtime interrupt`, `runtime stop`, `runtime status`, `runtime logs`. Não usar `start` sem namespace para dois significados incompatíveis. Aliases de conveniência somente se inequívocos e documentados.

Daemon: `STOPPED → STARTING → RUNNING → DRAINING → STOPPED`, com `FAILED/RECOVERING` quando cabível. Uma instância por conta de SO + diretório de instalação/domínio de confiança; múltiplos agentes/Servers dentro dela. Lock com identidade real do processo e readiness via IPC; não confiar em PID file isolado. CLI e TUI podem terminar sem matar daemon/runtimes independentes. Não existe fachada MCP; uma conversa tools-only com MCP HTTP direto é independente do daemon.

`daemon start` retorna após readiness local; offline do Nexus aparece como degradação, não prova de startup falho do daemon. `daemon run` fica em foreground; Ctrl+C solicita shutdown. `service install` exige consentimento e usa serviço de usuário quando disponível, sem privilégio admin por padrão. Fechar terminal, encerrar login e reiniciar máquina são eventos distintos: sem autostart/serviço de SO qualificado não prometer sobreviver ao logout ou boot.

Não abrir todos os harnesses ao subir daemon/Server. Harness sobe por pedido explícito ou entrega cuja aprovação permita auto-start. `runtime start` reutiliza sessão compatível por padrão; `--new-session` é explícito. Readiness só depois de spawn, handshake/probe, credencial de provider e bridge necessários. Um runtime headless não implica abrir a TUI nativa em outra janela.

Interromper turno preserva runtime quando o adapter permite. Parar runtime impede novas entregas e termina recursos próprios. Parar daemon/Server entra em drain por prazo limitado, depois interrompe e encerra árvores próprias. Emitir relatório por sessão com graceful/forced/unknown; não alegar sucesso total se ownership/terminação não puder ser demonstrado. Attach externo faz detach; não matar o alvo de terceiros.

Default de shutdown explícito: aguardar até 30 s de drain, solicitar interrupção, aguardar 15 s, terminar/forçar conforme backend qualificado. Essas janelas são configuração interna validada, não requisito de um wizard. O encerramento não desfaz efeitos externos, mudanças em arquivos nem remove identidade/chave/histórico.

Política padrão de ociosidade: manter runtime reutilizável enquanto host estiver ativo, sob quota. Encerramento por idle só quando configurado e suportado; não perder silenciosamente conversa não retomável. Reiniciar processo não reenvia último trabalho. Restart com turno em andamento ou desconhecido requer política/decisão explícita.

## A.12. Partições, leases, ownership e restart

Desconexão do canal não prova morte do harness. Suspender novas operações remotas; um turno em execução pode continuar até expirar a autorização local. Heartbeat não renova lease de trabalho. O prazo local é monotônico, calculado conservadoramente a partir de validade/RTT; alteração do relógio ou replay do frame não o estende. Reboot exige revalidação antes de qualquer novo efeito.

Reconnect: TLS/autenticação, negociação, reconciliação, aplicação de revogações, renovação autorizada e só depois novas admissões. Uma operação de estado desconhecido não é realocada para outro host. O Server continua com único owner de despacho conforme a base; o projeto não implementa HA multiwriter.

`connection_generation` impede comandos de canal antigo; `session_owner_generation` protege ownership da execução. Um novo WSS não autoriza novo processo para a mesma sessão. Definir CAS para reconexão da mesma instalação; duas instâncias ativas conflitantes não alternam posse silenciosamente. Nova posse após crash exige reconciliação; clone de disco/chave não é distinguido por alegação de hostname. Não prometer atestação de hardware.

Ownership inclui PID, criação/birth record, nonce e contenção/guard por SO; não matar por PID sem comprovar origem. Qualificar Job Objects no Windows e grupos/guards/cgroups onde disponíveis nos Unix. Process groups sozinhos não garantem cleanup após SIGKILL do pai. Core deve registrar os limites efetivos e usar guard adequado ou marcar risco/indisponibilidade, nunca prometer ausência de órfãos sem teste.

Na falha do host supervisor, o default é impedir execução indefinida sem controle usando contenção/guard de processos próprios. Reabrir pipes de um processo antigo não é pressuposto. Resume de conversa nativa pode criar novo processo/sessão sob nova intenção, sem replay automático de trabalho incerto. Processo externo anexado permanece fora da política de kill.

## A.13. Capacidades reais e ferramentas Nexus no harness

Descritor do adapter informa protocolos, versões qualificadas, plataformas e semântica de controle. Capacidade efetiva é a interseção de implementação × versão detectada × SO × perfil × política × prova de readiness. Flags estáticas são metadados, não comprovação de suporte naquela instalação.

Qualificar Codex app-server, Pi RPC, Claude stream e o attach existente. Completar os modos gerenciados para multi-turn, streaming, cancelamento, erros, input/aprovações e término real. Capacidades não suportadas retornam `CAPABILITY_UNSUPPORTED` antes do efeito; não converter steering imediato em interrupt+reprompt sem sinalizar e autorizar essa semântica.

Runtimes com cliente **MCP HTTP** recebem automaticamente configuração de acesso direto ao Nexus Server, sem passar pelo Connector ou por helper MCP do Core. No mesmo host, usar o endpoint HTTP de serve; em outro host, usar a origem HTTPS aprovada e alcançável a partir do processo/sandbox do harness. Não criar entrada MCP do tipo `command/args` apontando para Nexus/Connector nem subprocesso MCP. Runtimes sem cliente MCP HTTP só usam integração nativa não MCP quando implementada e qualificada — por exemplo, uma extensão estruturada do Pi — limitada a ações dos casos de uso canônicos. Não exigir cURL manual nem interpretar texto livre como `claim`, `complete` ou autorização.

O Nexus Server emite/valida capabilities de sessão consumíveis diretamente pelo endpoint MCP HTTP; o Connector solicita a capability sob a identidade importada e o Core apenas realiza a configuração segura do cliente. Um handle IPC local não serve como substituto que obrigue proxy de chamadas. No modo local o Server não precisa recuperar plaintext de sua key armazenada como hash: emite a capability da sessão autorizada. Não confundir autenticação de lane NXL com autenticação MCP. Providers/harnesses só recebem credenciais próprias e capabilities estritamente necessárias ao processo, nunca chave administrativa ou coleção de chaves de agentes. Segredos ficam fora de prompts, logs, URLs e argv; usar referência/env/config isolada com ACL conforme capacidade real do cliente.

Modo sem bridge de trabalho comprovada pode ser qualificado como conversacional, mas não como `execute_work`. Essa limitação não pode ser ocultada para marcar adaptação completa. Para attach baseado em substrato não suportado, preservar e diagnosticar o caminho existente, qualificar versões delimitadas; não inventar compatibilidade universal.

## A.13.1. Topologia MCP HTTP, credenciais diretas e remoção do stdio

A correção de arquitetura é normativa e substitui qualquer instrução de preservar stdio, criar fachada ou oferecer MCP dentro do Connector/Core nas revisões anteriores. Ela não é uma opção de implantação.

```text
Ferramentas — harness com MCP HTTP, local ou remoto:
  Harness (cliente MCP HTTP) ── HTTP(S) direto ──> Nexus Server / endpoint MCP

Controle remoto de runtime:
  Nexus Server <── WSS / NXL ──> Connector + Core <── protocolo nativo ──> Harness

Controle local de runtime:
  Nexus Server + Core <── protocolo nativo ──> Harness
```

O caminho de ferramentas não atravessa o processo Connector/Core. O caminho de runtime não é MCP, ainda que o adapter nativo use stdin/stdout. O Server precisa estar rodando para servir MCP HTTP; o harness não inicia uma instância Nexus por configuração MCP `command`. IPC privado da CLI/daemon permanece permitido para gestão, nunca como endpoint MCP. HTTP(S) de gestão no Server e o cliente HTTPS do Connector continuam válidos; não confundir remoção de MCP no Connector com proibição de todo uso de HTTP.

**Autoconfiguração e independência.** Preservar conexões MCP HTTP já existentes e a identidade do agente. Para novas configurações, gerar URL alcançável no contexto real do harness — não reutilizar loopback do Server para um host remoto, e considerar container/sandbox e allowlists de rede aprovadas. Preferir configuração por sessão; persistente usa consentimento, diff, backup e CAS. Não instalar MCP server/proxy local, não expor porta MCP no Connector, não injetar catálogo MCP em NXL e não introduzir callbacks para o daemon a cada tool call. Um cenário tools-only configurado com a credencial atual funciona sem instalar Connector, e continua funcionando após desligá-lo se ele foi usado apenas para configurar; isso não promete manter vivo um runtime que o daemon possui quando ele é desligado.

**Autorização direta.** O endpoint MCP HTTP resolve o agente pela credencial/capability autenticada e aplica permissões, claims e deduplicação comuns. Managed sessions recebem capability limitada por agente/workspace/binding/sessão/ações e validade; a identidade permanece o mesmo agente, não nasce outra credencial canônica. Requisições MCP diretas não podem contornar lease, geração, grants ou revogação das operações que pertencem à sessão gerenciada. A credencial canônica de um cenário tools-only independente mantém a política própria já existente; possuir WSS não é requisito para usar MCP HTTP legítimo.

**Validade sem proxy.** Tickets NXL e capabilities MCP têm finalidade e audiência distintas. Especificar e testar emissão, expiração, renovação e revogação das capabilities no Server. Preferir segredo de sessão validado contra estado/validade renovável no Server, sem reinjetar segredo a cada chamada; não pressupor hot-reload de credenciais em todos os harnesses. Qualificar o mecanismo seguro por adapter, inclusive expiração durante turno. Não trocar uma operação incerta por restart/retry para renovar credenciais. O modo tools-only independente não depende do Connector para renovar sua credencial; revogação real exige o fluxo autorizado. Nunca aceitar automaticamente um ticket NXL como bearer MCP com escopo ampliado.

**Partições independentes.** Testar WSS indisponível com HTTP alcançável e o inverso. A perda do WSS não redireciona MCP via túnel nem autoriza novos efeitos de sessão após lease/revogação. A perda do MCP HTTP não é reparada com MCP stdio; reportar disponibilidade separada de processo, controle e ferramentas. `execute_work` exige caminho de ferramentas e autorização comprovados; runtime conversacional não deve ser anunciado como execução governada completa. Capability expirada não vira falha segura para repetir uma chamada mutável.

**Migração obrigatória.** Inventariar e remover entrypoints, subcomandos, inicialização automática por harness, módulos, distribuição, exemplos, wizard, documentação e testes que implementam ou mantêm MCP stdio no Nexus. Comando antigo deve falhar de forma prescritiva ou deixar de existir, sem abrir transporte MCP nem preservar um shim stdio→HTTP. Converter somente configurações Nexus explicitamente selecionadas e sob ownership/consentimento; manter identidade/key e entradas de outros servidores MCP. O rollback deste trabalho não reativa MCP stdio como fallback operacional; uma volta manual a artefato histórico é um downgrade fora do contrato r3, nunca suporte aceito. Remover a implementação não autoriza apagar projetos/histórico ou adapters nativos de stdio.

**Capacidade não suportada.** Harness com MCP apenas stdio não atende ao caminho MCP desta arquitetura. Retornar diagnóstico de transporte não suportado, sem instalar proxy de terceiros nem extensão genérica que apenas esconda o mesmo proxy. Uma integração nativa não MCP é uma feature separada, limitada, estruturada e qualificada; não recebe envelopes MCP, não publica MCP e não substitui o caminho direto de harness compatível.

## A.14. Inbox, respostas, handoffs e HITL

Uma entrega lógica disputa o mesmo mecanismo de consumo exclusivo entre MCP pull, runtime local e runtime remoto. A outbox registra tentativas de transporte; não vira segunda tarefa. Duplicar conexão não duplica grant, turno ou resposta. Observadores recebem eventos sem execução; não enviar prompt de trabalho a um “observador” que o executará.

Turno concluído não significa handoff concluído. O resultado governado passa pelos casos de uso de claim/grant/complete existentes. Preservar reply target, root/parent/correlation, dedupe, orçamento causal/relay e evidências. Reconnect não reinicia orçamento de mensagens nem permite loop de agentes.

Pedido HITL correlaciona binding, sessão, turno, request nativo, geração, revisão e expiry. Server autoriza/registra decisão única com CAS; UI e CLI são canais de apresentação, não identidades humanas novas nem autoridades paralelas. A chave do próprio agente não basta para aprovar uma escalada que exige operador. CLI deve encaminhar ao mecanismo já autorizado ou reportar pendência; jamais autoaprovar por ser local.

Negação, timeout, saída da UI ou rede caída não viram aprovação. Resposta tardia não é aplicada a outro turno. Estado de solicitação e decisão precisa sobreviver ao reconnect dentro das capacidades reais do harness.

## A.15. Segurança, isolamento e configuração

Cofre local para chaves; configuração/journal guarda refs. Fallback restrito com ACL é explícito e explicado, sem alegar criptografia que não existe. Host comprometido ou processo malicioso com a mesma conta do SO pode exceder a proteção da aplicação; sandbox de provider não equivale a isolamento de contas. Redigir secrets em stdout/stderr, tracing, dump e exports; evitar dumps de memória por padrão.

Não procurar credenciais automaticamente. Detectar métodos locais de autenticação, disponibilidade de login e arquivos candidatos; ler/importar só o que foi selecionado. Provider homes podem carregar hooks/plugins: consentimento de usar login não é autorização de executar todo hook do home. Resolver isolamento/config suportado por versão e informar quando não puder separar.

Alterações em configuração de harness são plan/apply com backup, comparação de revisão e merge estrutural. Preferir configuração efêmera por execução. Não sobrescrever arquivos globais ou apagar entradas de outros MCPs. `disconnect/unbind` remove somente campos sob ownership do produto; evidência de operações não é apagada como efeito de remover configuração.

Não aceitar executable, argv arbitrário, env livre, plugin dinâmico ou root enviado pela rede como autorização. O Server envia intenção/template; Core resolve realização local aprovada. Wrapper Windows deve ter implementação especializada/qualificada, não comando de shell montado por concatenação.

TLS obrigatório fora de desenvolvimento loopback explícito, sem fallback silencioso `verify=False`. Allowlist da origem, proteção de proxy reverso, limites de frame, redaction de headers e timeout de upgrade. Não expor IPC à rede externa. Unix sockets/named pipes com ACL; fallback loopback só autenticado e com proteção de origem/CSRF onde aplicável.

## A.16. Defaults, escalabilidade e observabilidade

Defaults são hipóteses de engenharia a testar, não resultados de benchmark:

| Parâmetro | Default inicial |
|---|---|
| Ticket de binding | 10 min, renovação a 70% com jitter e single-flight |
| Heartbeat / detecção de canal ausente | 15 s / 45 s; ausência não prova término do runtime |
| Lease de sessão / renovação | 120 s / 30 s; renovação condicionada à autorização |
| Grace após lease | 15 s antes de escalada de terminação própria |
| Startup de runtime | Até 90 s; API pode responder 202 imediatamente |
| Frame máximo / chunk de evento | 1 MiB / 64 KiB, medidos em bytes |
| Intenção inline | 64 KiB; recursos maiores por referência autorizada |
| Operações em trânsito / runtimes por instalação | 32 / 8, respeitando política e quotas existentes |
| Journal técnico por executor | 256 MiB, 16 MiB reservados para controle/críticos |
| Backoff de rede | 0,5–30 s exponencial com jitter; não é retry de efeito |
| Drain explícito | 30 s + 15 s de grace; resultado por recurso |

Ao atingir 80% do journal sem recuperação saudável, bloquear novas admissões e compactar somente dados elegíveis. Quotas por agente/host/Server contam todos os endpoints; fairness impede um stream monopolizar o daemon.

Cenário de pelo menos **100 mil identidades cadastradas**: onboarding autentica uma chave por índice e retorna somente vínculos pertinentes; descoberta é local. Não enumerar todas as identidades, abrir WSS para agentes offline ou alocar uma thread por agente cadastrado. Paginação por cursor, índices e caches limitados. Volume de identidades não é promessa de 100 mil runtimes concorrentes; medir concorrência separadamente.

Métricas: tempo de resolve/start/ready, reconexão, backlog em bytes, leases, gaps, operações incertas, duração de approval, recursos por adapter. Não usar `agent_id/session_id` como labels ilimitados de métricas; IDs completos ficam em logs/traces escopados e redigidos. WSS ativo, daemon vivo e runtime pronto são estados distintos.

## A.17. Erros, compatibilidade e publicação

Erros mínimos: `AGENT_AUTH_REQUIRED`, `AGENT_ID_MISMATCH`, `AGENT_REVOKED`, `CREDENTIAL_REPLACEMENT_REQUIRED`, `SERVER_ID_CHANGED`, `BINDING_NOT_AUTHORIZED`, `AMBIGUOUS_BINDING`, `APPROVAL_REQUIRED`, `PROVIDER_AUTH_REQUIRED`, `BINARY_NOT_FOUND`, `NATIVE_VERSION_UNQUALIFIED`, `PROFILE_DRIFT`, `WORKSPACE_UNAVAILABLE`, `EXECUTOR_OFFLINE`, `STALE_GENERATION`, `STALE_TURN`, `CAPABILITY_UNSUPPORTED`, `OPERATION_CONFLICT`, `OUTCOME_UNKNOWN`, `JOURNAL_FULL`, `EVENT_GAP`, `CAPACITY_EXCEEDED`, `VERSION_INCOMPATIBLE`.

Resposta inclui código, estágio, possível efeito, segurança do retry, operation_id consultável e ação corretiva. Não ecoar segredo, traceback ou root sem necessidade. Erro de rede depois de efeito possível não pode receber `retry_safe=true`.

Core usa SemVer da biblioteca, separado do wire major NXL. Antes de 1.0, fixar minor compatível e testar upgrade explicitamente. Aplicações consomem wheel imutável + hash; nada de instalar `main` ou importar pasta irmã como distribuição final. Schemas e fixtures fazem parte do wheel e sdist. Publicação PyPI é etapa técnica preparada, mas só executada com autorização e credenciais apropriadas; build local não depende disso.

Não alterar a licença dos arquivos extraídos sem decisão do titular. Preservar avisos/proveniência e registrar necessidades de packaging/licença sem transformar este plano em parecer jurídico.

## A.18. Ordem dos três projetos e evidência

O Core é dono dos contratos; N00, C00 e K00 podem começar em paralelo. K01 publica bundle de desenvolvimento a partir deste anexo. K02/K03/K04 liberam wheel incremental utilizável antes de terminar todos os adapters. Nexus e Connector integram esse wheel; não esperam conclusão total do outro projeto.

```text
N00 ───────────────┐
C00 ───────────────┤
K00 → K01 ────────┼→ N01/N02 e C01/C02
       → K02 → K03/K04 → N03/N04 e C03/C04/C05
                         → K05/K06/K07/K08 → K09 → bridges nas aplicações
N05/N06 + C04 → primeiro WSS ponta a ponta
N12 + C10 + K11 → mesma campanha conjunta N13/C11
```

Dependências cruzadas de testes são **gates de integração**, não exigência de um projeto se declarar DONE antes do outro rodar a mesma campanha. Cada build registra SHA de Server/Connector/Core e hash do bundle.

Nenhuma evidência de teste executado durante a escrita destes planos é presumida. Tarefas começam `PENDING`; testes `NOT_RUN`. Codex pode usar fakes para unitários/contratos, mas testes de provider real, múltiplos hosts e processo/SO precisam executar nesses ambientes. Sem credencial/host autorizado, registrar bloqueio externo e continuar tarefas independentes; não declarar o produto completo com mocks.

Cada evidência inclui ID, ambiente, versões, comandos, resultado, logs redigidos, duração/recursos quando relevantes e distinção entre falha anterior e regressão. Não sobrescrever evidência histórica. Implementar, testar e registrar resultados; não encerrar entregando outro planejamento.

---

# Anexo B — Aceite conjunto dos três projetos

Os casos abaixo são os mesmos nos três planos. Todos iniciam **NOT_RUN**. Registrar owner de execução, ambiente e blockers. Um cenário de contrato com peer sintético não fecha o cenário homônimo que exige provider/host/SO real.

**Topologia mínima:** A com Nexus Server sem binários/provider keys/projetos remotos; B/C com Connector e o mesmo wheel Core; uma instalação Nexus local separada sem aplicativo Connector. Para heterogeneidade, incluir Windows e um Unix em infraestrutura autorizada. Não simular SO só mudando uma string `platform`.

| ID | Cenário | Preparação/ação | Resultado exigido |
|---|---|---|---|
| J01 | Identidade canônica | Criar agente previamente no Nexus e configurar MCP com sua key; importar a mesma no Connector. | Nenhum segundo Agent/user; MCP continua válido, mesmo agent_id em mensagens e sessões. |
| J02 | Não rotacionar para conectar | Usar Server que guarda somente hash; gerar comando para identidade existente. | Comando pede/importa key existente de forma protegida; não chama issue_key silenciosamente. |
| J03 | Autenticação errada | Key A com hint B; depois ticket A tenta abrir lane de B. | Negação antes de configuração/spawn; nenhuma atribuição por payload. |
| J04 | Nexus local puro | Instalar Nexus/Core, sem app Connector, e abrir/gerir cada runtime gerenciado qualificado. | Core embutido em serve, sem daemon Connector, pareamento ou WSS local obrigatório. |
| J05 | Servidor realmente remoto | A sem executáveis/providers/projetos; B/C com Connector/Core e harnesses. | Operações e streams funcionam; Server não faz realpath/spawn de B/C. |
| J06 | Rede outbound | Firewall de B/C nega conexões entrantes e permite WSS/HTTPS ao Server; testar também o processo/sandbox do harness. | Controle via Connector e MCP HTTP direto via harness funcionam com tráfego de saída; nenhuma porta MCP local exigida. |
| J07 | Paths heterogêneos | A Linux, B Windows e C Unix; roots diferentes do mesmo e de outros repositórios. | Vínculos lógicos autorizados, validação física local e nenhuma fusão por path/Git. |
| J08 | 100 mil agentes | Sem providers, popular 100 mil identidades no Server e importar uma key em B. | Queries indexadas e escopadas; não listar tudo nem criar recursos por agente offline. |
| J09 | Um daemon, várias identidades | B importa agentes A1/A2 que usam o mesmo binário Codex e um agente Pi. | Sessões/credentials/lanes isoladas, sem daemon por agente ou prompt broadcast indevido. |
| J10 | Dois Servers | B conecta dois Servers distintos e remove/revoga binding em apenas um. | Namespaces, processos, cofre e tickets do outro preservados. |
| J11 | First-use/second-use | Configurar por comando da tela e executar runtime start repetidamente. | Setup agregado uma vez; depois sem JSON/argv/endpoint/profile/grant/chave manual recorrente. |
| J12 | Daemon automático | Connect e runtime start concorrentes com daemon parado. | Uma instância; daemon ready não abre todos os harnesses descobertos. |
| J13 | Terminal independente | Fechar CLI de start, TUI/log follower e encerrar cliente MCP HTTP tools-only independente. | Daemon e runtimes independentes continuam; fechar cliente HTTP não encerra supervisor nem outra sessão. |
| J14 | Turno versus processo | Enviar trabalho, interrupt, novo turno e runtime stop. | Cancelamento preserva runtime quando suportado; stop encerra recursos próprios, não identidade/histórico. |
| J15 | Shutdown/crash | Stop daemon/serve; depois SIGKILL do supervisor em cenário controlado. | Drain/containment e relatório real; sem kill alheio ou trabalho indefinido não declarado. |
| J16 | MCP HTTP tools-only direto | Usar conversa não gerenciada com MCP HTTP antes/depois de instalar e desligar Connector; também testar sem Connector instalado. | Harness chama somente o Server; identidade preservada, nenhum proxy/subprocesso MCP e nenhuma adoção de conversa pelo runtime. |
| J17 | Work bridge nativa não MCP | Pi sem MCP HTTP recebe tarefa e chama contexto/claim/complete via extensão qualificada. | Mesmo domínio canônico; nenhum servidor/proxy/envelope MCP no Core/Connector; texto livre não completa handoff. |
| J18 | Consumo exclusivo | Uma entrega com MCP pull e dois runtimes disponíveis ao mesmo agente. | Um consumidor lógico; sem duplo turno/grant/resposta por multiplicidade de conexão. |
| J19 | HITL concorrente | Provider pede aprovação; CLI/UI respondem, agente tenta autoaprovar e decisão chega tarde. | Autoridade existente, CAS, geração/turno corretos; timeout/deny não aprovam. |
| J20 | Recebido não é concluído | Observar ACK WSS, aceitação nativa, fim de turno e handoff em cada adapter. | Estados separados, nenhum marco antecipa outro sem evidência. |
| J21 | Resposta perdida | Perder ACK após submit nativo possível, reconectar e repetir consulta/ID. | Sem replay automático; recibo/unknown/reconciliação pelo mesmo intent. |
| J22 | Partição e revogação | Revogar key com WSS online e depois testar partição prolongada/relógio alterado. | Online invalida derivados; offline limita por lease, sem prometer revogação instantânea. |
| J23 | Gerações e takeover | Canal antigo e novo/daemon clonado disputam mesma sessão. | Um owner, fencing/reconciliação; sem failover silencioso ou processo duplicado. |
| J24 | Eventos/retention | Interromper ACK, enviar duplicatas/out-of-order e ultrapassar retenção. | Ingressão durável idempotente e watermark contíguo; gap explícito, terminais não ocultos. |
| J25 | Saturação | Flood texto, disco cheio e consumidor lento enquanto chega interrupt. | Memória/journal/queues finitos, faixa crítica preservada e novas admissões bloqueadas quando necessário. |
| J26 | Drift/config segura | Trocar binary/root/symlink/home/hook e editar MCP existente durante setup. | Reprepare/approval/CAS; sem execução ampliada, JSON destruído ou secrets centrais. |
| J27 | Quatro adapters | Qualificar Codex/Pi/Claude managed e attach existente por versão/SO delimitados. | Mesma implementação Core local/remota e capabilities comprovadas, sem sucesso simulado. |
| J28 | Upgrade/rollback | Migrar Nexus legado, atualizar Connector/Core com journal pendente e instalar wheels limpos. | Histórico/IDs/negações preservados, drain/reconcile e dependências acíclicas. |
| J29 | Segredos/ameaças | Inspecionar argv/log/config/export/metric; tentar handle/agent/server spoof e shell injection. | Sem chave canônica/admin de terceiros/provider secrets vazados ou efeito fora do escopo. |
| J30 | Release coordenado | Conferir resultados/SHAs/wheel hashes e gates provider/SO/multi-host em três relatórios. | Mesma evidência, bloqueios explícitos e nenhuma alegação de produto completo baseada só em fakes. |
| J31 | Remoção MCP stdio | Instalação limpa e upgrade do Nexus v0.2.0 com configuração MCP stdio; inspecionar entrypoints, módulos, exemplos e migração selecionada. | MCP stdio ausente, sem shim/fallback; MCP HTTP direto mantém agente/key/histórico e outras entradas não são alteradas. |
| J32 | MCP HTTP local nativo | Somente Nexus/Core no host; abrir runtime gerenciado com MCP HTTP para o próprio Server. | Sem Connector ou fachada; cliente chama endpoint HTTP de serve com capability válida e o Core só configura o cliente. |
| J33 | Fronteira protocolo/transporte | Exercitar stdio nativo dos adapters e inspecionar artefatos/portas de Connector/Core; testar harness com MCP apenas stdio. | Protocolos nativos funcionam; nenhum serviço/extra/CLI MCP/proxy; cliente incompatível recebe diagnóstico sem fallback stdio. |
| J34 | Dois canais e autorização | Em runtime remoto com MCP HTTP direto, derrubar apenas WSS e depois apenas HTTP; expirar/revogar capability e manter outra conversa tools-only independente. | Sessão gerenciada respeita lease/grants/revogação sem bypass, replay ou túnel; canal HTTP tools-only legítimo mantém política própria sem exigir daemon. |

## Registro de evidência obrigatório

Cada caso registra: `test_id`, `status`, `blocked_reason`, SHAs de Server/Connector/Core, hashes dos wheels/bundle, versões dos harnesses, SO/arquitetura, topologia e política, comandos exatos, data/hora, resultado observado, artefatos redigidos e limitações. Status permitido: NOT_RUN/PASS/FAIL. Não usar SKIP como sinônimo de PASS.

Segregar credenciais/contas e projetos de teste. Não executar faturamento/provider/hosts de produção sem autorização. Quando indisponíveis, construir fixtures e registrar contrato PASS se executado, mantendo o caso real NOT_RUN. Um relatório de CI verde com testes reais não executados não autoriza alegar suporte nesses ambientes.

A campanha N13/C11 pode começar assim que N12, C10 e K11 entregarem seus artefatos. Nenhuma fase aguarda que a outra conclua a mesma campanha. Reutilizar a mesma evidência, não dois resultados conflitantes com SHAs diferentes.

---

# Anexo C — Fontes, baseline e natureza das decisões

## C.1. Referências históricas da revisão 2

**[R01]** GitHub, branch `feature/v0.2.0`: HEAD `7ed52c22865a92c3768bc32508ed9e35dc5efdc3`, registrado como confirmado na revisão 2 em 25/09/2026. A revisão 3 não consultou novamente o repositório; o Codex deve conferir o HEAD efetivo.
https://api.github.com/repos/OktoLabsAI/okto-nexus/branches/feature/v0.2.0

**[R02]** `pyproject.toml` no SHA de referência: Python >=3.11; dependência MCP `>=1.0,<2`; extras serve/serve-lite; CLI e metadados do projeto. Não mudar SDK major ou licença como efeito da extração.
https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/pyproject.toml

**[R03]** `application/auth.py`: AgentKeyAuthService, emissão/rotação, hash, retorno de plaintext uma vez, resolvedor e invalidação. Importação de chave existente e tickets derivados são decisões de projeto; não supor que já estejam implementados.
https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/auth.py

**[R04]** `application/identity.py`: identidade/sessões/workspaces e caminho legado de resolução física do project_root. As demais âncoras de runtime/UI vieram da revisão anterior e precisam ser reproduzidas pelo Codex no HEAD efetivo.
https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/identity.py

**[R05]** Materiais anteriores fornecidos nesta conversa e relidos a partir de seus arquivos: `PLANO_01_NEXUS_CONEXOES_NATIVAS_E_DISTRIBUIDAS_CODEX.md` e `PLANO_02_NEXUS_CONNECTOR_CODEX.md`, contrato `nxl-1-draft-2026-09-24-r1`. Foram usados como base/crosswalk, não como autoridade acima das decisões posteriores. Esta revisão substitui o desenho de dois projetos, o runtime package dentro do Connector e onboarding não centrado na credencial do agente.

## C.2. Referências técnicas primárias registradas na revisão 2

**[R06]** Documentação oficial do Codex App Server, consultada em 25/09/2026. O endereço redirecionou para documentação oficial em ChatGPT Learn. Usar a versão instalada e schemas do binário como parte da qualificação; não prometer todos os recursos descritos para versões antigas.
https://developers.openai.com/codex/app-server/
https://learn.chatgpt.com/docs/app-server

**[R07]** Documentação RPC do Pi no repositório oficial atual `earendil-works/pi`; o antigo endereço `badlogic/pi-mono` redireciona. Arquivo consultado pelo GitHub, blob `ad6ff90e80ba89eb2a42f226c1cbd46bc1818a2f`: framing LF, IDs assíncronos, eventos e shutdown. Fixar commit/versão usados nos testes de implementação.
https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md

**[R08]** Documentação oficial Claude Code, uso programático e saída stream-json, consultada em 25/09/2026. Controles/approvals devem ser verificados na interface e versão qualificada, não inferidos da saída em streaming.
https://code.claude.com/docs/en/headless

**[R09]** Especificação MCP versionada 2025-11-25, usada para Streamable HTTP. A presença de stdio no padrão não autoriza MCP stdio nestes produtos; r3 o proíbe. Referência deliberadamente versionada para compatibilidade, não afirmação de que é a revisão mais recente. O plano não migra o protocolo/SDK da base implicitamente.
https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

**[R10]** RFC 6455, WebSocket. NXL é decisão de protocolo do produto sobre WSS, não parte do padrão MCP.
https://www.rfc-editor.org/rfc/rfc6455

**[R11]** Decisão explícita do usuário nesta conversa, 25/09/2026: remover MCP stdio do Nexus e qualquer MCP no Connector; clientes MCP acessam diretamente o Nexus Server por HTTP. A revisão 3 corrige documentos e backlogs, sem nova auditoria de código ou consulta às fontes externas. Essa decisão prevalece sobre instruções de compatibilidade stdio/fachada da revisão 2.

## C.3. O que é especificação, não fato implementado

Nomes/rotas novos, comandos CLI, modelos, API do Core, tickets, defaults, budgets, schemas a gerar, fases, testes e métricas são decisões propostas e requisitos de implementação. Nenhum benchmark, teste de provider, execução multi-host, publicação PyPI ou alteração em repositório foi realizado ao escrever estes planos. A validação desta entrega verifica consistência dos documentos/backlogs, não funcionamento do produto.

Se o HEAD mudou, o Codex registra a diferença e aproveita código correto posterior; não restaura a branch ao SHA deste documento. Conflitos com limites reais de protocolo devem produzir ADR, capacidade explícita e teste, não uma promessa inexequível ou remoção silenciosa de requisito.
