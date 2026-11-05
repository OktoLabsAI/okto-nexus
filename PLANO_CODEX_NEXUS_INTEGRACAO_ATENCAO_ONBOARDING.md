# Okto Nexus — plano de implementação para o Codex
## Padrão plug and play, daemon, uso pelo terminal e evolução opcional pela interface

**Data de referência:** 22/10/2026.  
**Revisão:** R3 — padrão completo para o uso diário sem dashboard obrigatório, conforme decisão do usuário.  
**Natureza:** especificação proposta de implementação; não representa funcionalidades já entregues nem testes executados.  
**Destino:** execução incremental nos repositórios Nexus Server, Connector Core e Connector.  
**Princípio:** melhorar a entrada e a operação do produto sem substituir sua arquitetura de coordenação por um gerenciador de terminais.

---

## O que muda nesta revisão

Esta revisão mantém o daemon na primeira entrega e amplia seu critério de sucesso para **Server/Connector em segundo plano + agente padrão pronto + ciclo de trabalho completo pelo terminal**. O usuário pode permanecer na configuração padrão e usar o Nexus no cotidiano sem abrir o dashboard. A interface permite personalizar e administrar mais detalhes quando isso for útil; não existe uma etapa posterior obrigatória de configuração no painel. A central de atenção vem depois; a integração Herdr permanece opcional e independente.

| Decisão | Diretriz de implementação |
|---|---|
| Eliminar a inicialização manual recorrente | O comando de conexão inicia ou reutiliza a instância configurada e aguarda prontidão. |
| Disponibilidade além do primeiro comando | Oferecer instalação como serviço do usuário, com início no login e recuperação de falha comprovados por plataforma. |
| Tornar o dashboard opcional durante todo o uso padrão | Conectar, solicitar trabalho, acompanhar, responder a perguntas/aprovações autorizadas, obter resultados e voltar a usar pelo terminal. |
| Começar pelo que o usuário conhece | Projeto e harness detectado; decisões de transporte e runtime são resolvidas pelo produto e explicadas quando relevantes. |
| Entregar um agente padrão útil | Sugerir identidade persistente e perfil generalista de projeto, preservar a configuração efetiva do harness e incluir as permissões de coordenação adequadas no resumo inicial. |
| Permitir sofisticação gradual | Editar a mesma configuração e identidade depois; o preset inicial permanece suficiente para quem nunca abrir o painel. |
| Preservar o investimento existente | Reutilizar Server, Connector, Core, adaptadores nativos e setup transacional. |
| Entregar valor cedo | Primeiro marco com um harness suportado executando trabalho real de ponta a ponta; expansão de clientes e plataformas em etapas verificáveis. |

Os IDs das 39 tarefas e dos 79 cenários originais são preservados, assim como todas as tarefas e cenários acrescentados em R2. R3 acrescenta o preset completo e o uso cotidiano sem painel; antecipa somente as partes das operações necessárias a esse primeiro marco. **A ordem dos capítulos descritivos não substitui as dependências da seção 11.** O prompt de execução atualizado está na seção 19.

# 1. Mandato de execução

Implementar quatro frentes coordenadas:

**SVC — Ciclo de vida do Server e do Connector:** executar os componentes existentes em segundo plano, iniciar sob demanda, reutilizar instâncias e oferecer serviço do usuário com controles e diagnóstico. Não criar outro coordenador.

**DX — Onboarding e operações de alto nível:** começar por projeto e harness, aplicar um preset generalista útil e oferecer o ciclo cotidiano completo pelo terminal. A primeira fatia reutiliza um adaptador nativo existente e os contratos canônicos de interação, decisões e resultados. Participação MCP e execução gerenciada continuam caminhos válidos, sem escolha técnica obrigatória antes do primeiro benefício.

**ATN — Central de atenção:** reunir situações que exigem decisão ou acompanhamento, reutilizando os registros e comandos canônicos existentes.

**OBS — Integração leve e atividade externa:** permitir observabilidade opcional de harnesses executados fora do Core. Entregar um observador Herdr de referência, desacoplado do funcionamento normal do Nexus.

Prioridade: **baseline → daemon, preset e trabalho completo pelo terminal → ampliação de clientes/operações → central de atenção → observação externa**. Trabalho independente pode avançar em paralelo, sem deslocar o primeiro marco para depois da central ou do Herdr.

O produto já permite participação MCP-only. OBS **não** deve ser apresentado ou implementado como criação dessa capacidade. O acréscimo é o contrato de atividade externa, sua integração à experiência operacional e a facilidade de conectar participantes.

Entregar implementações utilizáveis, testes, documentação, migrações e evidências por etapa. Não entregar somente interfaces simuladas, esqueletos, fixtures apresentados como suporte real ou uma segunda proposta sem código. Não mudar a arquitetura de execução para facilitar os testes.

O plano autoriza seu executor a trabalhar no escopo definido, mas não autoriza publicar pacotes, fazer merge em branches protegidas, alterar a instalação pessoal do usuário, usar credenciais reais, instalar plugins globais ou executar turnos pagos sem autorização específica.

# 2. Baseline e regras de atualização

## 2.1 Snapshots consultados

| Repositório | Branch de referência | Versão no pyproject.toml | Commit |
|---|---|---|---|
| `OktoLabsAI/okto-nexus` | `main` | `0.3.1` | `e480ab41ba046204c62ebf25d04c9e61b22fbd78` |
| `OktoLabsAI/okto-nexus-connector-core` | `main` | `0.0.12` | `76db0a79c5cf7f5248e4994dd10f2587a2d59f9b` |
| `OktoLabsAI/okto-nexus-connector` | `main` | `0.0.10` | `20f16199f4b2926630c0bfe1b8a8646a836dbe53` |

Server e Connector fixam Core `0.0.12` nesse conjunto. A documentação possui trechos históricos e divergentes: não inferir versão vigente do README nem copiar instruções de onboarding legado quando o código atual já mudou. [B01–B03]

Antes da implementação, registrar `git status`, branch, HEAD, instruções `AGENTS.md`, dependências e diferenças em relação a esses commits. Usar a branch de trabalho autorizada no ambiente; não fazer reset, checkout destrutivo ou sobrescrever mudanças do usuário. Se houver evolução posterior, reconciliar o plano com ela e documentar diferenças. Não retroceder automaticamente para esses SHAs.

## 2.2 Fatos que o plano deve preservar

**Participação externa já disponível.** MCP HTTP, identidades, sessões, inboxes e handoffs não dependem de um adaptador nativo para cada cliente. Clientes MCP reivindicam handoffs explicitamente; o caminho automático gerenciado tem admissão e capacidade próprias. [B04, B05]

**Onboarding gerenciado já implementado.** `connection_setup.py` contém o fechamento transacional do setup, proteção por revisões e recibos idempotentes. `connection-setup.md` descreve descoberta, teste temporário e aplicação final. Não construir um fluxo concorrente de bindings e grants. [B06, B07]

**Observabilidade já extensa.** Há presença/conexões, eventos, visão por agente de instâncias e turnos, histórico, aprovações, perguntas nativas, capacidade e apresentação de runtime. ATN é uma composição operacional desses fatos, não um substituto. [B08–B11]

**Configuração MCP gerenciada não é onboarding genérico.** `harness_config.py` valida templates gerenciados, formatos qualificados e referências `mcp-cap:`. Reaproveitar funções puras adequadas, mas não flexibilizar esse contrato para encaixar uma chave canônica de participante. [B12]

**Há uma introdução de primeiro uso.** `OnboardingModal.tsx` é uma introdução em slides, não prova de conexão real. O placeholder consultado ainda constrói URL HTTP com chave em query string; corrigir a orientação para autenticação por header e respeitar o endereço/scheme aprovado. [B13]

**Duas expressões semelhantes têm significados distintos.** `runtime_observations.py` trata entrega de contexto sem execução. Não reutilizar esse subsistema para telemetria externa apenas porque contém “observations” no nome. Capacidade reservável também não é atividade observada. [B14]

**Idempotência não é presumida.** A assinatura consultada de `MessageService.create_message` não expõe um identificador público genérico de requisição. Recibos de runtime não tornam automaticamente qualquer criação de mensagem idempotente. DX precisa confirmar o caminho completo e suprir a lacuna antes de oferecer repetição segura. [B15]

## 2.3 Limite da revisão R3 e fundamento da mudança

Os SHAs e fatos de código acima são o baseline registrado na análise original, preservado nesta revisão. R2 e R3 não constituem nova auditoria integral dos três repositórios nem certificação do HEAD atual. O executor deve confirmar o que já existe de serviço, daemon, supervisão, interação nativa e retomada antes de acrescentar código; inclusive o nome real do comando de servidor em foreground.

A documentação oficial do Herdr consultada em 22/10/2026 descreve iniciar/reutilizar uma sessão em background, criar o workspace inicial e executar o agente dentro de uma pane; há onboarding inicial e integrações adicionais. Essa referência fundamenta a proposta de reduzir o caminho até o primeiro benefício, sem copiar seu multiplexer nem presumir adoção de processos abertos em terminais externos. [H04–H06]

R3 incorpora a decisão do usuário de manter a experiência padrão suficiente também depois do onboarding. A analogia com Herdr é uma meta de facilidade de uso: o harness continua sendo o ambiente de trabalho reconhecível pelo usuário. Herdr mantém agentes em panes de terminal reais; um adaptador gerenciado no Nexus, por si só, não comprova paridade de TUI, attach ou retomada de sessão. A rota padrão precisa demonstrar a interação completa descrita em DX-20, sem prometer essas capacidades por associação. [H07]

As opções de serviço por sistema operacional na seção 7 são propostas a qualificar. Documentação de um gerenciador de serviços não comprova que Nexus/Connector já funcionam nele. [S01–S06]

# 3. Invariantes obrigatórios

| ID | Regra |
|---|---|
| INV-01 | A identidade canônica continua sendo `agent_id`. Harness, transporte, pane, host, sessão e observador não criam automaticamente outro agente. |
| INV-02 | MCP do Nexus permanece HTTP direto no Server. Não adicionar servidor/proxy/fachada MCP no Connector ou no observador. Não reintroduzir MCP stdio do Nexus. |
| INV-03 | Core continua independente das aplicações; não recebe banco de identidades, inbox, HTTP de produto, UI ou autorização canônica. |
| INV-04 | Connector continua host/cliente remoto de execução. Não passa a decidir handoffs nem a possuir inbox própria. |
| INV-05 | Presença, atividade, capacidade, autorização, término do turno e conclusão do handoff são fatos diferentes. |
| INV-06 | `idle`, `done`, timeout, silêncio ou desconexão não autorizam execução, conclusão, liberação de capacidade ou replay. |
| INV-07 | Observar/ler/abrir a central não aprova, responde, interrompe, reivindica ou reexecuta trabalho. |
| INV-08 | Um observador externo não produz recibos nativos, prova de ownership do Core, heartbeat de sessão MCP ou reserva de capacidade. |
| INV-09 | Handoffs preservam claim canônico único. MCP-only continua elegível conforme o contrato existente, sem obrigação de reportar capacidade externa. |
| INV-10 | Uma requisição repetida para recuperação mantém a identidade original. Nova tentativa produtiva exige intenção explícita e as regras canônicas. |
| INV-11 | Não colocar chaves em URLs, argumentos de processo, logs, screenshots, exemplos executáveis, exportações ou estado do browser. |
| INV-12 | Não fabricar qualificação de harness. Suporte ao formato de configuração MCP é distinto de suporte à execução nativa. |
| INV-13 | A fonte de verdade de mensagens, handoffs, aprovações e execução permanece nos subsistemas atuais. Novas tabelas são auxiliares, não novas filas de trabalho. |
| INV-14 | Não interpretar texto livre de prompt/log como comando Nexus, aprovação, identidade ou conclusão. |
| INV-15 | Não aumentar a superfície MCP indiscriminadamente. Priorizar ferramentas existentes e APIs específicas; qualquer parâmetro novo deve ter schema, testes e revisão de superfície. |
| INV-16 | O daemon é um modo de operação do Server/Connector existente; não cria outro domínio de execução, fila, scheduler ou identidade de agente. |
| INV-17 | Identidade da instância do serviço é distinta de agent_id, workspace e sessão. Perfis que usam a mesma instância não iniciam processos concorrentes sobre seus dados. |
| INV-18 | Resolver destino local/remoto antes de iniciar processos. Falha do Server remoto nunca cria um Server local substituto. |
| INV-19 | Só existe um supervisor ativo por instância. Serviço instalado é acionado pelo gerenciador correspondente, sem daemon avulso concorrente. |
| INV-20 | Iniciar/reiniciar serviço não concede autoridade nova, não renova grants e não repete operações de resultado incerto. Trabalho previamente autorizado segue admissão/reconciliação canônicas. |
| INV-21 | Fechar CLI/dashboard não significa parar serviço ou cancelar trabalho. Parada explícita não é tratada como crash para ressuscitar a instância. |
| INV-22 | Estado do processo, prontidão do serviço, conexão do harness e sucesso de uma tarefa são provas diferentes. |
| INV-23 | Consultas de status, logs e doctor padrão não iniciam o serviço nem inferência. A inicialização automática pertence a comandos de ação documentados. |
| INV-24 | Sobreviver ao terminal, reiniciar após falha, iniciar no login e operar sem login exigem evidências separadas; não prometer sobrevivência do processo a reboot. |
| INV-25 | O caminho padrão de conexão e uso cotidiano é completo pelo terminal, incluindo decisões com autoridade válida. Política organizacional explicitamente preexistente continua obrigatória; a configuração padrão nova não introduz dependência do dashboard. |
| INV-26 | O preset preenche a configuração comum do produto. Generalista é um perfil reutilizável, não uma identidade global compartilhada; reconnect não recria agente nem reaplica defaults sobre escolhas do usuário. |
| INV-27 | O preset preserva instruções, modelo, ferramentas e limites efetivos do harness quando suportados e verificáveis. Integração com Nexus não remove sandbox, não desabilita perguntas nativas nem concede administração global. |
| INV-28 | Serviço ativo ou sessão pronta não encerram M1: solicitar trabalho, decidir pedidos autorizados e recuperar resultados pelo terminal precisam estar demonstrados no caminho escolhido. |

Configurações de MCPs de terceiros e pontes nativas já existentes, como as necessárias ao Pi, não são alvo de remoção ou reescrita neste plano. A proibição se refere a introduzir um proxy/servidor MCP do Nexus nas novas integrações.

# 4. Modelo de produto

Não criar uma enumeração exclusiva de tipos de agente `MCP Participant / Observed / Managed`. Esses rótulos misturam dimensões independentes.

Representar, por instância/contexto, as seguintes dimensões:

| Dimensão | Exemplos | Autoridade |
|---|---|---|
| Participação na coordenação | MCP HTTP, cliente CLI/API autorizado, indisponível | Autenticação e serviços Nexus |
| Dono da execução | Core local, Core remoto, externo | Binding/ownership existente ou vínculo externo explícito |
| Origem da atividade | Core, hook externo, inferência Herdr, desconhecida | Proveniência da observação |
| Presença na coordenação | Presente, stale, offline | Sessões/atividade canônica existente |
| Atualidade da observação | Atual, expirada, fonte desconectada | Validade temporal do reporte |
| Capacidade e autoridade | Disponível/reservada/recusada/desconhecida; ações permitidas | Admissão, grants, leases e regras atuais |

Um agente externo com MCP pode cooperar e reportar atividade. Um agente apenas observado pode aparecer no painel, mas isso não prova que ele consegue ler mensagens ou reivindicar trabalho. Um agente gerenciado pode ter várias sessões simultâneas; uma sessão bloqueada não deve converter todas as demais em bloqueadas ou indisponíveis.

**Resultado esperado:** o usuário entende o que está conectado, o que está trabalhando, o que exige atenção e quais capacidades são realmente comprovadas, sem precisar conhecer tabelas, epochs ou protocolos internos.

**Primeiro uso:** inferir a pasta atual, detectar executáveis suportados no host correto e apresentar uma recomendação concreta. Se houver várias escolhas válidas, pedir somente a escolha necessária. Não inventar login do provedor, não assumir posse de uma sessão externa e não selecionar MCP-only apenas por exigir menos implementação interna. Para um harness com adaptador nativo qualificado, o caminho gerenciado pode ser a recomendação mais simples.

**Padrão de uso:** o setup já propõe identidade, workspace, perfil generalista e permissões de projeto; não pede que o usuário desenhe uma persona ou um papel especializado para começar. O usuário trabalha com o harness e encontra os recursos de coordenação do Nexus disponíveis no escopo aprovado. A interface edita esses mesmos objetos quando desejado. Quem conservar o padrão não precisa completar cadastros ou administrar o agente em outra tela.

# 5. Distribuição entre repositórios

| Frente | Nexus Server | Core | Connector |
|---|---|---|---|
| SVC | Lifecycle do Server, configuração da instância, readiness, comandos e integração com supervisor local | Apenas contratos/primitivas portáveis realmente compartilhados; sem I/O no import | Lifecycle do Connector, contexto de execução local, vínculo remoto e reconciliação existente |
| DX gerenciado | CLI de entrada e fachada do setup atual; autorização canônica e progresso | Catálogo, capacidades e adaptadores já existentes | Descoberta no host onde roda, aplicação local autorizada e progresso correlacionado |
| ATN | Read-model, regras de triagem, API de operador, UI, estado de visualização | Consumir os eventos existentes; mudança somente se faltar fato nativo indispensável | Preservar publicação de eventos/diagnósticos; sem triagem própria |
| DX MCP-only | Cliente CLI, onboarding UI, identidade/autorização, teste de participação | Renderização/validação declarativa compartilhável, separada dos templates gerenciados | Reutilização opcional desses contratos; manter o setup remoto atual |
| DX operações | Facade de cliente, idempotência canônica e espera correlacionada | Sem novo scheduler nem política de handoff | Diagnósticos e compatibilidade; evitar duplicar comandos de coordenação |
| OBS | Registro de fontes, autenticação restrita, ingestão, consulta e observador opcional | Sem responsabilidade obrigatória no MVP | Não obrigatório para observar um harness externo |

O Server concentra coordenação e experiência do produto. Esta revisão mantém as mudanças concretas de lifecycle no Connector introduzidas em R2. Não distribuir alterações artificialmente pelos três repositórios: Core muda somente se houver contrato compartilhado real. Se um componente não precisar mudar em uma etapa, declarar isso e comprovar compatibilidade.

## 5.1 Pontos de entrada existentes a revisar

Server:

```text
src/okto_nexus/application/observability.py
src/okto_nexus/application/agent_connection_status.py
src/okto_nexus/application/agent_runtime_administration.py
src/okto_nexus/application/execution_native_requests.py
src/okto_nexus/application/execution_native_decisions.py
src/okto_nexus/application/execution_session_views.py
src/okto_nexus/application/handoff_runtime_views.py
src/okto_nexus/application/connection_setup.py
src/okto_nexus/application/connection_test.py
src/okto_nexus/application/messages.py
src/okto_nexus/application/handoff.py
src/okto_nexus/application/poll_tokens.py
src/okto_nexus/adapters/inbound/cli/
src/okto_nexus/adapters/inbound/http/
src/okto_nexus/adapters/inbound/mcp/
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/runtimeApi.ts
frontend/src/useSSE.ts
frontend/src/components/onboarding/OnboardingModal.tsx
frontend/src/components/AgentConnectionsPanel.tsx
frontend/src/components/NativeQuestions.tsx
frontend/src/components/CanonicalNativeDecision.tsx
frontend/src/components/AgentRuntimeAdministration.tsx
frontend/src/components/RuntimeRecovery.tsx
frontend/src/views/ApprovalsView.tsx
frontend/src/views/HandoffsView.tsx
frontend/src/views/MetaHarnessView.tsx
frontend/src/views/ExecutionLogView.tsx
```

Core: revisar `src/nexus_connector_core/harness_config.py`, contratos/configuração portátil e testes de importação sem efeitos. Connector: localizar os implementadores atuais de `identity`, `connect`, `configure`, `doctor`, `status` e `mcp-config` a partir de `docs/cli.md` e `cli.main`. [B17] Não inventar caminhos internos não verificados.

## 5.2 Novos módulos sugeridos, não existentes presumidos

```text
# Server — nomes indicativos; adaptar à estrutura real sem monólitos.
domain/attention.py
domain/external_activity.py
application/attention.py
application/attention_sources.py
application/external_activity.py
application/observation_authority.py
application/coordination_request_receipts.py
application/participation_setup.py
adapters/outbound/sqlite/attention.py
adapters/outbound/sqlite/external_activity.py
adapters/outbound/observation/herdr.py
adapters/inbound/http/attention.py
adapters/inbound/http/observations.py
adapters/inbound/cli/init.py
adapters/inbound/cli/connect.py
adapters/inbound/cli/service.py
application/service_lifecycle.py
adapters/outbound/service_manager/
adapters/inbound/cli/doctor.py
adapters/inbound/cli/coordination.py
adapters/inbound/cli/observe.py
client/coordination.py
frontend/src/views/AttentionView.tsx
frontend/src/components/AttentionItem.tsx
frontend/src/components/ActivityBadge.tsx
frontend/src/components/onboarding/ParticipationSetup.tsx

# Core — contratos puros compartilháveis, sem lifecycle de aplicação em importação.
client_configuration.py
```

# 6. Fase 0 — inventário e contratos antes de alterar comportamento

**BASE-01 — registrar baseline.** Produzir `plans/agent_ops/baseline.md` com commits reais, versões, branches, instruções locais, comandos de teste disponíveis e funcionalidades já presentes.

**BASE-02 — rastrear caminhos.** Seguir pelo menos: pergunta nativa → decisão; handoff broadcast → claim MCP/runtime; criação de mensagem → inbox/outbox; setup → teste → Finish; renderer MCP → gravação do arquivo do cliente. Registrar os serviços e fronteiras transacionais encontrados.

**BASE-03 — separar documentação vigente e legado.** Corrigir, no escopo tocado, orientações conflitantes sobre `automatic_reply`, persistência em Next versus Finish, versões e credencial em query string. Não reativar controles removidos. O código e os testes vigentes decidem o comportamento; inconsistência documental deve gerar tarefa, não suposição.

**BASE-04 — criar ADR curto.** Formalizar dimensões ortogonais, fonte de verdade da central, telemetria sem autoridade e separação entre configuração de participante e configuração de runtime.

**BASE-05 — ledger de evidências.** Criar `plans/agent_ops/ledger.json` com tarefa, dependências, arquivos, testes, resultado, plataforma e limitações. Estados: `NOT_STARTED`, `IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`. Só marcar VERIFIED com evidência correspondente.

**BASE-06 — lifecycle e primeiro uso reais.** Localizar entrypoints foreground/background, arquivos de configuração, diretórios de dados, locks/PIDs, gerenciadores de serviço, vault, descoberta de harnesses, startup/shutdown, reconciliação e empacotamento nos três repositórios. Registrar a matriz real de plataformas e escolher um harness já suportado para a primeira campanha local e remota. Medir as etapas atuais entre instalação e primeira sessão útil. Não presumir ausência de daemon porque o fluxo atual exige um comando manual.

Para a rota padrão de R3, mapear também envio de solicitação à sessão, contexto efetivo do harness, perguntas/permissões, correlação de resultados e reencontro do trabalho após fechar o CLI. Registrar quais etapas já existem no terminal e quais exigem uma fachada pequena sobre os serviços atuais. Qualificar a rota por esse ciclo completo, não somente pelo suporte do adaptador à inicialização.

Ampliar BASE-04 com ADR de instância/supervisão, on-demand versus login, propriedade dos processos e semântica de stop/restart. Ampliar BASE-05 com componente, topologia, mecanismo de inicialização e prova de sobrevivência efetivamente executada.

**Aceite:** nenhum trabalho existente foi duplicado; os fluxos de coordenação, setup e lifecycle podem ser descritos por serviços e testes reais; falhas preexistentes estão separadas de regressões novas.

# 7. Frente SVC — daemon e serviço do usuário na primeira entrega

## 7.1 Resultado e limite da entrega

O usuário instala, executa a entrada de conexão no projeto e começa a usar o harness. O produto inicia/reutiliza o componente necessário, aguarda prontidão e mantém sua execução independente do terminal de configuração. Não exigir um segundo terminal para manter o Server ou o Connector ativos.

Entregar dois modos automáticos e preservar a execução em foreground:

| Modo | Comportamento | Uso padrão |
|---|---|---|
| Background sob demanda | Uma ação de conexão inicia a instância quando necessário e a reutiliza depois. | Caminho inicial, sem exigir instalação de serviço para experimentar o produto. |
| Serviço do usuário | Integração opt-in com o SO para iniciar no login e supervisionar falhas, conforme a plataforma qualificada. | Quem quer disponibilidade contínua durante sua sessão de usuário. |
| Foreground | Mesmo componente e mesmas regras, com processo vinculado ao chamador. | Diagnóstico, desenvolvimento, containers ou supervisor externo. |

Disponibilidade antes do login e após logout é um perfil operacional separado. Não ativar linger, serviços de sistema, privilégios administrativos ou acesso ampliado como efeito colateral do caminho inicial. A instalação de serviço pode integrar o resumo de consentimento inicial quando seu escopo estiver explícito; não criar confirmações repetidas para a mesma operação autorizada.

## 7.2 Topologias e propriedade

| Situação | Processo persistente necessário | Quem configura/inicia |
|---|---|---|
| Server e execução gerenciada na mesma máquina | Server com runtime local existente | CLI local controla a instância configurada. |
| Server remoto e execução nesta máquina | Server já acessível + Connector nesta máquina | CLI do Connector inicia/reutiliza seu serviço; não cria Server local. |
| Harness externo com MCP direto para Server remoto | Server remoto; processo do harness é externo | Configuração MCP não exige Connector ou daemon de execução local. |
| Instalação em container/supervisor externo | Componente em foreground sob o supervisor existente | CLI detecta o modo; não instala outro supervisor dentro do container. |

O daemon não adota automaticamente processos de harness iniciados em outro terminal. Execução gerenciada usa os adaptadores existentes; participação externa usa seu canal autorizado. Cada projeto preserva seu contexto, mas não precisa ganhar outro Server quando pertence à mesma instância.

## 7.3 Contrato comum de lifecycle

**SVC-01 — fachada de lifecycle.** Definir operações internas equivalentes a `inspect`, `ensure_running`, `start`, `stop`, `restart`, `install_user_service`, `uninstall_user_service` e `logs`. Reutilizar implementações existentes. CLI, onboarding e gerenciador do SO chamam o mesmo entrypoint de aplicação, com os mesmos dados e regras. Não criar um processo supervisor próprio de longa duração se o SO já atende ao contrato.

O contrato retorna componente, identidade da instância, versão ativa/instalada, configuração efetiva com segredos ocultados, supervisor, estado, prontidão, motivo e próxima ação. O Core pode compartilhar tipos puros e utilitários portáveis se isso reduzir duplicação; não recebe o banco, a política do Server nem efeitos no import.

## 7.4 Instância única e inicialização concorrente

**SVC-02 — propriedade e exclusão mútua.** Identificar a instância por configuração e diretório de dados canônicos, usuário efetivo e componente. Resolver aliases antes de adquirir lock. Usar exclusão mútua do SO/armazenamento com semântica documentada e revalidar após adquirir o lock. Não manter lock de banco/transação durante espera por rede.

Um PID, arquivo antigo ou porta aberta não basta para comprovar propriedade: correlacionar identidade da instância, processo e geração/início disponíveis. Tratar lock obsoleto e PID reutilizado sem matar processos alheios. Conflito de porta não autoriza mudar endpoint, abrir outra base ou iniciar segunda instância silenciosamente. Instâncias explicitamente diferentes permanecem isoladas.

**SVC-03 — iniciar ou reutilizar.** Resolver primeiro o perfil local/remoto. Se houver instância compatível pronta, reutilizar. Se estiver iniciando, aguardar a mesma inicialização com prazo limitado. Se existir serviço instalado, acioná-lo pelo supervisor; caso contrário, lançar o entrypoint existente em background de forma adequada à plataforma, sem shell interpolado e sem dependência do terminal pai.

Não implementar somente `nohup` e tratar isso como suporte completo. Desacoplamento de stdin/stdout/stderr, grupos de processo e sinais devem ser testados no SO alvo. Sob `launchd` ou outro supervisor, o processo principal permanece em foreground para ser acompanhado corretamente; a camada supervisionada não destaca outro processo e termina. [S03]

## 7.5 Prontidão e erros recuperáveis

**SVC-04 — prova de prontidão.** Distinguir `stopped`, `starting`, `ready`, `degraded`, `stopping` e `failed`, adaptando nomes à convenção vigente. Porta acessível não significa Nexus pronto: verificar identidade/compatibilidade, configuração carregada, armazenamento/migrações e condições seguras de admissão. No Connector, separar processo local saudável de vínculo remoto autenticado e capacidade de receber trabalho.

Restaurar/reconciliar fatos de execução antes de admitir trabalho nos escopos afetados. Operação incerta pode manter esse escopo bloqueado sem indisponibilizar consultas e escopos independentes. Falha de credencial, rede, versão, configuração ou migração deve apresentar causa específica. Timeout do cliente não mata automaticamente o serviço nem dispara outra inicialização; uma nova consulta recupera o estado existente. Cancelar a espera de conexão não cancela tarefas em andamento.

## 7.6 Serviço do usuário e plataformas

**SVC-05 — integração com o gerenciador do SO.** Instalar, habilitar, iniciar, parar, desabilitar e remover somente os recursos da instância selecionada. Operações repetidas devem reconhecer o estado atual. Registrar proprietário e revisão da definição instalada; configuração alterada pelo usuário exige reconciliação, não sobrescrita cega. Desinstalar o serviço preserva dados, histórico, projetos e credenciais; se estiver ativo, aplicar antes a parada controlada.

| Plataforma | Mecanismo candidato | Limite a declarar e testar |
|---|---|---|
| Linux com systemd | Unidade de usuário e supervisão pelo gerenciador do usuário | Linger é configuração separada para boot/continuidade após logout; não ativar implicitamente. Políticas de sessão podem encerrar processos apenas destacados. [S01, S02] |
| macOS | LaunchAgent do usuário | O agente pertence à sessão logada; LaunchDaemon de sistema é outro escopo. Validar comandos na versão alvo, pois a referência Apple é arquivada. [S03] |
| Windows | Tarefa no login no contexto do usuário ou mecanismo já adotado pelo projeto | Especificar gatilho, principal e tipo de logon; não chamar tarefa no login de Windows Service. S4U não é fallback universal para Connector, pois limita rede/arquivos criptografados. [S04] |
| Windows sem login | Windows Service, se houver requisito e suporte explícitos | Boot e identidade de serviço exigem campanha própria; interação com o usuário ocorre por interface separada. Não é requisito implícito do primeiro caminho local. [S05, S06] |

BASE-06 fecha a matriz apoiada pelo produto e o primeiro ambiente de campanha. O marco inicial deve comprovar Server e Connector em pelo menos uma plataforma real; não bloquear esse benefício até terminar todas as plataformas. Também não declarar uma plataforma suportada só porque seu template foi gerado. Qualificação adicional integra SVC-12 e o rollout.

## 7.7 Configuração e credenciais fora do terminal

**SVC-06 — contexto estável de execução.** Persistir referências necessárias a executável, ambiente/venv, configuração, dados e diretórios de trabalho usando caminhos resolvidos. Projetos mantêm seus caminhos próprios. Não depender de alias de shell, diretório corrente ou PATH do terminal usado no setup; não copiar indiscriminadamente todo o ambiente para a definição do serviço.

Verificar o acesso a credenciais no usuário e contexto reais do serviço. Login de provedor disponível no terminal pode não estar disponível em sessão não interativa ou cofre bloqueado. Exibir correção específica e usar mecanismos existentes, sem inserir segredos em argv, plist/unit, descrição de tarefa, logs ou URL. Segredo do operador não deve ser copiado para o host do Connector para facilitar onboarding.

Iniciar o serviço mantém as políticas de bind/origem/TLS e a superfície de rede configurada. Não expor interfaces administrativas remotamente para permitir controle local do daemon. Identidade técnica de serviço não substitui identidade de agente nem credencial de participante.

## 7.8 Parada, reinício e trabalho ativo

**SVC-07 — parada controlada.** Implementar política explícita de drain: bloquear novas admissões do escopo, persistir estado, aguardar operações em andamento conforme contrato e prazo, e só então encerrar. Se o prazo expirar, informar trabalhos ainda ativos/incertos e permitir decisão explícita de força; não converter timeout em sucesso ou cancelamento automático. Cancelar um pedido de parada e reabrir admissão exige transição clara e autorizada.

No fluxo solicitado pelo CLI, concluir o drain pela aplicação antes de pedir stop ao supervisor; não iniciar uma contagem de encerramento forçado do SO enquanto a interface ainda promete aguardar uma decisão do usuário. Coordenar os prazos e a política de processos filhos com o gerenciador escolhido. Quando o encerramento vier de fora — logout, shutdown, administrador ou falha — aplicar persistência/encerramento dentro do prazo disponível e registrar estado incerto para reconciliação posterior; não prometer que todo término externo pode ser impedido.

Solicitar drain pelo canal autorizado existente e manter disponíveis as operações necessárias para terminar trabalho já admitido: resultados, decisões autorizadas e reconciliação. Bloquear novas admissões produtivas, sem derrubar prematuramente os canais usados pelas operações em andamento. Um connect concorrente informa que a instância está parando; não cancela o drain nem inicia outra instância. Informar o alcance da parada quando vários projetos compartilham o mesmo serviço.

Definir a política de processos filhos com base no Core real. Não prometer preservar um harness após matar seu dono se não houver mecanismo comprovado de reconexão. `restart` segue o mesmo protocolo; parar serviço e cancelar tarefa são operações distintas. Uma parada solicitada não aciona recuperação automática. Um novo `connect` pode iniciar a instância novamente segundo a política documentada.

## 7.9 Recuperação e disponibilidade

**SVC-08 — reconciliação sem repetição de efeitos.** Reinício do serviço restaura configuração/estado e reutiliza recibos, identidades, bindings, grants e processos conforme os contratos atuais. Verificar ownership e estado real antes de retomar admissão. Processo supervisor perdido não comprova morte dos filhos nem permite liberar imediatamente claims, leases ou slots.

Grants expirados continuam expirados. Trabalho com resultado desconhecido permanece incerto; startup não cria outra tentativa, mensagem ou aprovação para resolvê-lo. Recuperação de falha usa backoff e limite observável pelo supervisor escolhido. Após esgotamento, expor falha acionável. O modo apenas destacado pode ter garantias menores de recuperação que um serviço supervisionado; declarar essa diferença.

Suspensão, perda de rede e retorno do Server exigem revalidação de autoridade e reconciliação. Reinício automático do daemon não equivale a reinício automático de inferências. Trabalho novo/previamente autorizado só avança pelo caminho canônico de admissão.

## 7.10 Atualização e compatibilidade

**SVC-09 — versão ativa e upgrade controlado.** Distinguir versão do CLI/pacote instalado da versão do daemon ativo. Reutilizar versões compatíveis; para incompatibilidade, apresentar atualização/retomada explícitas. Não atualizar nem matar trabalho silenciosamente durante `connect`.

Coordenar substituição do executável, ambiente, arquivos de serviço e migrações. Guardar referências suficientes para recuperação, mas não assumir rollback binário seguro depois de migração incompatível. Arquivos de serviço não podem continuar apontando para venv removido sem diagnóstico. Atualização concorrente com conexão preserva exclusão mútua e propriedade da instância.

## 7.11 Comandos operacionais e observabilidade

**SVC-10 — controles simples.** Expor status, logs, start, stop, restart e instalação/remoção do serviço, além de manter o entrypoint foreground atual. Os nomes seguintes são **propostas de interface**, a reconciliar com o parser; não são comandos já confirmados:

```bash
okto-nexus service status
okto-nexus service start
okto-nexus service logs --follow
okto-nexus service stop
okto-nexus service restart
okto-nexus service install --user --start-at-login
okto-nexus service uninstall --user
```

O CLI do Connector deve oferecer operações equivalentes em seu próprio namespace; preservar aliases e comandos existentes, sem impor um nome de executável não verificado. Status/logs/doctor são diagnósticos sem inicialização implícita. Aplicar ocultação de segredos, rotação/retenção e saída JSON/códigos estáveis. Logs inacessíveis ou endpoint indisponível não significam ausência de trabalho.

O sistema não precisa consultar um modelo para gerenciar o serviço. Supervisor do SO e serviço não dependem de dashboard aberto. Fechar o CLI após sucesso deixa o componente ativo; fechar o browser apenas encerra sua interface.

## 7.12 Connector remoto

**SVC-11 — mesmo lifecycle no Connector.** Implementar start/reuse, serviço do usuário, prontidão e parada no host de execução, usando configuração e vault atuais. Descoberta de diretório/harness ocorre nesse host. Reutilizar vínculo e identidade de executor no Server; queda/reconexão não refaz cadastro, não duplica executor e não repete trabalho.

Quando houver aprovação remota pendente, preservar seu identificador e mostrar estado/ação. O CLI autenticado do operador deve poder tomar a decisão canônica pelo terminal; o CLI participante sem essa autoridade apenas acompanha. Não copiar credencial administrativa para o host do Connector nem aceitar assentimento local do participante como decisão do operador. O link de painel é complementar, sem chaves. Política organizacional preexistente que exija outro canal deve ser identificada como tal, sem virar requisito da instalação padrão. Server remoto indisponível gera diagnóstico/retry de transporte limitado, nunca instalação de Server local ou fallback de identidade.

## 7.13 Evidências e aceite do primeiro marco

**SVC-12 — empacotamento, campanha e documentação.** Empacotar recursos de serviço, helpers e configuração necessários ao wheel/artefato final. Testar a instalação pelo pacote, sem depender do checkout. Produzir matriz por SO, versão, topologia, supervisor, sobrevivência ao terminal, recuperação de falha, início no login e acesso a credenciais. Testes isolados não alteram a instalação pessoal do usuário; campanhas reais seguem autorização já concedida no ambiente.

O primeiro marco SVC + DX exige: Server local e Connector remoto iniciados/reutilizados corretamente; preset útil aplicado e ciclo de trabalho completo com um harness nativo suportado pelo terminal; fechamento do terminal sem encerrar componentes de ownership do serviço; instância única sob concorrência; modo de serviço do usuário exercitado na plataforma da campanha; diagnóstico honesto quando faltam login/credencial/aprovação. A campanha inclui decisão canônica, resultado e reencontro do trabalho conforme DX-20. Início antes de login e restauração de um processo após reboot não são garantias desse aceite.

Conexão pronta é uma etapa intermediária de M1. O aceite também exige trabalho útil real solicitado de forma autorizada, acompanhado e concluído pelo fluxo canônico no terminal. Isso é uma exigência da campanha de validação, não autorização para enviar tarefa ou executar teste pago implicitamente ao iniciar o daemon. Sem ambiente/provedor autorizado para a campanha real, registrar o aceite correspondente como pendente.

# 8. Frente DX — onboarding e operações simplificadas

## 8.1 Intenção do usuário e caminhos internos

Começar por projeto e harness detectado. Apresentar um preset completo com seus efeitos: por exemplo, “usar este Claude Code como assistente deste projeto, com a configuração do harness e colaboração no workspace indicado”. Resolver identidade e autorização conforme a seção 8.11. Oferecer “usar meu cliente existente” quando essa for a intenção. Não exigir conhecer MCP, runtime ou Connector, escolher persona ou preencher formulários separados para avançar. Os caminhos técnicos abaixo continuam explícitos na revisão e na documentação, sem virar uma escolha arquitetural obrigatória na abertura.

**Participação na coordenação:** conectar uma identidade existente a um cliente MCP HTTP ou cliente de coordenação autorizado. Não exige runtime gerenciado, instalação nativa qualificada, binding de executor ou grant de execução do Core.

**Execução gerenciada:** utilizar o setup atual para Core local ou Connector remoto, preservando descoberta, aprovação, teste, grants e sessões. A evolução deve reduzir escolhas desnecessárias e melhorar diagnóstico, não contornar requisitos.

“MCP-only” não significa “agente não executa tarefas”: significa que o Nexus não é o dono de seu processo. Ele pode reivindicar e concluir handoffs pela via canônica que já possui.

## 8.2 Contrato de configuração de participante

**DX-01 — modelo declarativo próprio.** Criar um contrato puro para configurar clientes MCP externos, distinto de `HarnessHTTPTemplate` gerenciado. Campos: cliente/formato/versionamento, origem e endpoint aprovados, nome da entrada, mecanismo de referência de credencial e escopo de arquivo selecionado.

O Core pode abrigar esse contrato se ele for reutilizado por Server e Connector. A biblioteca não importa as aplicações, não lê credenciais, não faz HTTP, não modifica arquivos e não abre processos em importação. O host/CLI executa os efeitos autorizados.

Não aceitar uma chave `nxs_` fingindo ser `mcp-cap:`. Não relaxar `format_qualified` nem a proteção dos templates gerenciados. Não inferir que um cliente com suporte MCP tem adaptador de runtime correspondente.

**DX-02 — matriz de formatos.** Na ampliação da frente DX, entregar dois formatos de clientes efetivamente testados, preferencialmente Claude Code e Codex, e exportação genérica para configuração manual. O primeiro marco pode usar um adaptador nativo já qualificado; não deve esperar esta ampliação para entregar daemon + preset + ciclo de trabalho pelo terminal. Verificar o formato nas versões usadas na campanha. A opção genérica não deve afirmar que instalou ou testou um cliente desconhecido. Pi segue sua integração suportada; não inventar MCP HTTP nativo para ele.

## 8.3 Escrita segura da configuração

**DX-03 — plan/apply.** Gerar diff redigido antes da alteração. Aplicar somente a entrada escolhida, preservando outros MCPs, preferências, comentários quando o formato permitir e configurações sem relação com Nexus. Não executar comandos recuperados do arquivo de configuração.

Registrar hash/revisão de entrada e exigir CAS na aplicação. Se o arquivo mudou desde a revisão, parar e refazer o plano. Usar gravação atômica, backup protegido e reversão somente das mudanças de propriedade desta operação. Uma segunda aplicação idêntica não cria duplicata.

O browser não deve fingir editar arquivos na máquina do usuário: gera orientações/configuração ou chama efeitos no host realmente autorizado. Alteração em cliente remoto é realizada no próprio host remoto. Caminho do Server não substitui caminho do cliente.

**DX-04 — credenciais.** Importar a chave existente por prompt oculto, stdin ou referência de ambiente autorizada. Usar cofre do sistema quando disponível; fallback em arquivo restrito depende de consentimento explícito e política. Não criar chave permanente nova nem rotacionar a existente como efeito colateral de init.

Referência de ambiente no arquivo não basta: garantir e testar como o processo real do harness obtém o valor. Não dizer “pronto” se o launcher/GUI não herdar a variável. Não imprimir `export TOKEN=segredo`; explicar a instalação segura necessária. Exportações portáveis continuam sem chaves, grants ativos, caminhos e recibos de teste do host de origem.

Autenticação deve usar header Bearer. Selecionar a origem explicitamente, não seguir redirecionamento para enviar credencial a outro host. Respeitar a política de transporte atual do Server, alertar sobre plaintext e não afrouxá-la automaticamente. Corrigir o placeholder antigo do onboarding sem quebrar compatibilidade de clientes legados por mudança incidental.

## 8.4 CLI de entrada

Usar o executável atual `okto-nexus`, não introduzir um nome obrigatório `nexus` que possa conflitar com outros produtos. Comandos abaixo são **interfaces propostas**, sujeitas a ajuste consistente no parser:

```bash
# Entrada principal proposta: projeto atual e detecção de harness.
okto-nexus connect
okto-nexus connect --client claude --project .

# Caminho explícito de participante e compatibilidade de init.
okto-nexus init --mode participant --client codex --project . --plan
okto-nexus doctor --profile reviewer
okto-nexus agents list --workspace <workspace-id>
```

**DX-15 — connect como entrada principal.** Implementar a fachada que resolve perfil/topologia, chama SVC para iniciar/reutilizar o serviço local apropriado e conduz o setup pelo terminal. Usar os serviços e autorizações atuais; não duplicar o Finish gerenciado. Aplicar o preset de DX-18/19 e encaminhar diretamente ao percurso de trabalho de DX-20. O dashboard é uma opção durante todo o uso padrão; seus links não substituem controles de terminal necessários a decisões rotineiras. Instalações já configuradas reutilizam o vínculo e não repetem o wizard. Política organizacional preexistente que imponha outro canal permanece válida e é diagnosticada separadamente.

**DX-16 — descoberta e revisão mínima.** Detectar pasta atual e executáveis suportados no host correto; a existência no PATH é descoberta, não qualificação nem login confirmado. Reutilizar a escolha anterior ou pré-selecionar uma recomendação válida; havendo ambiguidade material, pedir somente a escolha necessária. Mostrar projeto/workspace, harness, identidade sugerida ou reutilizada, efeito de execução e mudanças de configuração em um resumo revisável. Permitir escolher início no login nessa mesma revisão, sem tornar instalação de serviço um pré-requisito. A autorização já válida é reutilizada; criação de agente, ampliação de escopo e autorização de execução são ações explícitas nos serviços existentes, reunidas na mesma revisão quando o operador possui autoridade.

**DX-17 — progresso, retomada e primeira sessão.** Preservar `setup_run_id`, revisões e recibos do fluxo atual. Mostrar etapas verificáveis: serviço pronto → identidade/vínculo autorizado → configuração aplicada → harness/sessão pronta → interação disponível no terminal. Se ocorrer perda de resposta, consultar o mesmo setup antes de repetir. Distinguir “serviço disponível”, “cliente precisa recarregar”, “aguardando aprovação” e “sessão pronta”; nenhum deles equivale a tarefa concluída. Login de provedor ausente exige instrução concreta no contexto do usuário, sem tentar autenticar uma pessoa dentro do daemon. Depois da conexão, permitir a primeira solicitação real e seu acompanhamento conforme DX-20; o smoke continua opcional e consentido. Não enviar trabalho automaticamente.

O fluxo padrão do terminal é: executar `connect` na pasta → confirmar o resumo necessário → trabalhar com o agente e acompanhar o resultado. Não há um passo “abra o dashboard para terminar de configurar”. Uma política ou falha real pode exigir intervenção adicional, mas não acrescentar perguntas apenas para reproduzir conceitos internos. No host do Connector, integrar seu CLI existente ao percurso, apontando para o Server remoto configurado; decisões de operador podem ocorrer em outro terminal autenticado, sem transportar sua credencial para esse host.

**DX-05 — init.** Preservar o caminho explícito/compatível de participante, compartilhando a implementação de setup com connect. Escolher Server, identidade e workspace; validar identidade; produzir/revisar configuração; aplicar com consentimento; orientar restart/reconnect do cliente quando necessário; validar o nível realmente alcançado. Uma identidade ausente exige criação explícita pelo operador usando os serviços existentes. O `init` de agente não se autoeleva a operador.

Persistir `setup_run_id` e progresso não secreto suficiente para retomar a mesma configuração. A preparação não autoriza tarefas nem inicia o modelo. Se a identidade já tiver runtime, acrescentar um cliente participante não deve desligar o runtime globalmente ou substituir bindings existentes. Informar que o endereço é a identidade, não o cliente: acrescentar um canal não garante que ele será o consumidor de cada mensagem. Preservar a seleção e a reserva exclusiva da entrega lógica já existentes; não fan-out para todos os meios da mesma identidade. Uma identidade separada só é criada quando o operador explicitamente deseja outro agente, não como solução automática para ambiguidade de transporte.

**DX-06 — sem transação distribuída fictícia.** Identidade no Server, cofre local e arquivos do cliente não participam da mesma transação. Registrar etapas e compensações explícitas. Não chamar o setup inteiro de atômico. Preservar o Finish transacional que já existe para a parte gerenciada. Falha local não autoriza apagar uma identidade preexistente no Server.

## 8.5 Diagnóstico por níveis de prova

**DX-07 — doctor estruturado.** Retornar checagens independentes com `PASS`, `FAIL`, `UNKNOWN` ou `NOT_APPLICABLE`, motivo e próxima ação:

| Nível | O que demonstra | O que não demonstra |
|---|---|---|
| Serviço local | Instância, supervisor, versão e prontidão quando verificáveis | Harness autenticado ou tarefa executada |
| Endereço acessível | Reachability e versão anunciada | Autenticação ou capacidade de executar |
| Identidade autenticada | Credencial válida para o agente correto | Permissão para qualquer ação |
| Configuração do cliente | Entrada válida e referência de segredo resolvível no contexto testado | Cliente já recarregou o arquivo |
| MCP negociado | Transporte inicializado e superfície compatível | Modelo chamou as ferramentas |
| Participação comprovada | Agente abriu sua sessão/trocou a mensagem de teste | Handoff concluído |
| Handoff de teste comprovado | Claim e resultado canônicos correlacionados | Qualificação de todos os cenários de runtime |

Doctor padrão não inicia o daemon, não instala serviço, não inicia inferência, não envia trabalho, não abre processo de harness, não executa probes sem consentimento e não modifica configuração. Checks ativos ficam explícitos e explicam efeito/custo. Distinguir resultado desconhecido de falha comprovada.

**DX-08 — smoke de cooperação.** Oferecer teste opcional com correlação própria. Validar primeiro uma troca dirigida e depois um handoff explicitamente consentido. O resultado válido é a cadeia canônica observada, não a presença de uma string na resposta do modelo. Não mudar o teste gerenciado `NEXUS_CONNECTION_OK` para prometer o que ele não prova.

## 8.6 Operações de alto nível

```bash
# Conversa/informação; não substituir tarefas por mensagens.
okto-nexus message send --to reviewer --workspace <workspace-id> \
  --subject "Contexto da revisão" --body-file contexto.md

# Trabalho com ownership e ciclo de vida canônicos.
okto-nexus handoff create --to reviewer --workspace <workspace-id> \
  --title "Revisar implementação" --body-file tarefa.md --wait

# Reabrir somente a observação do mesmo trabalho.
okto-nexus handoff wait <handoff-id> --timeout 300
okto-nexus request inspect <request-id>
```

**DX-09 — cliente fino, não orquestrador.** Implementar fachada reutilizável por CLI e scripts. Comunicação direta com o Server via transportes existentes; pode usar MCP HTTP como cliente, nunca como proxy. Escolher uma superfície canônica por operação e documentá-la. Não escrever diretamente nas tabelas a partir da CLI remota nem duplicar regras de domínio.

A identidade vem da autenticação; `--to` escolhe destinatário, nunca ator. Campos de sessão/contexto devem preservar proveniência e afinidade existentes. Não abrir uma sessão nova por comando se isso mudar involuntariamente a conversa. Perfis/sessões explícitos devem expor o ciclo de vida; um processo observador não mantém falsamente vivo um agente que não está participando.

Não adivinhar intenção por LLM: `message send` é conversa/informação; `handoff create` é trabalho. Não converter estratégia de roteamento em broadcast para obter execução automática. Handoffs dirigidos, broadcast e claim MCP continuam usando os comportamentos existentes.

## 8.7 Idempotência de criação: requisito antes de prometer retry seguro

**DX-10 — verificar e complementar deduplicação.** Mapear o caminho real de criação de mensagens/handoffs. Reutilizar mecanismo existente apenas se sua chave, escopo e transação forem compatíveis com uma requisição de coordenação. Caso contrário, adicionar `client_request_id` opcional às entradas apropriadas e um recibo canônico mínimo.

Chave lógica: instalação + ator autenticado + workspace + operação + `client_request_id`. Hash semântico exclui segredos, mas inclui alvo, conteúdo e contexto relevantes. Mesmo ID/hash retorna a decisão/objeto existente; mesmo ID com conteúdo diferente conflita. Retentativa continua sujeita à autenticação e visibilidade atuais.

O recibo deve ser confirmado na **mesma transação** da mensagem/handoff, inbox/outbox, evento e contabilização aplicáveis. Não implementar “criar por HTTP e gravar recibo depois”, nem um lock em memória que desaparece no restart.

A decisão `pending_approval` também é deduplicada: não criar segunda aprovação. A execução posterior usa o caminho existente, preservando a identidade da requisição e autoridade original. Campos internos de bypass de aprovação nunca se tornam parâmetros da CLI/API.

Retenção de recibos deve ser explícita, limitada e compatível com a retenção dos recursos. Dentro da janela garantida, um recurso removido não pode ser recriado pela repetição: responder com referência/tombstone apropriada. Fora da janela, o cliente recusa replay automático e exige revisão; não alegar idempotência infinita ou exactly-once de efeitos externos.

A CLI grava o ID antes de transmitir. Resposta perdida é tratada por consulta do mesmo ID. Não gerar novo ID automaticamente em timeout. Em Server antigo sem esse contrato, diagnosticar a limitação e não oferecer replay seguro fictício.

## 8.8 Semântica de espera

**DX-11 — espera correlacionada.** `handoff wait` observa o handoff identificado, seu resultado e verificação quando exigida. Para operação nativa, quando exposta, observar `operation_id` exato. Mensagem entregue/lida não é execução concluída; um futuro `message --wait` deve exigir condição explícita, como entrega, leitura ou resposta correlacionada.

Timeout encerra a espera, não cancela o trabalho. Ctrl+C encerra o observador; cancelamento exige comando explícito. Resposta do cliente deve incluir IDs recuperáveis e estado atual. Estado incerto é distinto de falha e de sucesso.

Evitar corrida entre snapshot e assinatura: usar cursor e releitura canônica, cobrindo conclusão antes de a espera iniciar. Não depender apenas de um evento futuro. Respeitar long-poll/capacidades da versão instalada e o orçamento de conexões. Nunca manter transação SQLite aberta durante uma espera de rede.

Saída JSON deve ser estável. Códigos de saída precisam distinguir comando válido, erro de uso, recusa, timeout de observação e resultado incerto sem conflitar silenciosamente com convenções existentes. Documentar a matriz exata após revisar o parser atual.

## 8.9 Evolução do dashboard e do Connector

**DX-12 — UI orientada à intenção.** Evoluir a introdução atual em coerência com connect: projeto/harness e o mesmo preset; “usar meu cliente existente” continua disponível. O dashboard consome o mesmo setup, identidade, configuração e estados, sem obrigar a troca do terminal para o navegador em qualquer etapa do uso padrão. Abrir o painel posteriormente não inicia outro onboarding nem cria outro agente. Mostrar capacidades/resultados comprovados, não um único selo verde que mistura todos os níveis. Manter configurações avançadas acessíveis e opcionais.

**DX-13 — caminho gerenciado.** Reutilizar Connections e seu Finish. Não ressuscitar `automatic_reply` como opção independente; o código atual normaliza esse campo. Não aplicar política runtime=false ao agente inteiro somente porque ele recebeu outro participante externo.

**DX-14 — Connector.** Preservar `connect/configure/status/doctor`, aprovação assíncrona e vault existentes, integrando-os a SVC-11 e DX-15…21. Melhorar mensagens e referência aos mesmos códigos de diagnóstico. Somente compartilhar contrato declarativo onde há benefício real; não copiar uma nova implementação de credenciais/conexão para cada aplicação. Alterações no Core exigem pins/locks e testes coordenados, não mudança de NXL sem necessidade.

## 8.10 Aceite da frente DX

O primeiro marco aplica o preset e demonstra trabalho completo com um harness de adaptador existente pelo terminal, com o serviço persistente pronto: solicitação autorizada, acompanhamento, pergunta/permissão representativa, resultado correlacionado e reencontro do trabalho ao reabrir o CLI. O percurso normal exige zero visitas ao dashboard e zero edição manual de configuração quando os pré-requisitos de harness/provedor estão atendidos. A mesma identidade e configuração continuam válidas no uso posterior.

Interações do usuário com a sessão usam os contratos nativos existentes; quando houver delegação de trabalho entre agentes, usar handoff canônico. Não forçar cada prompt humano a se tornar um handoff, nem usar mensagem de informação como substituto de uma operação produtiva. Perda de resposta não duplica mensagens, aprovações ou trabalho. O fluxo remoto continua funcionando sem credencial de operador no host do Connector. A frente DX completa também permite conectar dois clientes MCP testados sem desenvolver adaptador nativo; a configuração de outros MCPs permanece intacta e doctor informa exatamente o que sabe.

## 8.11 Preset inicial completo e uso cotidiano sem painel

**DX-18 — preset generalista de projeto.** Definir um preset pequeno e versionado, resolvido para a configuração comum do produto antes da aplicação. Não introduzir um “modo simples” com armazenamento, autoridade ou executor próprios. O preset deve ser útil sem especialização posterior; nome, papel, ferramentas adicionais e políticas mais sofisticadas ficam disponíveis como ajustes opcionais.

| Aspecto | Padrão proposto | Regra de aplicação |
|---|---|---|
| Identidade | Nome legível sugerido a partir de harness/projeto, com `agent_id` persistente. | Reutilizar vínculo canônico já configurado. Criar identidade nova somente como ação explícita do operador no resumo inicial; não associar só por nome ou pasta. |
| Projeto e workspace | Pasta atual e workspace canonicamente associado, quando houver. | Se faltar workspace, incluir sua criação autorizada ou seleção necessária na mesma revisão; nunca presumir que igualdade de caminhos comprova acesso. |
| Papel | Assistente generalista capaz de realizar o trabalho solicitado no projeto. | Não exigir persona ou especialidade. O perfil não é um agente global compartilhado entre usuários ou projetos. |
| Harness | Modelo, instruções do projeto, ferramentas e políticas já configurados e suportados na rota escolhida. | Validar a configuração efetiva no processo real; diferenças de launcher/serviço devem ser explicadas antes do uso. Não remover sandbox nem desabilitar decisões nativas. |
| Trabalho no projeto | Ler, editar e executar ferramentas conforme as permissões efetivas do harness e a autorização do usuário. | O preset não vira um assistente apenas de leitura, mas também não amplia automaticamente acesso a outros projetos, shell, rede ou credenciais. |
| Coordenação Nexus | Descoberta dos colaboradores visíveis, própria inbox, contexto autorizado, mensagens e participação em handoffs no workspace aprovado. | Mapear cada ação ao catálogo e aos contratos atuais; claim, resultados, destinatários e admissão continuam sujeitos às políticas canônicas. |
| Execução gerenciada | Permitir sessões para trabalho autorizado nesse projeto, incluindo solicitações elegíveis de colaboradores autorizados quando esse for o perfil aprovado. | Explicar esse efeito no resumo, usar grants/admissão atuais e respeitar revogação. Estar online não autoriza executar qualquer mensagem recebida. |
| Operação | Serviço sob demanda, controles pelo terminal e opção explícita de início no login. | O serviço continua independente do painel. Diagnóstico não inicia trabalho e o setup não dispara um turno produtivo. |

O agente deve receber identificação e instruções mínimas para usar a coordenação disponível, pelos mecanismos de configuração/contexto já suportados. Não reescrever a personalidade do harness nem sobrescrever instruções do projeto para impor uma persona Nexus. Instruções e descrições de ferramentas orientam comportamento; a autoridade é verificada pelos serviços, nunca pelo prompt.

**DX-19 — uma revisão significativa para aplicar o preset.** Resolver os defaults e mostrar um resumo legível de identidade, projeto/workspace, harness e o que o Nexus poderá iniciar ou encaminhar ali. Reunir criação autorizada de agente/workspace, participação e configuração de execução quando necessárias; o usuário não percorre formulários administrativos separados para cada objeto. Oferecer expansão dos detalhes e edição opcional, sem transformar todos os campos internos em perguntas.

Usar o mesmo `setup_run_id`, revisão, autorização e Finish existente. Uma confirmação de produto cobre efeitos concretos previamente mostrados; não transforma as etapas de Server/cofre/host em transação distribuída. Se a autorização ou a configuração mudar antes do commit, refazer a parte afetada da revisão. Operador sem autoridade recebe a pendência real; participante não pode criar agentes ou conceder grants para eliminar a pendência. O preset não concede administração global, mudança de políticas ou aprovação dos próprios pedidos ao agente. Reabrir o setup após resposta perdida recupera o mesmo resultado, sem novos agentes ou permissões.

**DX-20 — ciclo cotidiano completo no terminal.** Disponibilizar, no caminho padrão qualificado, solicitar trabalho e continuar a conversa, acompanhar o estado, responder a perguntas, aprovar ou recusar pedidos autorizados, obter resultado e reencontrar trabalho/sessão ao voltar. Preferir a interação nativa já suportada pelo harness; quando a rota gerenciada não a expuser, implementar a menor fachada CLI necessária sobre as operações, perguntas, decisões e consultas canônicas existentes. Não criar um histórico de conversa paralelo nem interpretar logs/prompts como comandos de controle.

Cada decisão deve preservar principal autorizado, ID do pedido, revisão, validade, escopo, correlação e opções canônicas. Resposta livre enviada ao modelo não substitui endpoint de aprovação. Uma pergunta ao agente continua destinada ao agente; um terminal participante não toma decisões de operador. O operador pode usar outro CLI autenticado, sem distribuir suas credenciais ao Connector ou ao harness. Perguntas/permissões rotineiras do padrão precisam de uma apresentação no terminal; um link obrigatório para o painel não satisfaz esse requisito.

Submissão e acompanhamento mantêm a identidade da requisição e da operação ou handoff. Antecipar da DX-09…11 somente a fachada, deduplicação, correlação e espera usadas por M1, reutilizando os recibos nativos comprovados quando suficientes. Não oferecer uma nova submissão com retry inseguro para depois corrigir na PR-05. Persistir a referência antes de transmitir quando o contrato permitir; uma resposta perdida leva a inspeção/recuperação do mesmo pedido. Se a versão não permitir recuperar o resultado com segurança, expor incerteza e não repetir produtivamente.

Fechar o CLI encerra a observação, não cancela a execução pertencente ao serviço. Ao voltar, reencontrar perfil, `agent_id`, workspace e referências canônicas de conversa/trabalho; retomar a sessão quando isso for suportado. Se a sessão não puder ser retomada, apresentar o resultado/estado recuperado e a opção explícita de nova sessão com o contexto autorizado disponível, sem fingir continuidade nem repetir a tarefa anterior. Não prometer attach à TUI original, adoção de processo externo ou sobrevivência a reboot sem qualificação específica.

Um adaptador que apenas inicia o processo, mas obriga o usuário a abrir o dashboard para trabalhar ou decidir pedidos normais, não qualifica a rota padrão de M1. Completar a fachada mínima ou escolher outra rota já suportada que cumpra o ciclo, mantendo os contratos de execução. O objetivo não exige desenvolver um multiplexer PTY. Colaboração usa os caminhos canônicos disponíveis no preset; expansão para outros clientes e comandos genéricos permanece em M2.

**DX-21 — preservar configuração e permitir evolução opcional.** Guardar a origem/revisão do preset nos mecanismos de configuração existentes, quando necessário para explicar sua aplicação. Reconectar não reaplica defaults, troca modelo, reseta nome/papel/permissões ou cria outra identidade. Atualização futura de preset não amplia acesso automaticamente: apresentar diff dos efeitos e reaproveitar o fluxo autorizado. Evitar uma nova infraestrutura genérica de templates para suportar esse único preset.

O dashboard e o CLI leem os mesmos objetos. Alterar especialização, nome ou opções na interface mantém identidade, histórico e vínculos, sujeito às revisões e autorizações canônicas. O usuário que nunca personaliza continua podendo executar o ciclo padrão indefinidamente, enquanto suas credenciais e políticas permanecerem válidas. Documentação de início rápido deve terminar em trabalho útil e explicar apenas os controles necessários; administração avançada é opcional.

# 9. Frente ATN — central de atenção

## 9.1 Escopo inicial da central, após o primeiro marco de uso pelo terminal

Criar uma visão de operador com dois grupos: **Precisa de ação** e **Acompanhar**. Inicialmente, usar somente fatos que o Nexus já controla. A integração externa entra depois.

Não começar por notificações de sistema operacional, integrações Slack/e-mail ou um motor genérico de regras. Não usar LLM para classificar estados.

## 9.2 Catálogo inicial de ocorrências

| Código proposto | Condição | Categoria e ação |
|---|---|---|
| `native_permission_pending` | Pedido nativo pendente, não expirado, decidido pelo operador | Precisa de ação → abrir controle canônico de aprovação |
| `native_question_pending` | Pergunta pendente cujo interlocutor autorizado é o operador | Precisa de ação → formulário canônico de resposta |
| `question_waiting_for_agent` | Pergunta destinada a outro agente | Acompanhar; não oferecer resposta humana com identidade emprestada |
| `verification_pending` | Handoff VERIFYING | Ação somente para um verificador humano autorizado; caso contrário acompanhamento |
| `execution_outcome_unknown` | Operação canônica requer reconciliação | Precisa de ação quando há procedimento humano; abrir inspeção, nunca retry genérico |
| `delivery_parked` | Entrega exige intervenção conforme estado canônico | Precisa de ação → inspeção/recuperação existente |
| `runtime_recovery_attention` | Recuperação automática esgotada ou bloqueio permanente registrado | Precisa de ação → diagnóstico e controles autorizados |
| `execution_authority_blocking` | Trabalho efetivamente pendente bloqueado por grant/configuração revogada ou expirada | Precisa de ação → revisar autorização; não autorizar automaticamente |
| `executor_disconnected_with_work` | Executor sem comunicação e trabalho relevante pendente | Acompanhar durante recuperação; escalar apenas por condição explícita/limiar configurado |
| `handoff_unclaimed_aged` | Handoff OPEN, elegível e sem claim além do limiar | Acompanhar → mostrar motivos de elegibilidade/capacidade disponíveis |
| `result_unseen` | Novo resultado canônico ainda não visualizado pelo operador | Acompanhar; não alterar status de tarefa ao marcar como visto |
| `cleanup_attention` | Resultado produtivo já bem-sucedido, mas limpeza requer intervenção | Acompanhar/ação de manutenção, separado do sucesso produtivo |

`CLAIMED` não é sinônimo de travado. Falta de eventos durante inferência não é prova de falha. Handoff aguardando dependência não deve ser classificado automaticamente como problema. Executor offline sem trabalho pode ser apenas informação de conexão.

Cada classificador deve declarar predicado, fontes, destinatário da ação, prioridade, condição de encerramento, uso de tempo e teste de não ocorrência.

## 9.3 Modelo da ocorrência

Campos mínimos propostos:

```text
attention_id                 identificador estável do episódio
kind                         tipo fechado de ocorrência
category                     action_required | watch
severity                     info | warning | error
agent_id, workspace_id       escopo canônico quando aplicável
session_id, operation_id      opcionais; nunca inventados
source_type, source_id        referência ao fato original
source_revision              versão do fato usado na projeção
first_detected_at             início estável; não a cada refresh
last_changed_at               última mudança material
freshness                     current | stale | unavailable
summary_code                  código traduzível; texto externo é dado
allowed_actions               ações derivadas para o operador atual
resolution                    open | resolved | expired
seen_state                    estado de visualização independente
```

A origem canônica resolve a ocorrência. O estado auxiliar do usuário só registra visto/adiado. Uma ocorrência nova no mesmo objeto recebe novo episódio; um refresh, reconnect SSE ou leitura não deve produzir uma nova ocorrência.

Para fatos com revisão/evento, derivar a identidade do episódio dessas referências. Para limiares temporais, usar a referência estável da condição que iniciou a espera. Nunca usar o horário de cada GET como identidade.

## 9.4 Persistência e consultas

**ATN-01 — serviço de projeção.** Compor consultas em lote sobre aprovações, perguntas, handoffs, receipts, recuperação e entregas. Retornar referências, não duplicar payloads secretos. Reutilizar serviços/ports quando disponíveis; evitar N+1 e consultas sem limite.

**ATN-02 — armazenamento auxiliar.** Persistir somente seen/snooze e, se indispensável, uma projeção materializada reconstruível com referências de origem. Não criar uma nova fila de handoffs ou aprovações. Modelar a preferência sob o principal de operador já existente; não adicionar usuários/agentes apenas para suportar o painel. Em uma instalação de operador único, documentar esse escopo compartilhado entre dispositivos.

**ATN-03 — transações e leitura.** GET não materializa decisões nem altera lifecycle. Atualizações de projeção devem ocorrer após confirmação do fato original ou em manutenção limitada. Auditoria/autenticação já existente continua separada; não alterar seus contratos sob pretexto de leitura pura.

**ATN-04 — API.** Propor `GET /api/v1/attention`, `GET /api/v1/attention/summary` e ações explícitas de visto/adiado. Usar envelope, autenticação de operador e controles de origem do produto. Os nomes podem ser adequados na implementação; seus contratos devem permanecer únicos e versionados.

Filtros mínimos: workspace, agente, categoria, tipo, estado e prioridade. Paginação por cursor com desempate estável. Resumo e lista devem aplicar os mesmos filtros e autorização. Um cursor não pode ampliar visibilidade.

Decisões de aprovação, respostas, cancelamentos e recuperação continuam nos endpoints existentes. `allowed_actions` é uma descrição para renderização, não uma autorização permanente: o endpoint de comando revalida tudo.

## 9.5 Atualização em tempo real

**ATN-05 — SSE e reconciliação da visão.** Reutilizar o canal SSE como notificação de invalidação; ler a projeção canônica em resposta. Reunir rajadas, não buscar todos os dados a cada token. Se um fato relevante não gerar evento, acrescentar um evento mínimo após commit ou usar refresh limitado da visão; não criar um monitor por agente.

No reconnect, obter snapshot e cursor coerentes. Eventos perdidos, retenção ou gap exigem novo snapshot. Tempo também muda condições: validade e limiares precisam de refresh/maintenance limitado, mesmo sem um novo evento.

Erros de rede mantêm a última visão autorizada com aviso de desatualização; negação/revogação de autorização limpa conteúdo e contadores protegidos. Nunca transformar falha de leitura em “nenhuma pendência”.

## 9.6 Experiência de operador

**ATN-06 — UI integrada.** Adicionar item ao menu e badge global. Preservar Graph, Meta-harness e páginas especializadas. Mostrar agente, contexto, motivo, idade, origem/atualidade e ação principal. Permitir abrir a sessão ou o registro original sem navegar por várias telas.

Reutilizar `CanonicalNativeDecision`, controles de perguntas e inspeção existentes. Não construir outra implementação de aprovação dentro do cartão.

**ATN-07 — interação segura.** Visto não resolve. Adiado não aprova nem suspende a execução. Aprovar mantém confirmação e fencing atuais. Resultado desconhecido oferece inspeção; nunca um botão “repetir tudo”. Ações sobre fatos que mudaram exibem conflito e recarregam a situação.

**ATN-08 — acessibilidade.** Navegação por teclado, foco previsível, textos que não dependem de cor, estados vazios distintos de erro e light/dark conforme o dashboard. A abertura da página não deve mostrar toasts repetidos de todo o histórico.

## 9.7 Aceite da frente ATN

A tela identifica os bloqueios reais com uma única navegação; cada ação abre o comando canônico correto. Aprovação vencida não permanece acionável. Um resultado já visto não reaparece por simples reconnect. Fechar um alerta não modifica trabalho. Um handoff normal em execução não gera falso incidente. A central funciona sem Herdr e sem observações externas habilitadas.

# 10. Frente OBS — atividade externa opcional

## 10.1 Escopo e exclusões

Criar contrato de telemetria para estado de instâncias externas. Ele não controla terminal, não envia prompts, não conclui handoffs e não gerencia processos. A cooperação continua por MCP HTTP/cliente autorizado. Para harness sem canal de cooperação, a observação não finge que o canal existe.

Não fazer scraping de terminal dentro do Nexus. O adaptador Herdr consome o estado que o Herdr expõe, identifica sua natureza reportada/inferida e não transforma inferência em prova nativa.

## 10.2 Modelo de fonte e instância

**OBS-01 — vínculo explícito.** Registrar uma fonte de atividade para uma identidade existente e workspace aprovado. Não associar agente pela igualdade de nome, hostname, diretório ou pane. Exigir seleção explícita e autenticação/consentimento compatível.

Entidades auxiliares propostas:

```text
ObservationSource
  source_id
  agent_id
  allowed_workspace_ids
  source_kind                herdr | hook | custom
  source_registration_revision
  enabled / revoked_at

ObservedInstance
  observed_instance_id
  source_id
  workspace_id
  external_instance_ref      identificador opaco
  generation                 emissão/fencing controlados pelo Server
  optional_canonical_session_ref
  last_sequence
  activity_state
  activity_evidence          reported | inferred
  observed_at / received_at / valid_until
  current_completion_ref     opcional, sem significado de handoff
```

Sessão externa não é automaticamente sessão de coordenação nem de runtime. Correlação opcional com sessão canônica exige evidência e autorização; sem ela, mostrar instância externa separada. Suportar várias instâncias da mesma identidade sem sobrescrever seu estado agregado.

## 10.3 Vocabulário de atividade

Estados propostos: `working`, `idle`, `blocked`, `unknown`. Representar término observado como transição/evento ou `completion_ref`, não como sucesso de tarefa.

Herdr pode apresentar `done` como ocioso com conclusão ainda não vista. Normalizar para atividade ociosa e, quando existir referência/seq de conclusão válida, um evento de término observado. A visualização no Nexus não deve chamar focus nem alterar o seen do Herdr. [H02]

Falha de fonte, estado ausente e término observado são distintos. Um observador desconectado não declara que o processo morreu; uma observação expirada não declara que ele ficou ocioso.

## 10.4 Autenticação e autorização da telemetria

**OBS-02 — capacidade restrita.** Reutilizar a infraestrutura de credenciais escopadas quando apropriado, sem ampliar os EPTs de leitura existentes. Caso seja necessária uma nova família de token, ela deve ser opaca, revogável, armazenada com proteção/hash apropriado, de curta duração e aceita exclusivamente nos endpoints de telemetria previstos.

A emissão é autorizada pelo agente para sua própria fonte/escopo, quando a permissão correspondente existir, ou pelo operador através dos mecanismos atuais. Uma autorização limitada nunca cria permissão que o emissor não possui. Não criar outro agente nem uma nova chave permanente canônica. Registrar permissões técnicas específicas, por exemplo `observations.manage_self` e `observations.publish`, com concessão explícita no catálogo/preset apropriado; não ampliar silenciosamente permissões de identidades existentes. Essas permissões não são skills nem capabilities de roteamento. A credencial de publish não autoriza gerenciar fontes ou emitir credenciais sucessoras por conta própria.

O processo que apenas reporta não recebe privilégios de mensagem, handoff, aprovação, arquivo, shell, capacidade ou runtime. Nunca aceitar token de observação em `/mcp`, endpoints de execução, emissão de tickets ou administração.

A renovação valida identidade, fonte, workspace, revisão e revogação atuais. Revogar fonte/identidade impede publicações futuras imediatamente no caminho de admissão; o estado visível fica indisponível/expirado, não “idle”. Não transformar registro de fonte em registro de executor NXL.

## 10.5 Contrato de ingestão

Nomes propostos: `POST /v1/observations/sources`, operação de emissão/renovação de capacidade, `POST /v1/observations/activity` e consultas autenticadas. Adaptar ao roteamento vigente com testes de separação de audiências. Registro de fonte não compartilha a mesma credencial mínima de publish.

Exemplo de reporte proposto, sem credenciais no corpo:

```json
{
  "schema_version": 1,
  "source_id": "src_exemplo",
  "observed_instance_id": "obs_exemplo",
  "generation": 3,
  "sequence": 42,
  "state": "blocked",
  "evidence": "inferred",
  "observed_at": "2026-10-22T12:00:00Z",
  "valid_for_seconds": 90,
  "reason_code": "external_input_required"
}
```

O Server resolve agente/workspace a partir da fonte autorizada e da instância. Não confiar em campos de identidade arbitrários do payload. Schema estrito: tipos exatos, tamanhos limitados, enum fechada e ausência de campos secretos/prompt/frame/log.

**OBS-03 — ordenação e replay.** Aceitar sequência monotônica por fonte/instância/generation. Mesma sequência e mesmo hash é idempotente, não emite outro evento nem renova validade. Mesmo número com conteúdo diferente conflita. Sequência antiga não sobrescreve o estado atual. Geração antiga não altera a nova.

Registrar atualização e evento derivado na mesma transação. Leitura não renova observações. Reinício do publicador preserva identidade/generation de modo comprovado ou solicita nova geração autorizada; não reseta sequência silenciosamente para aceitar dados antigos.

**OBS-04 — freshness.** Usar horário de recebimento do Server e idade/horário observado com tolerância de relógio documentada. Reporte excessivamente antigo não vira estado atual apenas porque chegou agora. Relógio futuro não cria validade ilimitada. Após reconnect, buscar snapshot novo da fonte e publicar estado atual; não reproduzir backlog como se fosse observação recente.

Expiração é projeção temporal, não transição de negócio. Não dar heartbeat à sessão MCP, libertar slot ou reabrir handoff quando TTL vencer.

## 10.6 Limites operacionais iniciais

Os valores abaixo são propostas configuráveis a validar, não métricas medidas:

| Limite | Valor inicial sugerido |
|---|---|
| Validade padrão de observação | 90 segundos |
| Atualização de continuidade da fonte | 30 segundos, sem iniciar turno de modelo |
| Payload máximo | 4 KiB |
| Texto explicativo opcional | 512 caracteres, tratado como dado não confiável |
| Lote máximo | 100 observações |
| Taxa por fonte | 60 reportes/minuto, burst 20 |
| Fontes por agente | 32 |
| Instâncias externas na instalação | 4.096 |

Usar limites por instalação/ator/fonte e backpressure explícito. Coalescer estados transitórios sem descartar eventos relevantes de bloqueio/término. Não persistir streams de tokens. Retenção deve reaproveitar políticas e manutenção existentes, com índices adequados e limpeza limitada. Falta de disco não confirma uma observação que não foi persistida.

## 10.7 Observador Herdr de referência

**OBS-05 — empacotamento opcional.** Implementar um módulo opcional invocado, por exemplo, por `okto-nexus observe herdr`. Ele roda perto da instância Herdr e publica via HTTP autenticado no Nexus. Não exige o daemon Connector, não registra executor e não inicia junto com o Server por padrão.

Um manifest de plugin Herdr pode iniciar esse mesmo comando. Isso não deve criar uma quarta plataforma/daemon obrigatório nem outro protocolo de coordenação. A implantação padrão do Nexus não depende de Herdr instalado.

**OBS-06 — contrato real instalado.** Usar a CLI/socket API documentada. Registrar versão e obter o schema da instalação quando suportado (`herdr api schema --json`). A documentação pública não basta para presumir campos da versão instalada. Criar fixtures a partir do contrato compatível, sem dados pessoais. [H01]

Preferir snapshot inicial mais assinatura de eventos. Confirmar se há cursor/replay na versão testada; se não houver, não inventar. Registrar subscription, obter snapshot e reconciliar possíveis corridas usando seq/identidade disponíveis. Reconnect implica novo snapshot. Polling limitado pode ser fallback explicitamente degradado, nunca scraping de tela pelo Nexus.

**OBS-07 — identidade do ocupante.** Mapear instalação/sessão Herdr + pane + identidade/generation do ocupante para instância observada. Nome é só alias. Fechar, mover, renomear pane ou substituir processo não pode transferir silenciosamente o vínculo ao novo agente.

Quando o protocolo não fornecer evidência suficiente para preservar identidade após uma mudança, invalidar o vínculo e solicitar nova associação; não usar um PID ou nome isolado como prova. Instâncias Herdr independentes podem reutilizar IDs de pane, portanto o namespace é obrigatório.

**OBS-08 — leitura sem controle.** A integração consulta/lista/assina; não chama `agent.start`, `agent.prompt`, `send-keys`, focus, aprovação ou kill. Seu token Nexus também não pode executar essas ações. Um plugin Herdr roda com permissões do usuário: documentar essa fronteira; token restrito no Nexus não é sandbox de código local. [H03]

Não coletar conteúdo dos terminais. Mesmo para explicar bloqueio, preferir código de motivo e referência de origem. Deep links/comandos de navegação são dados seguros e explicitamente acionados pelo usuário; não executar string fornecida pela fonte.

**OBS-09 — semântica de término.** Usar `completion_seq` ou referência equivalente somente quando disponível e coerente com o schema. Sem prova de nova conclusão, mostrar idle, não produzir uma entrega “concluída”. `agent.wait` do Herdr observa atividade, não a conclusão de um handoff específico; não usá-lo como verificador de tarefas Nexus. [H02]

## 10.8 SDK/protocolo para outras integrações

**OBS-10 — exemplo mínimo.** Documentar registro autorizado, obtenção de capacidade, publicação, sequência, TTL, revogação e encerramento. Oferecer helper pequeno, isolado e testado. Não exigir plugin framework ou implementação de `LocalRuntimeCore`.

Um harness com MCP continua usando MCP diretamente para mensagens/handoffs. Um harness com somente hooks pode apenas reportar atividade, a menos que implemente separadamente um cliente de coordenação autorizado. Um ambiente com ferramenta de shell pode usar a CLI de coordenação por instrução explícita, sem o observador interpretar automaticamente texto como ação.

## 10.9 Integração da atividade à central

**OBS-11 — projeção.** Acrescentar `external_blocked`, `external_completion_unseen` e `external_observation_stale` à central, com origem, atualidade e limitação explícitas. Fonte externa bloqueada sem pedido canônico não recebe botão “aprovar”; a ação é inspecionar no ambiente de origem.

Eventos externos não disparam inferência, wake de runtime, mensagens automáticas em cascata nem claims. Renderizar o badge por instância/contexto e agregação honesta por agente, por exemplo “2 trabalhando; 1 aguardando entrada”. Não substituir presença ou disponibilidade por esse resumo.

**OBS-12 — fontes concorrentes.** Para uma mesma instância explicitamente correlacionada, manter precedência/proveniência definida: fatos canônicos do Core não são sobrescritos por inferência de terminal. Divergência pode aparecer como diagnóstico, sem alterar autorização. Fontes sem correlação suficiente permanecem separadas.

## 10.10 Aceite da frente OBS

Um harness externo pode ser observado sem adaptador nativo e sem obrigação de instalar Connector. Um participante MCP continua cooperando normalmente. Dois reportes repetidos produzem uma única mudança. Reporte expirado perde atualidade. Substituição do ocupante não herda identidade. `done` no Herdr não modifica handoff, inbox, grants, leases ou slots. Desabilitar observação deixa todos os fluxos canônicos funcionando.

# 11. Backlog de PRs e dependências

Esta tabela mantém a sequência de R2 e amplia a PR-03 para o ciclo completo do padrão. Os IDs de tarefa são mantidos; os subescopos de operações necessários a M1 são antecipados e registrados sem duplicar implementação.

| PR | Escopo | Dependências | Critério de saída |
|---|---|---|---|
| PR-00 | BASE-01…06, ADR e baseline de código/testes/primeiro uso | Nenhuma | Mapa real de lifecycle/setup, contexto do harness e interação/decisões pelo terminal; matriz de plataformas e ledger inicial. |
| PR-01 | SVC-01…04: contrato, instância única, start/reuse e prontidão | PR-00 | Background local com concorrência, ownership e erros verificados; sem segundo coordenador. |
| PR-02 | SVC-05…12: serviço do usuário, contexto, recuperação, operações e Connector | PR-01 | Server e Connector exercitados na plataforma inicial; parada/restart sem duplicação e instalação pelo pacote. |
| PR-03 | DX-15…21; DX-06…08 e DX-12…14 no caminho gerenciado; fachada compatível com DX-05; subescopos de DX-09…11 necessários ao ciclo padrão | PR-02; contratos canônicos de submissão/decisão/recuperação usados nesta PR | Marco M1: preset e trabalho real completo com um harness em topologia local e via Connector, incluindo decisões e resultados pelo terminal; zero visitas obrigatórias ao dashboard. |
| PR-04 | DX-01…05: configuração de participantes, dois formatos e gravação segura; completar os cenários MCP de DX-06…08 e DX-12…14 | PR-00; PR-03 para UX/perfis | Participação MCP com configuração preservada e provas por nível. |
| PR-05 | Completar DX-09…11: operações genéricas, deduplicação e espera dos caminhos restantes | PR-00; PR-03 para perfil e subescopos já entregues; PR-04 para campanha MCP | Perda de resposta/restart não duplicam coordenação; colaboração ampliada entre os clientes qualificados. |
| PR-06 | ATN-01…05: regras, read-model, API e atualização | PR-00 | Contratos e testes de autorização/episódios completos. |
| PR-07 | ATN-06…08: central, badge, visto/adiado e ações existentes | PR-06 | Fluxo real de operador exercitado em browser. |
| PR-08 | OBS-01…04 e limites: fontes, tokens e ingestão | PR-00 | Isolamento, replay, TTL e revogação testados. |
| PR-09 | OBS-05…10: observador Herdr e exemplo/documentação | PR-08 | Integração real somente de leitura, em versão explícita. |
| PR-10 | OBS-11…12, qualificação ampliada SVC-12, regressão conjunta e rollout | PR-03…09 | Campanha conjunta, matriz declarada e pacotes finais verificados. |

**M1 — Padrão completo pelo terminal:** PR-01…03 entregam daemon, preset e ciclo cotidiano com um harness real: conectar, solicitar trabalho autorizado, acompanhar, responder a pergunta/permissão representativa, receber o resultado e reencontrar o trabalho ao voltar. O usuário pode continuar com esse padrão sem abrir o dashboard. A instalação de serviço do usuário pertence a esse marco na plataforma inicial. A mera conexão pronta não encerra o marco, e operações/decisões essenciais a ele não podem depender de PR posterior.

**M2 — Ampliação de clientes e coordenação:** PR-04…05 completam os dois formatos MCP e a superfície genérica de comandos, deduplicação e observação correlacionada, reaproveitando as partes de M1. **M3 — Atenção:** PR-06…07. **M4 — Integração externa:** PR-08…10.

ATN, contratos DX e OBS podem avançar em paralelo quando independentes, sem bloquear M1. Dentro de PR-03, configuração gerenciada continua usando o renderer existente: não depender de relaxar contratos para completar DX-01…04. Quando a operação nativa já tiver recibo/correlação adequados, demonstrar o reaproveitamento; se M1 expuser criação de mensagem ou handoff, trazer também sua deduplicação canônica antes de oferecer retry. Testes de trabalho/colaboração com inferência exigem autorização específica; a conexão em si não deve dispará-los.

No ledger, distinguir subescopos gerenciado e participante MCP das tarefas compartilhadas entre PR-03/04 e subescopos nativos/coordenação de DX-09…11 compartilhados entre PR-03/05. Não marcar a tarefa inteira verificada quando somente um dos caminhos foi exercitado. Não reimplementar em PR-05 uma fachada ou recibo já concluído em M1. Reutilizar o catálogo de testes para indicar o contrato efetivamente comprovado em cada etapa.

Cada PR pode ser dividida em mudanças menores preservando IDs, dependências e marcos. Não reunir várias frentes numa única PR difícil de revisar. Plataforma sem campanha fica identificada como não qualificada; não converter a falta de evidência em sucesso.

# 12. Matriz mínima de testes

Os testes abaixo são obrigatórios como cenários. Reutilizar testes equivalentes e registrar correspondência; não duplicar nomes somente para aumentar contagem.

## 12.1 Lifecycle do Server e do Connector

| ID | Cenário e resultado esperado |
|---|---|
| SVC-T01 | Primeiro connect local inicia o Server em background e aguarda prontidão real. |
| SVC-T02 | Segundo connect reutiliza a mesma instância; projetos distintos não duplicam serviço por acidente. |
| SVC-T03 | Dois connects simultâneos iniciam uma única instância e observam o mesmo resultado. |
| SVC-T04 | Perfis que apontam ao mesmo diretório canônico compartilham exclusão mútua; instâncias diferentes ficam isoladas. |
| SVC-T05 | Lock obsoleto/PID reutilizado não permite matar processo alheio nem comprova serviço ativo. |
| SVC-T06 | Porta ocupada por outro processo produz diagnóstico; não muda endpoint ou base silenciosamente. |
| SVC-T07 | Serviço instalado e parado é iniciado por seu supervisor, sem daemon avulso concorrente. |
| SVC-T08 | Perfil remoto indisponível não inicia Server local substituto. |
| SVC-T09 | Fechar terminal e dashboard mantém Server/Connector e execução conforme o contrato de ownership. |
| SVC-T10 | Consulta status/logs/doctor em instância parada não a inicia e não executa inferência. |
| SVC-T11 | Endpoint acessível de instância/versão errada não vira prontidão válida. |
| SVC-T12 | Falha de migração/configuração/armazenamento impede prontidão ou admissão afetada e informa causa. |
| SVC-T13 | Timeout/Ctrl+C do connect interrompe espera sem matar serviço, repetir setup ou cancelar tarefas. |
| SVC-T14 | Serviço iniciado com cwd/PATH diferentes encontra executável, configuração e projeto corretos. |
| SVC-T15 | Credencial só disponível no terminal ou cofre bloqueado gera diagnóstico no contexto real do serviço. |
| SVC-T16 | Definições de serviço, argv, logs e saída JSON não expõem segredos nem ampliam bind/permissões. |
| SVC-T17 | Instalar/habilitar serviço repetidamente não duplica recursos; alteração externa de definição é preservada. |
| SVC-T18 | Início no login é comprovado em SO real; resultado não é apresentado como prova de boot sem login. |
| SVC-T19 | Crash supervisionado reinicia com backoff/limite; falha persistente fica visível e acionável. |
| SVC-T20 | Stop explícito não aciona autorressurreição; próximo connect segue a política documentada. |
| SVC-T21 | Stop pelo CLI conclui drain antes de acionar supervisor; timeout de espera não força término. Logout/shutdown externo registra interrupção/incerteza honestamente. |
| SVC-T22 | Restart com operação incerta ou filho ainda vivo não repete trabalho nem libera claim/slot indevidamente. |
| SVC-T23 | Restart preserva identidade, bindings e limites; grant expirado/revogado continua inválido. |
| SVC-T24 | Queda/retorno do Server mantém vínculo do Connector sem novo executor ou execução duplicada. |
| SVC-T25 | CLI novo/daemon antigo informa compatibilidade e não atualiza/interrompe trabalho implicitamente. |
| SVC-T26 | Upgrade interrompido permite recuperação documentada sem downgrade destrutivo da base. |
| SVC-T27 | Desinstalação remove só a integração selecionada, preservando dados e execução foreground posterior. |
| SVC-T28 | Container/supervisor externo usa foreground sem dupla supervisão ou dupla daemonização. |
| SVC-T29 | Suspensão/retorno, logout e reboot são campanhas distintas; não há retomada produtiva por inferência de disponibilidade. |
| SVC-T30 | Wheel/artefato instalado contém os recursos necessários e funciona sem checkout ou terminal de instalação. |

## 12.2 Onboarding e CLI

| ID | Cenário e resultado esperado |
|---|---|
| DX-T01 | Init usa agente existente e não cria/rotaciona identidade implicitamente. |
| DX-T02 | Participante sem permissão não cria agentes, grants ou bindings. |
| DX-T03 | Adicionar cliente MCP não desativa runtime já existente da identidade. |
| DX-T04 | Plan não muda configuração; apply só altera entrada revisada. |
| DX-T05 | Arquivo editado após plan causa conflito, sem sobrescrever mudança concorrente. |
| DX-T06 | Arquivo com outros MCPs e preferências conserva conteúdo alheio. |
| DX-T07 | Round-trip JSON/TOML, espaços, Unicode, formatos inválidos e duplicatas. |
| DX-T08 | Interrupção durante escrita/backup deixa original ou substituto íntegro e recuperação explícita. |
| DX-T09 | Segredos ausentes de argv, URL, logs, JSON de resultado, arquivos portáveis e browser. |
| DX-T10 | Variável referenciada mas indisponível ao harness produz diagnóstico, não sucesso. |
| DX-T11 | Origem trocada/redirect não recebe a credencial da origem aprovada. |
| DX-T12 | Doctor padrão não inicia turnos/probes nativos nem muda configurações. |
| DX-T13 | MCP conectado sem chamada de ferramenta não é participação comprovada. |
| DX-T14 | Teste de conexão nativa não é apresentado como prova de comunicação entre agentes. |
| DX-T15 | Duas requisições simultâneas com mesmo ID/hash criam um único recurso/recibo. |
| DX-T16 | Mesmo ID com payload/target/contexto diferente conflita. |
| DX-T17 | Falha entre evento, inbox/outbox e recibo reverte toda transação nova. |
| DX-T18 | Resposta perdida após commit e restart recuperam objeto original sem reenvio produtivo. |
| DX-T19 | Pending approval repetido mantém uma aprovação; decisão posterior preserva correlação. |
| DX-T20 | Credencial revogada não recupera conteúdo protegido por dedupe. |
| DX-T21 | Conclusão anterior à assinatura de wait é detectada. |
| DX-T22 | Timeout/Ctrl+C de wait não cancelam, reexecutam ou concluem o trabalho. |
| DX-T23 | Entrega/read receipt/idle externo não satisfazem espera de conclusão de handoff. |
| DX-T24 | Server antigo sem idempotência/capacidade nova apresenta degradação explícita. |
| DX-T25 | Requisição fora da janela de dedupe não é repetida automaticamente. |
| DX-T26 | Setup gerenciado continua transacional; alteração concorrente não amplia grants. |
| DX-T27 | Configuração remota usa diretório/credencial do host correto. |
| DX-T28 | Saída JSON e códigos de saída possuem testes de contrato. |
| DX-T29 | Projeto e único harness detectado levam a recomendação concreta sem escolha técnica MCP/runtime inicial. |
| DX-T30 | Vários harnesses válidos pedem somente escolha necessária; PATH não comprova login ou qualificação. |
| DX-T31 | Caminho normal gerenciado termina no terminal, com browser opcional e setup transacional reutilizado. |
| DX-T32 | Aprovação remota pendente preserva ID e identidade do decisor; terminal participante não a aprova por assentimento local. |
| DX-T33 | connect reutilizado após resposta perdida retoma o mesmo setup sem novo agente, binding ou grant. |
| DX-T34 | Login de provedor ausente produz instrução concreta e não deixa daemon bloqueado em prompt invisível. |
| DX-T35 | Serviço pronto, MCP negociado, sessão pronta e handoff concluído aparecem como níveis distintos. |
| DX-T36 | Conexão não envia tarefa/smoke pago automaticamente; a tarefa solicitada usa os serviços canônicos. |
| DX-T37 | Início no login pode ser escolhido na revisão inicial; recusar essa opção mantém o uso sob demanda funcional. |
| DX-T38 | Instalação nova com harness/provedor prontos propõe identidade, workspace e perfil úteis no mesmo resumo; aceitar os efeitos cria apenas os objetos autorizados e não exige definir persona ou visitar o painel. |
| DX-T39 | Pacote instalado, rota local padrão: solicitar trabalho real autorizado, acompanhar, responder a pergunta/permissão, obter resultado correlacionado e continuar pelo terminal, sem dashboard nem edição manual de configuração. |
| DX-T40 | A mesma campanha via Connector resolve decisões pelo CLI autenticado do operador, sem credencial administrativa no host remoto e sem aprovação pelo participante. |
| DX-T41 | Reconnect e repetição do setup preservam `agent_id`, modelo, papel, configuração, grants e personalizações; não recriam agente nem reaplicam defaults. |
| DX-T42 | Nome de agente/projeto igual não associa outra identidade; vínculos ausentes ou ambíguos exigem resolução autorizada, inclusive quando duas conexões iniciais concorrem. |
| DX-T43 | O harness iniciado pelo serviço usa instruções, modelo, ferramentas e limites efetivos revisados; configuração disponível apenas no shell não é presumida nem substituída silenciosamente. |
| DX-T44 | Direitos padrão permitem coordenação útil no workspace autorizado; não permitem ler inbox alheia, cruzar escopo não concedido, administrar globalmente ou mudar políticas. |
| DX-T45 | Decisão pelo terminal preserva ator, revisão, validade e escopo; texto enviado ao modelo, decisão expirada, recusada ou emitida por ator sem autoridade não aprova trabalho. |
| DX-T46 | Perda da resposta de submissão ou decisão em M1 recupera a mesma requisição/resultado, inclusive após restart; não cria operação, pedido ou handoff duplicado. |
| DX-T47 | Fechar e reabrir o CLI reencontra trabalho e identidade; retoma a conversa somente com suporte comprovado, ou oferece nova sessão explicitamente, sem replay nem contexto fictício. |
| DX-T48 | Perfil de execução do resumo admite somente trabalho elegível e autorizado pelas regras atuais; daemon online, mensagem recebida ou grant revogado não bastam para iniciar sessão. |
| DX-T49 | Abrir o dashboard depois do uso pelo terminal mostra o mesmo agente e configuração; personalizar nome/papel mantém identidade, histórico e vínculos canônicos. |
| DX-T50 | Adaptador que só inicia o processo, mas exige painel para uma decisão cotidiana, não passa o aceite M1; lacuna fica registrada até existir rota completa qualificada. |
| DX-T51 | Nova revisão do preset apresenta efeitos por diff e respeita mudanças concorrentes; upgrade/reconnect não amplia permissões ou sobrescreve escolhas existentes. |

## 12.3 Central de atenção

| ID | Cenário e resultado esperado |
|---|---|
| AT-01 | Aprovação pendente aparece para operador autorizado. |
| AT-02 | Aprovação expirada perde ação e preserva referência histórica adequada. |
| AT-03 | Pergunta destinada ao agente A não vira pergunta respondível pelo operador como A. |
| AT-04 | CLAIMED normal e inferência sem eventos não geram incidente de travamento. |
| AT-05 | VERIFYING automático permanece acompanhamento, sem inventar verificador humano. |
| AT-06 | Resultado desconhecido não oferece retry automático. |
| AT-07 | Marcar visto/adiar não altera aprovação, inbox, handoff ou operação. |
| AT-08 | Mesmo episódio resiste a refresh/reconnect; episódio posterior do mesmo objeto volta a aparecer. |
| AT-09 | Ação com revisão antiga conflita e recarrega o fato; não decide pedido novo. |
| AT-10 | Lista, total e filtros respeitam a mesma autorização e paginação. |
| AT-11 | Falha de leitura mostra dado stale; 403/revogação remove conteúdo protegido. |
| AT-12 | SSE perdido/gap resulta em resnapshot, sem sumir com pendências ou duplicar toasts. |
| AT-13 | Limiares temporais mudam a visão sem exigir novo evento de domínio. |
| AT-14 | Sucesso produtivo com limpeza pendente não vira tarefa fracassada. |
| AT-15 | UI teclado/foco/leitores de tela/light-dark e textos longos sem execução de HTML. |
| AT-16 | Consulta em lote não cresce em N+1 por ocorrência/agente. |

## 12.4 Observação e Herdr

| ID | Cenário e resultado esperado |
|---|---|
| OB-01 | Fonte vinculada somente a agente/workspace autorizado. |
| OB-02 | Token de observação rejeitado em mensagens, handoffs, MCP, runtime e emissão de tickets. |
| OB-03 | EPT de leitura não ganha permissão de publicar telemetria. |
| OB-04 | Agente B não publica estado para A por campo no payload. |
| OB-05 | Mesmo seq/hash não duplica evento nem renova validade. |
| OB-06 | Mesmo seq com conteúdo diferente conflita; seq antiga não sobrescreve. |
| OB-07 | Geração anterior não atualiza instância nova; reset local não remove fencing. |
| OB-08 | Relógios atrasado/futuro e backlog após reconnect não tornam dado antigo atual. |
| OB-09 | TTL expirado vira observação stale, não idle, offline canônico ou capacidade livre. |
| OB-10 | Revogação de fonte/credencial/identidade impede novos reportes/renovação. |
| OB-11 | Duas sessões da mesma identidade preservam estados independentes. |
| OB-12 | Instâncias Herdr diferentes com mesmo pane-id não colidem. |
| OB-13 | Pane renomeado/movido/substituído respeita evidência de ocupante ou exige reassociação. |
| OB-14 | Done/idle de startup/switch sem completion_ref não gera conclusão fictícia. |
| OB-15 | Término observado não conclui handoff nem libera claim/capacidade/inbox. |
| OB-16 | Reporte blocked não gera aprovação canônica nem permite responder via token observador. |
| OB-17 | Fonte Herdr desconecta e volta: snapshot reconcilia sem replay produtivo. |
| OB-18 | Schema/versionamento incompatível gera indisponibilidade explícita, sem campos adivinhados. |
| OB-19 | Estado inferido não sobrescreve evento canônico correlacionado do Core. |
| OB-20 | Limites de taxa/tamanho/cardinalidade e falta de disco retornam recusa honesta. |
| OB-21 | Fonte maliciosa não injeta HTML, URL executável, prompt, comando ou logs secretos na UI. |
| OB-22 | Observador Herdr não chama prompt/start/send-keys/focus/kill. |
| OB-23 | Nexus sem Herdr instalado inicia, testa e opera normalmente. |
| OB-24 | Desativar OBS mantém MCP-only, Core e Connector funcionais. |

## 12.5 Regressão conjunta e qualificação

| ID | Cenário e resultado esperado |
|---|---|
| RG-01 | Dois participantes MCP e um runtime gerenciado cooperam no mesmo workspace sem identidades duplicadas. |
| RG-02 | Broadcast handoff disputado por MCP/runtime continua com um único vencedor. |
| RG-03 | Observação idle não muda prioridade, fairness, elegibilidade ou reservas de claims. |
| RG-04 | Isolamento shared/per_sender/per_sender_session/one_shot mantém semântica existente. |
| RG-05 | Reinício/queda de rede com operação incerta não dispara replay por nenhum dos novos caminhos. |
| RG-06 | Core importado sem sockets/processos/credenciais; dependências entre aplicações continuam proibidas. |
| RG-07 | Cliente antigo + Server novo e cliente novo + Server antigo têm comportamento documentado. |
| RG-08 | Pacotes finais contêm UI, schemas, migrações e recursos necessários, sem depender de checkout irmão. |
| RG-09 | Campanha usa homes/workspaces temporários e não modifica contas/configurações pessoais. |
| RG-10 | Validação de browser usa o backend real; snapshot/string test não substitui interação. |
| RG-11 | Mesmo agente com MCP externo e runtime gerenciado mantém uma entrega lógica exclusiva, sem fan-out involuntário por canal. |

# 13. Estratégia de testes e evidências

**Unitários:** contratos de lifecycle, resolução de perfil/instância, estados de readiness, classificadores puros, precedência de fontes, schemas, TTL, sequências, hashes, renderização e códigos de diagnóstico.

**Integração:** SQLite/WAL real em diretório temporário, limites transacionais, concorrência, autenticação e endpoints reais; falhas injetadas antes/depois de commit e de emissão de evento.

**UI:** exercitar a central e o onboarding em browser com backend descartável. Reutilizar a infraestrutura existente. O `frontend/package.json` consultado possui build, dev e preview, mas não um script `npm test`; primeiro identificar como `frontend/tests` roda. Se necessário, adicionar runner funcional de desenvolvimento e CI, não apenas instruir um comando inexistente. [B16]

**Clientes reais:** duas configurações MCP em instalações/versionamentos explicitamente identificados; smoke opt-in com autorização. Fixtures qualificam o contrato simulado, não o binário real.

**Herdr real:** registrar versão/schema/plataforma, executar leitura de estado, mudança de estado, desconexão e substituição de instância em ambiente descartável. Teste do adaptador deve demonstrar que não enviou comandos produtivos. Não afirmar suporte cross-platform sem executar as campanhas correspondentes.

**Connector/Core:** executar suites afetadas e regressão de instalação de wheels. Um ambiente sem provedor/OS necessário deve produzir `BLOCKED`/`NOT_RUN` com comando e motivo, não “passou”. Continuar trabalho independente que não dependa do bloqueio.

**Carga:** medir latência de listagem/resumo, número de consultas, vazão de reportes, crescimento de armazenamento e custo de SSE com dados sintéticos representativos. Meta de aceitação inicial: sem I/O de harness por linha, paginação/limites funcionando, nenhuma transação aberta durante waits e nenhuma degradação não explicada dos fluxos canônicos. Definir SLO numérico após medir baseline, não inventar percentuais de ganho.

**Serviço e sistema operacional:** executar campanha real de foreground/background, fechamento do terminal, login, crash, parada solicitada, restart com trabalho ativo e desinstalação. Usar perfis/diretórios descartáveis. Não confundir validar unit/plist/XML com testar o gerenciador de serviços. Registrar explicitamente política de logout, escopo do usuário, disponibilidade do cofre e mecanismo de supervisão.

**Padrão completo por terminal:** testar o pacote instalado, um harness nativo real e as topologias Server local/Connector remoto. Partir de configuração nova com pré-requisitos de provedor atendidos e aceitar os defaults revisados. Demonstrar solicitação, acompanhamento, pergunta/permissão representativa, resultado correlacionado e reencontro do trabalho ao reabrir o CLI, sem visitar dashboard ou editar configuração manualmente. Incluir recusa/expiração de decisão e perda da resposta de submissão nos testes do contrato correspondente. Registrar decisões exigidas, tempo até prontidão e até resultado, configuração efetiva do harness e limitações de continuidade. A primeira campanha não exige central de atenção nem Herdr.

Trabalho real da campanha é explicitamente autorizado; testes de inferência não são disparados pelo setup. Usar doubles/falhas injetadas para lifecycle, autorização e recuperação quando suficientes, sem chamá-los de qualificação real do harness. Se faltar ambiente/provedor autorizado, comprovar o que for possível e manter o aceite real de M1 pendente; não converter “sessão pronta” em “ciclo completo verificado”.

# 14. Migração, compatibilidade e rollout

## 14.1 Migrações

Usar a infraestrutura vigente e obter o próximo número real no momento de cada PR. Não fixar aqui um número de migration. Migrações aditivas para estado de atenção, fontes/instâncias e recibos de coordenação quando necessários. Não reescrever histórico imutável nem reaproveitar tabelas de capacidade/contexto com significado diferente.

Criar índices compatíveis com filtros/paginação e unicidade de episódio/seq/request. Testar upgrade de base anterior, base vazia, restart e manutenção. Backfills não devem inventar perguntas, conclusões ou observações que nunca existiram.

## 14.2 Rollout de lifecycle

Manter o entrypoint foreground atual. O novo connect inicia/reutiliza background sob demanda no destino local selecionado; leitura/status/doctor não passam a iniciar processos. Instalações existentes continuam podendo usar seu supervisor/containers. Detectar essas formas antes de oferecer serviço do usuário, evitando duplicação.

Início no login é opt-in explícito, reversível e independente de OBS/ATN. Instalador indica usuário efetivo, componente, instância, supervisor e comandos de controle; não exige que o usuário compreenda locks ou protocolos. Recusar a instalação de serviço não bloqueia o primeiro uso em background sob demanda.

Na migração de processo manual para serviço supervisionado, preservar dados e endpoint, detectar trabalho ativo e coordenar drain/transferência conforme o contrato real. Não instalar uma segunda instância sobre o mesmo banco enquanto a primeira continua ativa. Falha de instalação deixa estado recuperável e não deve apagar configuração anterior.

## 14.3 Feature rollout

Aplicar o preset como recomendação para novas configurações. Instalações existentes mantêm identidade, personalizações e autoridade; adoção ou atualização de preset usa diff e setup autorizado conforme DX-21. A disponibilidade da central ou de OBS não condiciona os controles de terminal do padrão.

Introduzir controles independentes para a central e para ingestão externa, preferencialmente no catálogo de settings existente. OBS inicia opt-in. A configuração do controle de observação não altera `runtime_enabled`, autorização ou política MCP.

Quando a central estiver desligada, continuam válidos Approvals, Handoffs e os demais caminhos originais. Quando OBS estiver desligado, novas publicações são recusadas; histórico segue consultável segundo autorização/retention e não vira atividade atual.

Não obrigar um upgrade de Core/Connector se a etapa não altera seus contratos. Se o contrato declarativo compartilhado mudar, publicar/usar artefatos candidatos coordenados e atualizar pins/locks; não marcar publicação como feita antes de existir.

## 14.4 Rollback operacional

Desabilitar novos ingressos/UI, manter schema e histórico, e usar procedimentos existentes de backup/drain/reconciliação. Não apagar recibos para “destravar” repetição, não remover índices de unicidade e não fazer downgrade destrutivo de banco em produção.

Reverter configuração local somente quando o arquivo ainda corresponde à revisão/propriedade da operação original. Mudança posterior do usuário exige merge/revisão, não restauração cega de backup.

Para rollback do lifecycle, desabilitar a inicialização automática da instância selecionada, aplicar parada controlada e voltar ao entrypoint foreground compatível, preservando a base. Se o schema não permite downgrade, manter binário compatível e desabilitar somente o comportamento novo. Não matar processos por nome nem remover serviços de outras instâncias. Desinstalar serviço não significa desinstalar o produto ou apagar seu histórico.

# 15. Métricas de resultado

As métricas são instrumentação local e opt-in onde aplicável; nunca incluir chaves, prompts, caminhos privados ou conteúdo de mensagens.

**ATN:** tempo entre ocorrência acionável e decisão; proporção de itens marcados como irrelevantes; reincidência de toasts; quantidade de navegações até a ação; bloqueios resolvidos no fluxo canônico.

**SVC:** tempo até prontidão em início frio e reutilização; falhas por etapa; instâncias duplicadas evitadas; recuperação após crash; sucesso de início no login; diferenças entre execução interativa e serviço. Medir CPU/memória ociosa e rotatividade de logs a partir de baseline, sem inventar metas de consumo.

**DX:** tempo da instalação até primeira sessão útil e primeiro resultado de trabalho; quantidade de decisões e trocas terminal/browser; taxa de conclusão sem ajuda; ponto de abandono; tempo até participação comprovada; taxa de conclusão de setup; erro por etapa; necessidade de edição manual; tempo até primeiro handoff concluído; resultados incertos corretamente recuperados sem duplicação. Registrar uso cotidiano continuado com defaults e decisões resolvidas pelo terminal. Zero visitas obrigatórias ao dashboard no percurso padrão é critério funcional de M1, não uma meta estatística de marketing; falhas reais de credencial ou política são registradas separadamente.

**OBS:** integrações externas distintas; proporção de observações atuais; divergências e mudanças de ocupante detectadas; rejeições por schema/revogação; atraso de reporte; custo de armazenamento/eventos. Não medir “harness suportado” apenas porque apareceu um nome na tela.

Definir baseline antes da entrega. Não impor objetivos numéricos de marketing sem medição. Métricas de adoção não substituem testes de autorização e idempotência.

# 16. Fora de escopo

Não implementar multiplexer PTY, editor/IDE, screen scraping próprio, orquestrador cognitivo, autoaprovação, agendamento inteligente por inferência de idle, framework genérico de plugins, marketplace, gestão Git/worktrees, substituição do Core, substituição do Connector por SSH ou replay automático de resultados incertos.

O observador Herdr é integração de referência de leitura. Usá-lo como backend de execução exige outro projeto, outros contratos e outra revisão. Este plano não autoriza essa expansão.

Daemon e serviço do usuário do Server/Connector estão **dentro** do escopo. Não estão implícitos: novo supervisor distribuído, outro orquestrador, instalação privilegiada em todo o sistema, execução antes do login em todas as plataformas, funcionamento durante suspensão/desligamento ou preservação automática de processos de harness após reboot. Cada expansão exige contrato e qualificação próprios.

Preset útil, controles de decisões pelo terminal e ciclo cotidiano completo também estão **dentro** de M1. A meta de facilidade semelhante à do Herdr não inclui copiar sua TUI, seu multiplexer ou adotar arbitrariamente processos já abertos; uma fachada CLI sobre contratos nativos existentes permanece no escopo quando necessária para cumprir DX-20.

# 17. Critérios de conclusão geral

A entrega só pode ser considerada concluída quando:

1. Cada tarefa obrigatória tem implementação ou reaproveitamento explicitamente demonstrado, com testes correspondentes.
2. As frentes SVC, DX, ATN e OBS respeitam suas dependências e funcionam de modo combinado; Herdr continua opcional.
3. Dois clientes MCP testados participam sem adaptador nativo novo e sem identidade duplicada.
4. A central oferece ações reais e autorizadas, sem virar fonte paralela de lifecycle.
5. Repetição/timeout/restart preservam IDs e não duplicam mensagens, aprovações ou handoffs dentro do contrato de idempotência.
6. Atividade externa nunca se transforma em autorização, capacidade reservada ou conclusão de trabalho.
7. Core e Connector preservam suas fronteiras e o conjunto de dependências é reproduzível.
8. Documentação, schemas e ajuda da CLI descrevem o comportamento realmente entregue.
9. Testes não executados estão nomeados; nenhuma fixture é apresentada como campanha de provedor ou plataforma real.
10. Não há segredo em artefatos, logs, exemplos, URLs ou configurações exportadas.

11. O primeiro marco comprova daemon + preset + ciclo completo de trabalho pelo terminal com um harness real, no Server local e via Connector, incluindo decisão e resultado, sem dashboard obrigatório nem terminal exclusivo para manter o serviço.
12. Inicialização concorrente reutiliza a instância correta; perfil remoto não cria Server local e não há supervisores concorrentes.
13. Serviço do usuário foi instalado, iniciado no login, parado, recuperado de falha e removido nas plataformas declaradas qualificadas, com contexto/credenciais reais de execução validados.
14. Restart, suspensão e queda de conexão preservam contratos de autoridade, ownership e incerteza, sem repetição produtiva implícita.
15. Controle por status/logs/start/stop/restart e foreground funciona, sem que diagnóstico inicie daemon ou inferência.
16. O agente padrão tem identidade persistente, perfil generalista útil e coordenação no escopo aprovado; preserva limites efetivos do harness e não recebe administração global ou poder de aprovar seus próprios pedidos.
17. Reconnect, atualização e abertura posterior da interface preservam a configuração e a identidade; personalização é opcional e o uso padrão continua completo pelo terminal.

# 18. Relatório obrigatório do Codex por PR

Entregar um resumo com: objetivo; decisões; mudanças por repositório; migrações e contratos alterados; testes adicionados/reutilizados; comandos executados; resultados; evidências; cenários não executados; riscos restantes; compatibilidade; rollback e próxima dependência.

Ao finalizar, produzir `plans/agent_ops/implementation-report.md` e atualizar `ledger.json`. Não declarar a tarefa inteira concluída enquanto houver requisito obrigatório bloqueado; declarar exatamente quais fatias estão verificadas e quais dependem de campanha externa.

Para PRs de lifecycle/primeiro uso, incluir também: componente e instância; plataforma/versão; modo de supervisor; escopo login/logout/boot efetivamente verificado; contexto de credenciais; preset e configuração efetiva do harness; tarefa em andamento durante falhas; evidência de não duplicação; passos, decisões e visitas obrigatórias ao painel. Demonstrar separadamente conexão pronta e ciclo de trabalho completo, incluindo decisão pelo terminal e continuidade/recuperação comprovada. Registrar marco M1 concluído somente com esse aceite e listar frentes posteriores ainda abertas.

# 19. Prompt de arranque para o Codex

> Execute a revisão R3 deste plano incrementalmente nos três repositórios, respeitando instruções locais, branch autorizada e permissões já concedidas. Comece por BASE-01…06: reconcilie os snapshots com o código real, localize lifecycle, supervisão, configuração, interação nativa, decisões e setup existentes, e registre reaproveitamentos/lacunas. A prioridade é M1: Server e Connector iniciados ou reutilizados em background, serviço do usuário na plataforma inicial, preset útil e trabalho completo com um harness nativo existente pelo terminal. O usuário pode conservar os defaults e nunca abrir o dashboard. Inclua identidade persistente, perfil generalista de projeto, configuração efetiva do harness preservada, coordenação no escopo aprovado e uma revisão inicial significativa, sem formulários administrativos separados. Implemente SVC-01…12 e DX-15…21 pelo setup/Finish atual. Traga os subescopos de DX-09…11 necessários para solicitar trabalho, acompanhar, responder a perguntas/permissões, receber resultado e reencontrar o trabalho sem duplicação; não deixe operações essenciais de M1 dependentes da PR-05. Um prompt humano à sessão pode usar operação nativa; delegação entre agentes usa handoff canônico. Não recrie participação MCP-only, inboxes, grants, claims, histórico de conversa ou adaptadores. Depois amplie os dois formatos MCP e os comandos restantes, entregue a central e o observador Herdr somente de leitura. Siga a seção 11 e preserve as tarefas e os cenários originais. Resolva topologia antes de iniciar processos, garanta uma instância e um supervisor, mantenha foreground e ofereça início no login como opção explícita. Não confunda serviço ativo ou sessão pronta com M1 concluído; teste trabalho real somente com autorização e registre o que não pôde ser executado. Preserve MCP HTTP direto, autoridade do Server, execução pelo Core e papel remoto do Connector. Decisões pelo terminal usam o ator e a API canônicos; não distribua credencial administrativa ao harness/Connector nem remova limites nativos. Reconnect não reseta a configuração ou cria outro agente; dashboard opcional edita os mesmos objetos. Restart não renova grants nem repete efeitos incertos; reconcilie antes de admitir trabalho afetado. Login, logout, fechamento do terminal, crash e reboot são provas distintas. Não confunda observação com autorização, capacidade ou conclusão. Faça entregas pequenas com evidências reais, sem alterar instalações pessoais, usar credenciais reais, publicar pacotes ou fazer merge além do autorizado. Ao concluir cada PR, atualize ledger e relatório distinguindo implementado, verificado, não executado e bloqueado.

---

# Apêndice — referências da análise

As referências abaixo identificam a base examinada. O código proposto neste plano continua sendo proposta. URLs em monospace são referências para o executor; não são comandos de instalação.

**B01 — Server, metadados e dependência Core.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/pyproject.toml`

**B02 — Core, versão e recursos empacotados.**  
`https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/76db0a79c5cf7f5248e4994dd10f2587a2d59f9b/pyproject.toml`

**B03 — Connector, versão e dependências.**  
`https://github.com/OktoLabsAI/okto-nexus-connector/blob/20f16199f4b2926630c0bfe1b8a8646a836dbe53/pyproject.toml`

**B04 — Participação/coordenação/dashboard; contém também trechos históricos.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/README.md`

**B05 — Claim MCP e automático gerenciado.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/docs/runtime-handoff-notifications.md`

**B06 — Fluxo atual de configuração.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/docs/connection-setup.md`

**B07 — Finish transacional e baseline de revisão.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/connection_setup.py`

**B08 — Read-model de observabilidade.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/observability.py`

**B09 — Estado de conexão separado da atividade.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/agent_connection_status.py`

**B10 — Instâncias/turnos por agente.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/agent_runtime_administration.py`

**B11 — Perguntas e decisões já existentes na UI.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/frontend/src/components/NativeQuestions.tsx`

**B12 — Templates MCP gerenciados e restrições de credencial/formato.**  
`https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/76db0a79c5cf7f5248e4994dd10f2587a2d59f9b/src/nexus_connector_core/harness_config.py`

**B13 — Introdução de primeiro uso e placeholder de conexão.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/frontend/src/components/onboarding/OnboardingModal.tsx`

**B14 — Observações de contexto não são telemetria de atividade.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/runtime_observations.py`

**B15 — Criação de mensagens e fronteira transacional.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/src/okto_nexus/application/messages.py`

**B16 — Scripts reais do frontend.**  
`https://github.com/OktoLabsAI/okto-nexus/blob/e480ab41ba046204c62ebf25d04c9e61b22fbd78/frontend/package.json`

**B17 — CLI e operação remota atuais; revisar implementação correspondente.**  
`https://github.com/OktoLabsAI/okto-nexus-connector/blob/20f16199f4b2926630c0bfe1b8a8646a836dbe53/docs/cli.md`

**H01 — Herdr Socket API; consultar schema da versão instalada.**  
`https://herdr.dev/docs/socket-api/`

**H02 — Herdr Agent automation; espera de estado, done/seen e completion_seq.**  
`https://herdr.dev/docs/agent-automation/`

**H03 — Herdr Plugins; modelo de execução local e limites de sandbox.**  
`https://herdr.dev/docs/plugins/`

**H04 — Herdr Agents; fontes de estado, inferência e hooks.**  
`https://herdr.dev/docs/agents/`

## Referências adicionadas na revisão R2

Consultadas em 22/10/2026. As referências B01…B17 permanecem como evidência histórica do baseline original; as seguintes fundamentam as decisões novas, sem comprovar implementação no Nexus.

**H05 — Herdr: início/reutilização de sessão em background, fluxo local e remoto.**  
[How to work with Herdr](https://herdr.dev/docs/how-to-work/)

**H06 — Herdr: primeiro uso, workspace e onboarding inicial.**  
[Quick start](https://herdr.dev/docs/quick-start/) · [Configuration](https://herdr.dev/docs/configuration/)

**S01 — systemd: linger permite gerenciador do usuário no boot e após logout.**  
[loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html)

**S02 — systemd: políticas de sessão e KillUserProcesses.**  
[logind.conf](https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html)

**S03 — Apple: LaunchAgent/LaunchDaemon e comportamento sob launchd.** Guia oficial arquivado; confirmar comandos na versão alvo.  
[Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

**S04 — Microsoft: contexto de logon de tarefas e limites de S4U.**  
[TASK_LOGON_TYPE](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/ne-taskschd-task_logon_type)

**S05 — Microsoft: serviços automáticos iniciados durante o boot pelo SCM.**  
[Automatically Starting Services](https://learn.microsoft.com/en-us/windows/win32/services/automatically-starting-services)

**S06 — Microsoft: serviços e interação com o usuário.**  
[Interactive Services](https://learn.microsoft.com/en-us/windows/win32/services/interactive-services)

## Referência adicional da revisão R3

**H07 — Herdr: agentes em terminais reais, identificação e integração de sessão.** Consultada em 22/10/2026. Fundamenta a distinção entre a meta de facilidade de uso e uma promessa de equivalência entre panes Herdr e adaptadores gerenciados Nexus. A exigência de uso padrão completo sem dashboard é decisão de produto do usuário nesta revisão.
[Agents](https://herdr.dev/docs/agents/) · [Agent automation](https://herdr.dev/docs/agent-automation/) · [Integrations](https://herdr.dev/docs/integrations/)
