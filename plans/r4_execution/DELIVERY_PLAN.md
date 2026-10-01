# Plano de entrega completa do Nexus, Connector e Core

Este plano organiza a conclusão dos três produtos na branch `feature/v0.2.0`, com implementação, integração, testes, migração e aceite final. O resultado exigido é utilizar os harnesses diretamente no Nexus e remotamente pelo Connector, pelas entradas reais de UI, CLI e API, com o mesmo Core instalado. Todos os textos produzidos pelas aplicações devem estar em inglês dos Estados Unidos, inclusive superfícies legadas e mensagens de retorno.

Data da baseline: 29 de setembro de 2026. Revisão de planejamento: 30 de setembro de 2026. Este documento é um plano de conclusão; sua validação documental não executa testes de produto nem encerra gates de release. O trabalho anterior é aproveitado como implementação parcial a verificar.

## Visão geral da entrega

| Marco | Entrega verificável | Depende de |
|---|---|---|
| M00 | Inventário de requisitos, testes executáveis, defeitos e ambientes | — |
| M01 | Contrato Core completo e mesmo wheel nos dois consumidores | M00 |
| M02 | Composição, persistência, identidade e autorização | M01 |
| M03 | Descoberta, consentimento e bindings reutilizáveis | M02 |
| M04 | Admissão e dispatcher canônicos das sete operações | M03 |
| M05 | Harnesses diretamente no Nexus, sem aplicativo Connector | M04 |
| M06 | Harnesses via daemon Connector, WSS, reconciliação e leases | M04 |
| M07 | Eventos, receipts, histórico e replay duráveis | M06 |
| M08 | Aprovações e input com aplicação nativa única | M05, M07 |
| M09 | MCP HTTP direto, bridge Pi e trabalho governado | M08 |
| M10 | Jornadas UI/CLI completas e textos US English | M08 |
| M11 | Recuperação, revogação, shutdown e limites sob falha | M08 |
| M12 | Migração, cutover e rollback testados | M09, M10, M11 |
| M13 | Artefatos finais e aceite local, remoto e por provider/SO | M12 |

Cada marco abaixo define responsáveis, funcionalidades, testes e saída. O acompanhamento fica em [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md); os requisitos, dependências e cenários continuam rastreáveis nos arquivos de cobertura. A entrega total exige os quatro gates encerrados e evidência sobre o conjunto final dos três produtos.

## Roteiro operacional consolidado

Checkpoint de execução de 1º de outubro: o incremento corrente de NS15.01/M12
conclui a retomada do catálogo após adoção revisada de endpoint, com recibo
transacional e validação do backup preservado. Ver [escopo e limites](M12_MIGRATION_RESUME.md)
e [manifesto de testes](test_runs_20261001_migration_resume.json). A próxima
fronteira de M12 é o cutover/rollback. O aceite combinado de histórico legado
e recuperação M0–M3 passou em [TR4-15-01](M12_NS15_01_ACCEPTANCE.md).
A [correção de admissão durante cutover](M12_MIGRATION_CUTOVER_FENCE.md)
impede contornar endpoints legados usando o ID canônico do adapter.
O [incremento TR4-15-02](M12_NS15_02_DRAIN.md) integra drenagem do owner,
incerteza preservada e restore combinado no binário HTTP atual. A próxima
fronteira é NS15.03: abertura explícita, connect, comandos e leituras MCP/REST
de sessões canônicas, incluindo abertura por connection key com autoridade
durável, descoberta, configuração, seleção implícita local e boot aprovado, já usam R4/Core;
delivery conversacional já liga claim e admissão R4 atomicamente, incluindo
seleção explícita de workspace lógico sem caminho local e prioridade de sessões
prontas na seleção mista de endpoints. Claims de handoff com conclusão
governada também já admitem abertura/turno R4 atomicamente, agora com
seleção de workspace lógico nas entradas MCP/HTTP sem caminho local. Completar
o fallback entre protocolos após falha; a disputa combinada de claims foi
verificada em TR4-06-05, incluindo exclusão de MCP, observadores sem execução
e conclusão governada de handoff. A captura
de saída R4 já preserva eventos contíguos e aparece no histórico autorizado;
publicação governada, artefatos privados e resultados estruturados explicitamente
admitidos também reutilizam o domínio existente. Leituras de eventos MCP/REST já
usam o histórico canônico autorizado e paginado. Retenção da captura e auditoria
de subscribers verificadas; observadores sem execução cobertos em TR4-06-05.
Fallback legado→R4 com prova tipada e cutover dos loaders verificados. Os quatro
conectores nativos duplicados foram [retirados do pacote](M12_NS15_03_NATIVE_REMOVAL.md);
os helpers físicos também foram retirados e [TR4-15-03 passou](M12_NS15_03_HELPER_REMOVAL.md)
com REST/MCP pelo Core e verificação do pacote instalado. Tentativas canônicas
mantêm reconciliação explícita antes de novo trabalho;
NS15.04 mantém o aceite completo de configuração e recuperação após efeitos R4.
Nenhum gate de release é encerrado por estes incrementos.

Esta revisão atende à solicitação de estruturar a entrega total. O escopo de implementação continua sendo M00–M13, com os critérios detalhados abaixo e o backlog normativo preservado. A sequência de fechamento é:

**M00 → M01 → M02 → M03 → M04 → {M05, M06 → M07} → M08 → {M09, M10, M11} → M12 → M13.**

As chaves indicam dependências independentes, sem exigir execução por agentes paralelos. Preparar ambientes e testes negativos desde M00; incorporar os testes em cada incremento, com a campanha integral repetida no artefato final.

### Primeiro pacote executável após esta revisão

O Connector contém trabalho local ainda não testado em configuração de lançamento: schema 8, registro de configuração vinculado ao digest aprovado e seleção automática pelo host. Essas alterações não fazem parte do HEAD publicado e não encerram P6.1. O próximo incremento deve:

1. Revisar a migração 7 → 8 e a validação de configuração, referências de segredo, consentimento, revisão de perfil e identidade física do diretório.
2. Testar persistência, idempotência, configuração ausente/adulterada, segredo ausente, troca de diretório e mudança de autoridade durante a resolução assíncrona. Nenhuma recusa pode produzir abertura nativa.
3. Exercitar staging → publicação de realization → aprovação do binding → abertura pelo owner real, sem callback externo para substituir a configuração aprovada.
4. Compor a autorização de ferramentas: MCP HTTP para os adapters qualificados e bridge Pi, com segredo protegido, lease atual e recuperação explícita. A configuração básica de ambiente isoladamente não encerra esse item.
5. Construir e instalar o Connector em ambiente limpo com o Core fixado; executar os testes dirigidos e a integração afetada com Nexus. Registrar falhas e limitações.
6. Fazer commit/push apenas dos arquivos do incremento, atualizar evidências e continuar com P6.2. O fechamento de M02/M06 permanece condicionado a todos os demais critérios desses marcos.

As alterações preexistentes de assets e exclusões em Nexus, bem como arquivos não relacionados nos demais repositórios, permanecem fora desse pacote. O plano de entrega não autoriza classificá-las automaticamente como parte da implementação.

### Pacotes seguintes e prova de conclusão

| Ordem | Trabalho restante | Responsável principal | Prova exigida |
|---|---|---|---|
| 1 | Fechar inventário de aceites e lacunas do contrato compartilhado (M00/M01) | Core + consumidores | Cada requisito ligado a teste coletável, ambiente e owner; conformance instalada e mesmo hash Core |
| 2 | Completar autoridade, configuração, consentimento e onboarding reutilizável (M02/M03) | Nexus + Connector | Primeira configuração e reuso pelas entradas públicas; recusa de drift/revogação; segredos ausentes das projeções |
| 3 | Completar admissão/outbox e as sete ações (M04) | Nexus | IDs estáveis, reserva durável e nenhum segundo efeito após timeout/retry |
| 4 | Concluir composição embedded e daemon (M05/M06, P5/P6) | Nexus / Connector | Boot automático, ciclo local sem Connector, lanes remotas, renovação e reconcile paginado não vazio |
| 5 | Completar eventos, decisões e domínio (M07–M09) | Três repositórios | Replay após restart, aprovação/input únicos, claims exclusivos e resultados causais em MCP/Pi |
| 6 | Concluir jornadas humanas/headless e idioma (M10) | Nexus + Connector; mensagens Core | Browser/CLI reais, sucesso e erro, quatro cenários TLANG e assets do wheel em US English |
| 7 | Qualificar falhas, limites e atualização (M11/M12) | Três repositórios | Crash, rede, disco, saturação, ownership, migração interrompida, restore e rollback |
| 8 | Congelar e aceitar a entrega (M13) | Três repositórios | Regressões completas, providers reais, Windows/Linux, hosts independentes e G0–G3 encerrados |

A tabela resume a ordem; cada linha conserva as dependências, funcionalidades e testes definidos nos milestones. Nenhuma linha pode ser encerrada somente com fixtures técnicas ou pela existência de um helper.

### Controle de execução, estimativa e publicação

Para cada item restante, o inventário de aceite registra: requisito, repositório responsável, caller público, dependências, teste/nodeid, ambiente, evidência, estado e defeito impeditivo. Antes de implementar um pacote, selecionar seus critérios positivos, negativos e de recuperação; depois executar, corrigir falhas, verificar o artefato instalado e publicar o incremento testado.

A estimativa de calendário será calculada após M00 a partir dos itens ainda sem implementação, testes ausentes, infraestrutura e defeitos reproduzidos. Cada atualização deve mostrar trabalho restante e recursos necessários. Ausência de credencial, host ou provider mantém o respectivo aceite pendente e permite continuar os pacotes independentes.

A cada milestone concluído, entregar os três SHAs de referência, hashes dos pacotes, comandos e resultados dos testes, migrações aplicáveis e restrições remanescentes. Mudanças do Core exigem pacote/hash antes da atualização dos consumidores. Os commits e pushes seguem em `feature/v0.2.0` nos repositórios envolvidos.

O aceite final exige todos os casos obrigatórios aprovados no conjunto congelado. Relatórios de cobertura documental comprovam a estrutura do plano; a entrega de produto depende dos testes de execução e dos gates descritos neste documento.

## Fontes e cobertura obrigatória

A ordem normativa continua sendo [arquitetura R4](../01_ARQUITETURA_E_PLANO_MESTRE.md), [contratos](../02_CONTRATOS_HTTP_NXL_E_ESTADOS.md), [dados e migração](../03_DADOS_MIGRACAO_E_RECUPERACAO.md), [backlog](../04_BACKLOG_EXECUCAO.md), [testes e aceite](../05_TESTES_E_ACEITE.md) e [handoff Core e Connector](../06_HANDOFF_CORE_CONNECTOR.md). Este documento organiza a execução e acrescenta o requisito de idioma; não reduz requisitos nem cria uma autoridade de contrato concorrente.

A cobertura inclui as 85 tarefas NS00–NS16, os 164 cenários originais (85 TR4, 45 TN e 34 J), as quatro entregas CORE-R4, as oito entregas CON-R4, os quatro achados CN5, as 23 rotas HTTP/WSS originais e a consulta adicional de metadata (24 rotas) e os sete verbos de operação. Acrescenta quatro cenários de idioma. O mapeamento completo é verificável em [delivery_plan.json](delivery_plan.json) e [delivery_coverage.json](delivery_coverage.json).

Cada tarefa mantém seus critérios e dependências originais. O marco indica quando ela deve ser encerrada, não quando é permitido começar um protótipo. Dentro do mesmo marco, vale o grafo do backlog. Um componente necessário a um marco posterior pode receber contratos e fixtures antes, sem declarar a integração pronta.

## Entregas por repositório e integração

| Repositório | Responsabilidade de entrega | Evidência para aceitar |
|---|---|---|
| Core | Contrato público R4, discovery/seleção, adapters e capacidades, contexto/lease, execução, journal, decisões/input e contenção | Conformance instalada; testes de cada ação e erro; compatibilidade histórica; matriz de providers/SO com builds fixados |
| Nexus | Identidade/política, consentimento/binding, admissão/outbox, execução local, controle remoto, domínio/MCP, persistência e UI/API/CLI | Jornadas pelas entradas reais; ciclo local sem Connector; Server remoto sem acesso ao disco do executor; migração, browser, recuperação e regressões |
| Connector | Estado/vault/identidade, registro/inventário/realização, daemon WSS, attach/reconcile/lease, host Core e CLI | Startup a partir de estado persistido; ciclo remoto em processos e hosts separados; reboot, renovação/revogação, perda de rede e instalação |
| Conjunto | Mesmo Core, causalidade e autoridade consistentes, sete ações, histórico durável, textos US English e atualização segura | Manifesto dos três commits e hashes; G0–G3 fechados; todos os cenários obrigatórios aprovados nos artefatos finais |

A ordem de publicação de uma mudança de contrato é Core → pacote/hash →
adoção em Nexus e Connector → integração instalada. Mudanças restritas a um
consumidor mantêm o contrato fixado e reexecutam os testes de integração
afetados. O milestone só fecha quando as dependências e seus critérios de
aceite também estiverem completos.

## Resultado de produto esperado

O operador seleciona um agente existente, o executor local ou remoto, uma instalação descoberta pelo Core e um workspace aprovado. A proposta mostra o consentimento necessário. Após aplicação, o vínculo é reutilizável. Iniciar, enviar um turno, controlar, aprovar, fornecer input, observar e encerrar passam pela admissão canônica do Nexus, que cria a operação durável e a despacha uma única vez.

O Nexus executa localmente com o Core dentro do owner de `serve`, sem instalar o aplicativo Connector. Remotamente, um daemon Connector inicia o WSS para o Server, resolve referências no próprio host, instala a autoridade concedida e chama o mesmo Core. O Server remoto funciona sem binários ou acesso ao filesystem do executor.

MCP permanece HTTP direto no Nexus. Conversas tools-only funcionam sem daemon. A bridge nativa do Pi usa os casos de uso canônicos com capacidade limitada. Aprovações, trabalho, consumo exclusivo, causalidade, histórico e política existentes continuam preservados.

Codex app-server, Pi RPC e Claude stream devem ser qualificados por build e sistema operacional nas modalidades local e remota. Claude attach mantém uma trilha explícita de qualificação nos sistemas compatíveis; presença no catálogo não permite execução. Uma capacidade excluída normativamente precisa aparecer indisponível e ter teste negativo. Falta de ambiente, credencial ou implementação de uma capacidade exigida mantém a entrega incompleta; não permite remover a linha da matriz.

Continuam fora do escopo normativo: novo login de usuário Nexus, SSO, tenant obrigatório, A2A completo, sincronização de checkouts, instalação automática de providers, orquestração cloud, HA multiwriter, migração major do SDK MCP e reescrita dos protocolos nativos.

## Baseline e lacunas que orientam a sequência

### Checkpoint vigente — 30 de setembro de 2026

Os HEADs abaixo identificam o ponto de partida publicado do incremento corrente. Nos três repositórios, a branch é `feature/v0.2.0`; os SHAs foram conferidos diretamente em origin. Este checkpoint distingue commits publicados de alterações locais ainda não publicadas.

| Repositório | HEAD verificado | Pacote |
|---|---|---|
| Nexus | `77243df779f7d2021d877f7e0bc9d6e9a22001e1` | `0.2.0` |
| Connector | `f1ee452de5d2c9a2429e8f270f2308bffd24fc68` | `0.5.0.dev0` |
| Core | `770659b7f3404798fe6c59146c7ab9d12b84bbe4` | `0.2.30.dev0` |

O SHA-256 do wheel Core foi recalculado nos três repositórios e é o mesmo: `e060e033be05fdd4c9aff5c90902d191483d400b3f6778fa7bb5395b66f561e6`. A versão do pacote não equivale à revisão do wire. O contrato histórico R3 continua separado do preview R4. M00/M01 permanecem em andamento; os demais marcos contêm incrementos parciais, sem aceite integral. G0–G3 continuam abertos.

A [revisão anterior de planejamento](planning_review_20260930.json) e a [revisão de conclusão](completion_review_20260930.json) conservam seus snapshots. O incremento corrente de [capabilities de sessão](M02_SESSION_CAPABILITIES.md) e o [manifesto coordenado](test_runs_20260930_capabilities.json) registram implementação, testes e limites. O HEAD Nexus do quadro também contém a integração parcial dos handlers MCP descrita abaixo; Connector e Core são as dependências publicadas verificadas. A revisão documental anterior está preservada em [total_delivery_review_20260930.json](total_delivery_review_20260930.json). A atualização do checkpoint após os handlers MCP está em [full_delivery_checkpoint_20260930.json](full_delivery_checkpoint_20260930.json). Nenhuma flag de prontidão foi promovida.

O histórico está no [status de implementação](IMPLEMENTATION_STATUS.md) e nos relatórios de [decisões](M01_DECISION_CONFORMANCE.md), [targeting/inventário](M01_TARGETING_INVENTORY.md), [aplicação de leases](M01_LEASE_APPLICATION.md), [leases canônicas](M06_CANONICAL_LEASES.md), [contenção expirada](M01_EXPIRED_CONTAINMENT.md), [controles](M04_CANONICAL_CONTROLS.md), [close](M01_CLOSE_POLICY.md) e [contenção durante CAS](M01_PENDING_CONTAINMENT.md). Close e contenção durante renovação já foram integrados; a fila seguinte não deve tratá-los como incrementos ainda ausentes.

O [incremento da bridge Core](M09_CORE_NATIVE_BRIDGE.md) integra a autoridade
nativa R4 e os backends embedded/HTTP. Sua
[evidência coordenada](test_runs_20260930_native_domain.json) inclui pacotes
instalados, recuperação de resposta perdida, execução embedded com imports
Connector recusados e a correção de concorrência de leitura/escrita do estado
no Windows. O socket Pi e seus hooks de composição têm evidência técnica
parcial no checkpoint abaixo. Configuração aprovada, renovação e composição
automática pelas entradas de produto continuam na fila de conclusão.

A [revisão desta entrega](delivery_scope_review_20260930.json) registra os
HEADs, hashes e resultados observados no workspace. Core e Connector já
publicaram o owner do socket Pi e a retenção de producers durante shutdown.
A adoção correspondente no Nexus é publicada no commit que contém o
[manifesto Pi](test_runs_20260930_pi_owner.json). Os XMLs disponíveis registram 143 passes Core, 264 passes e um
skip Connector, 33 passes Nexus e dois passes embedded com imports do
aplicativo Connector bloqueados. São campanhas anteriores inspecionadas
na revisão de planejamento, com sobreposição. O incremento seguinte
reexecutou os 33 testes Nexus instalados antes de publicar a integração.

O peer Pi é técnico e sua qualificação é forçada no teste. O caso embedded
prepara a autoridade por uma fixture WSS compartilhada: comprova a
independência de imports e o owner, mas não comprova o produto local sem
WSS. O wheel Nexus inclui assets previamente modificados, sem aceite de UI.
Esses resultados não encerram M05/M06/M09 nem compõem uma release final.

O [incremento de intenção durável](M02_DURABLE_CAPABILITY_INTENT.md) adiciona
persistência antes da emissão, gravação no vault e ownership da espera pelo
Connector. A [campanha instalada](test_runs_20260930_capability_reservation.json)
registrou 275 passes Connector, um skip e 61 passes Nexus. A porta de abertura
foi exercitada com peer técnico. Reidratação sob autoridade reconciliada,
configuração automática, renovação e retenção terminal continuam pendentes;
P6.1 permanece parcial.

A [recuperação explícita](M02_CAPABILITY_RECOVERY.md) acrescenta leitura
correlacionada de metadata e recuperação do segredo sob lease aplicada
concordante no Server e Core. A [campanha](test_runs_20260930_capability_recovery.json)
passou 283 testes Connector (um skip) e 73 Nexus. A primeira tentativa de
build foi recusada por assets obsoletos; o rebuild isolado foi verificado.
A porta existe; sua adoção automática após reconciliação do daemon e o
agendamento de renovação continuam pendentes.

### Evidência disponível e seu alcance

| Registro | Resultado registrado | Limite |
|---|---|---|
| [Auditoria inicial M00](M00_AUDIT.md) | 2.829 casos Nexus, 240 Connector e 925 Core coletados; 31 de 85 tarefas tinham entrada candidata coletável | Inventário histórico a atualizar; coleta não comprova os critérios de aceite |
| [Incremento Core 0.2.28](test_runs_20260930_pending_containment.json) | Core 920 passes/74 skips; Connector 241 passes/2 skips; Nexus R4 69 passes; contenção instalada 12 passes; integração instalada 19 passes | Campanhas sobrepostas, peers sintéticos; sem aceite final de produto |
| Campanha instalada de conformance Core | 99 passes, sem falhas ou skips; `python -I`, pacote instalado e hash do wheel | Runner/evidência publicados em `9d244cf`; contratos sintéticos, sem fechamento de M01 |
| [Onboarding por operador](M03_OPERATOR_BINDING.md) | Nexus R4 77 passes; 11 casos com wheel instalado fora dos clones | Operador direto, inventário sintético e grant separado; sem ciclo de runtime |
| [Capabilities de sessão](test_runs_20260930_capabilities.json) | Nexus R4: 137 passes; integração instalada: 120 passes; Connector: 343 passes e dois skips existentes | Grupos sobrepostos; reserva e validação de autoridade comprovadas; handlers MCP/nativos, composição do ambiente e aceite de provider pendentes |
| [Handlers MCP](test_runs_20260930_mcp_capabilities.json) | R4: 159 passes; integração instalada: 165 passes; arquivo final de handlers: 23 passes; strict instalado após correção da fixture: um pass | Campanhas sobrepostas e executadas em momentos diferentes; oito ferramentas e claims canônicos comprovados; ações nativas, inbox, hosts e providers pendentes |

O runner `tools/run_r4_installed.py` e a evidência de conformance estão no
Core em `plans/implementation/evidence/r4-installed-campaign/`. As duas
tentativas anteriores com falha de resolução de helpers foram preservadas.
A campanha foi reexecutada após revisar o runner. Não transforma testes de
contrato em prova do dispatcher, daemon ou provider.

O [incremento de operador](M03_OPERATOR_BINDING.md) conclui a criação
transacional de perfil/endpoint habilitados para prepare/apply pelo operador
canônico. A prova delegada foi revisada para publicação neste incremento, com evidências
locais conferidas de 86 casos R4, 48 regressões de aprovação, sete de migração
e 27 instalados; os grupos se sobrepõem. As tentativas anteriores falharam
na expectativa de HTTP de storage e na ausência de consentimento do caller
vertical; seus registros foram preservados.
Completar reuso autorizado no self-bind e compor a jornada com os owners
continuam na fila. Nenhum gate foi encerrado.

O Connector publicou o DTO completo de consentimento e a correção de
isolamento do teste de pacote em ce7864d/40a8cb0. Sua regressão
registrou 246 passes, uma falha e dois skips; após corrigir a contaminação por
PYTHONPATH, os dois casos de pacote passaram no rerun. Isso não equivale
a uma nova execução verde de toda a suíte. A revisão de planejamento
preserva os hashes e os resultados desse registro.

O [bootstrap de abertura](M04_OPEN_BOOTSTRAP.md) agora registra o envio
autorizado antes da lease e associa sua instalação ao outbox atomicamente.
A jornada pública de binding/grant/admissão chegou a open/turn/receipt no
Core com peer sintético, sem semear binding ou operação. Passaram 97 casos
R4, sete de migração e 46 instalados, com sobreposição. Naquela campanha o dispatcher foi invocado pelo teste. O incremento seguinte
[liga o loop Server ao WSS](M04_REMOTE_DISPATCH_PUMP.md): a jornada pública
percorre open/submit/steer/interrupt/close e testa perda de conexão sem reenvio.
Naquela campanha os owners embedded/daemon e o resolver físico de produto continuavam pendentes.

O [owner de conexão Connector](M06_CONNECTOR_CONNECTION_OWNER.md) completa
reader único e filas limitadas para a jornada técnica remota. Passaram 13
contratos/ciclos de vida e 28 casos instalados. A repetição da integração
revelou uma corrida entre ACK de lease e receipt HTTP; o owner agora confirma
o commit com replay idempotente da mesma requisição no WSS. A campanha
corrigida passou. O incremento seguinte de [seleção física](M06_PHYSICAL_SELECTION.md) persiste
o binding aprovado no StateStore, valida instalação/workspace e compõe o
Core pelo host. Passaram 278 regressões Connector (dois skips), 103 casos
Nexus R4 e 55 instalados, com sobreposição. Daemon/CLI, executor persistido,
perfil/ambiente e refresh de revisões ainda precisam dessa integração antes
de aceitar M06.

O [consumidor de execução do daemon](M06_DAEMON_EXECUTION_OWNER.md) agora
executa as operações recebidas e projeta receipts. A jornada WSS admite e
consulta cinco ações, sem chamar Core diretamente no teste. Passaram 286
regressões Connector (dois skips), 17 casos dirigidos, 103 Nexus R4 e 63
instalados, com sobreposição. As sete traduções foram exercitadas com Core e
peer sintético. Startup automático, ambiente/capability de produção, renovação,
reconciliação e publicadores duráveis ainda impedem o aceite completo.

O [registro persistente de executor](M02_EXECUTOR_REGISTRATION.md) acrescenta
o schema 5 e a CLI de registro, consulta e listagem. A intenção é gravada
antes do HTTP; replay recupera o mesmo executor e um novo bootstrap mantém
o segredo fora do estado e da saída. Foram registrados 300 passes Connector
(dois skips existentes), 40 dirigidos, 104 Nexus R4 e 78 instalados, com
sobreposição. A prova pública usa CLI e HTTP reais. Usar esse registro no
startup automático, publicar inventário, anexar lanes e renovar autoridade
continuam pendentes; registro isolado não autoriza execução.

O [startup automático do controle](M06_DAEMON_STARTUP.md) agora usa o registro
persistente, consulta o protocolo, negocia o canal e publica inventário com
sequência durável. Reboot e reconnect exigem a nova geração reconciliada para
trocar o produtor. A jornada real percorre CLI, daemon, HTTP/WSS e IPC em dois
boots; o caso positivo usa qualificação sintética. A reconciliação inicial
verifica journal e ambos os ledgers, recusando fatos não vazios. Ainda faltam
a ligação automática das lanes aos consumidores e o ambiente/capability de
produção. Este incremento não fecha M06.

A [emissão de capabilities de sessão](M02_SESSION_CAPABILITIES.md) acrescenta
o segredo único por audiência/escopo, replay e substituição restrita, o port
de validação de autoridade ativa e renovação de validade no commit da lease.
O cliente Connector valida o DTO e o prazo contra o opening canônico.
Naquela campanha ainda faltavam os guards dos handlers. O incremento MCP
seguinte cobre oito ferramentas; as ações nativas foram integradas no incremento
posterior. Permanecem ferramentas restantes e adoção no ambiente aprovado dos hosts. NS03.04 permanece parcial. As campanhas e tentativas
estão no manifesto, sem transformar teste de reserva em aceite de ferramentas.

O incremento de [autoridade MCP](M09_MCP_SESSION_AUTHORITY.md) integra oito
ferramentas, incluindo claim/complete canônicos com escopo de sessão persistido.
O guard roda também no UOW do efeito. Inbox limitado ao workspace, demais
ferramentas e adoção automática no ambiente aprovado dos hosts continuam
pendentes. Ações nativas foram acrescentadas no incremento seguinte. O [manifesto corrente](test_runs_20260930_mcp_capabilities.json) preserva
o alcance dos testes e não encerra gates.

O incremento de [ações nativas](M09_NATIVE_ACTIONS.md) implementa contexto,
claim e complete pela rota pública, com audiência própria, resultado durável
e efeito no mesmo UOW. A disputa com MCP usa o mesmo claim; recuperação de
resposta perdida e recriação da aplicação preservam o resultado original.
A bridge pública Core e os hooks dos hosts já têm integração técnica parcial.
Permanecem configuração e composição automáticas de produto, inbox e ferramentas restantes. O [manifesto](test_runs_20260930_native_actions.json)
registra campanhas dirigidas, regressão e instalação, sem fechar gates.

### Lacunas prioritárias observadas

| Área | Lacuna e destino |
|---|---|
| Core R4 — M01 | `R4_BUNDLE_EXECUTABLE=False`; revisar conformance das sete ações, erros e consumidores instalados antes de promover o contrato |
| Onboarding — M02/M03 | Aprovação direta do operador cria perfil/endpoint habilitados; prova delegada revisada neste incremento; completar self-bind com autorização preexistente, mantendo identidade e CAS |
| Dispatcher — M04 | Loop WSS Server já reserva, revalida, envia e recupera reservas de owner substituído; completar composição embedded/daemon com o resolver físico aprovado, governança e recuperação de envios incertos |
| Local — M05 | `bootstrap/runtime_host.py` precisa receber seleção/contexto da autoridade canônica e operar no ciclo real de `serve`, sem aplicativo Connector |
| Remoto — M06 | Reader, seleção e consumidores de efeitos já são adotados pelo daemon na jornada WSS técnica; startup de controle e inventário já usa o registro persistido; conectar automaticamente lanes/consumidores ao perfil/ambiente aprovado, refresh de revisões, renovação de tickets/leases e reconciliação não vazia; extrair SQL/transições restantes do handler Server |
| Governança e observação — M07–M09 | Oito handlers MCP já validam capability e autoridade na transação; ações nativas HTTP já compartilham claims e replay; completar demais ferramentas/inbox, composição automática da bridge Pi a partir do perfil aprovado, eventos/receipts recuperáveis, decisões/input e consumo exclusivo entre canais |
| Jornadas e idioma — M10 | Completar UI/CLI, infraestrutura de testes de navegador e auditoria US English, incluindo superfícies legadas |
| Robustez e migração — M11/M12 | Provar recovery, revogação online/offline, ownership/shutdown e limites; ensaiar cutover e rollback com dados legados |
| Qualificação — M13 | Resolver regressões conhecidas, pipeline/empacotamento e matriz provider/SO/hosts sobre os artefatos finais |

As duas regressões de upgrade e expectativa MCP stdio registradas na campanha de 311 casos foram corrigidas no incremento MCP; passaram os 20 casos dirigidos e a campanha instalada correspondente. A campanha seguinte de ações nativas reexecutou os 311 casos, todos aprovados. Outras regressões de migração, superfície compacta/descrições e fixtures de Claude attach continuam com destino em M02/M09/M12 conforme o domínio. Preservar o gate de redução de 40% da superfície compacta. Uma expectativa antiga só deve mudar quando o contrato e a regressão substituta justificarem a alteração.

### Fila imediata de execução

A ordem abaixo detalha os próximos incrementos. O fechamento de cada marco continua dependente de todos os seus requisitos originais.

| Ordem | Trabalho e responsável | Prova e publicação |
|---|---|---|
| 1 | Três repos: atualizar M00 por critério de aceite, defeito, nodeid e ambiente; integrar a campanha Core publicada ao mapa de critérios | Cada requisito tem implementação/caller, teste existente ou a criar, responsável e ambiente; preservar o histórico de falhas |
| 2 | Core + consumidores: completar a conformance instalada de M01 | Sete ações, erros, targeting, lease/revogação e histórico R3; mesmo wheel/hash nos dois consumidores; readiness de host avaliada separadamente |
| 3 | Nexus + Connector: fechar autoridade e onboarding M02/M03 | Prepare sem efeito; aprovação exigida vinculada ao diff/revisões; apply habilita perfil/endpoint somente com autoridade válida; replay recupera o mesmo binding |
| 4 | Nexus: completar M04 a partir do loop WSS implementado, com composição dos executores e recuperação | `OPEN_AUTHORIZED_PENDING_LEASE` permite resolver a realização e obter lease; nenhum prepare/open/spawn antes da instalação; budget e efeito no máximo uma vez |
| 5 | Nexus/Core e Connector: compor os owners de M05/M06 | Local instalado sem Connector; remoto por Server/daemon reais, com StateStore, reader do socket, leases e reconciliação paginada |
| 6 | Três repos: completar M07–M11 | Histórico, eventos, approval/input, MCP/bridge, UI/CLI, idioma, recuperação e contenção exercitados pelos mesmos callers |
| 7 | Três repos: concluir M12/M13 | Migração/rollback e campanhas completas sobre o conjunto final; artefatos, commits, hashes e runbooks publicados |

### Próximos incrementos com saída objetiva

Estes lotes organizam o trabalho restante de M00 a M13. Não substituem as tarefas e dependências do backlog nem antecipam o fechamento de um marco. As dependências estruturadas estão em `execution_batches` de [delivery_plan.json](delivery_plan.json). P5 e P6 são frentes independentes depois de P4; P9, P10 e P11 podem avançar depois de P8. A preparação de testes, interface e laboratório começa antes do fechamento dessas dependências.

| Lote | Responsável e trabalho | Testes e condição de saída |
|---|---|---|
| P1 — baseline e evidência | Três repos: incorporar os incrementos de daemon e registro persistente ao mapa de aceite, atualizar nodeids por critério e classificar regressões e ambientes | Hashes de fonte/artefatos conferidos; falhas e reruns preservados; nenhum requisito sem responsável, teste ou motivo de pendência |
| P2 — contrato compartilhado | Core: completar a conformance de cada ação/erro e os helpers públicos; consumidores: instalar o mesmo wheel | Sete ações e R3 histórico exercitados por consumidores instalados; schema gerado sem drift; promoção de executable fundamentada, readiness do host independente |
| P3 — onboarding reutilizável | Nexus/Connector: reusar autorização e configuração aprovadas, leitura/options do binding, seleção e consentimento do host | Primeiro e segundo uso pela entrada pública; identidade cruzada, deny, drift, replay e revisão concorrente; grant explícito separado do consentimento |
| P4 — abertura e outbox | Nexus: partir do loop WSS já implementado; completar reconciliação de envio incerto, composição local e consumidores do resolver físico aprovado | Resolver realização → instalar lease → prepare/open; nenhum spawn antecipado; resposta perdida/crash não criam nova operação; fila saturada preserva controle |
| P5 — ciclo local | Nexus/Core: conectar o owner de serve à mesma admissão, seleção, contexto, journal e projeção | Pacotes instalados sem aplicativo Connector; open/submit/steer/interrupt/close pelo caller real; peer técnico primeiro e provider real depois |
| P6 — ciclo remoto | Connector/Nexus: partir do startup de controle e inventário publicado; compor perfil/ambiente/capability aprovados, attach automático, rotação de tickets, renovação de lease e reconciliação paginada | Server/daemon reais; report não vazio com mais de 256 IDs; reconnect/rotação/ACK antigo; mesmo ciclo de cinco ações antes de decisões/input em M08 |
| P7 — observação durável | Três repos / M07: concluir publicadores de eventos e receipts, ingresso transacional, ACK e replay paginado | Reiniciar sem novo evento nativo e recuperar publicação; duplicação, gaps, perda de ACK e namespaces coincidentes; histórico disponível sem provider |
| P8 — decisões e input | Três repos / M08: integrar pedidos nativos às decisões canônicas e operações únicas, com retenção protegida | Aprovação/input pela UI/API/CLI; concorrência, timeout, reboot, negação e autoaprovação; exatamente uma aplicação nativa autorizada |
| P9 — ferramentas e domínio | Nexus com Core/Connector / M09: MCP HTTP direto, capability de sessão, bridge Pi e trabalho governado | Tools-only sem daemon; audiência/ação proibida; revogação; disputa de consumo, handoff e resultados com causalidade; regressões do domínio |
| P10 — jornadas e idioma | Nexus/Connector com revisão Core / M10: concluir interface, CLI humana/headless e inglês US em todas as mensagens próprias | Primeiro/segundo uso, sessão nova/reuso, offline, aprovação, input e histórico em navegador real; TLANG-01–04; assets conferidos no wheel |
| P11 — falhas e limites | Três repos / M11: recovery, revogação, shutdown, ownership, contenção e carga | Kill/partição/disco cheio nas fronteiras de commit; zero efeito sem autoridade; controle sob saturação; memória/filas/shutdown dentro dos limites; CN5 completo |
| P12 — atualização de instalações | Três repos / M12: migração, drain, cutover, remoção de duplicação e rollback | Bases legadas e sessões pendentes; interromper cada checkpoint, repetir migração, restaurar banco/journal e comprovar retomada sem reset |
| P13 — entrega integral | Três repos / M13: congelar commits, construir artefatos e executar campanhas finais | Mesmo Core por hash; Windows/Linux e Python suportados; providers reais local/remoto, A/B/C, UI/CLI e regressões; todos os casos obrigatórios aceitos e G0–G3 fechados |

Cada lote termina com relatório, commit e push em `feature/v0.2.0` dos repositórios alterados. Um resultado parcial continua parcial no inventário, mesmo depois de publicado.

### Decomposição do ciclo local restante (P5)

A configuração aprovada e a intenção durável de segredo são requisitos
comuns a P5 e P6.1. Implementar os contratos comuns uma vez e integrar cada
host, preservando a independência das topologias.

| Passo | Mudança e fronteira | Prova de saída |
|---|---|---|
| P5.1 — composição canônica | Ligar binding, perfil, candidato completo, root aprovado e contexto ao owner de serve; retirar semeadura de autoridade do teste de produto | Onboarding público → admissão → lease local aplicada → prepare/open; nenhum WSS, daemon ou import Connector; configuração inválida falha antes do spawn |
| P5.2 — ambiente e ferramentas | Resolver referências protegidas por abertura; usar renderização pública Core para MCP HTTP e owner Pi; persistir intenção antes de emitir capability | Segredo ausente, resposta perdida e drift de configuração; nenhuma credencial em argv/logs; ferramenta alcança o mesmo claim canônico |
| P5.3 — ciclo e observação | Encadear as cinco ações iniciais, receipts, eventos, seleção/reuso e encerramento pelo dispatcher local | UI/API/CLI consultam o mesmo operation_id; novo turno não cria processo; sessão nova é explícita; dois ambientes simultâneos não se misturam |
| P5.4 — recuperação e autoridade | Renovar/revogar contexto e capability; recuperar journal/ledger e obrigações; manter owner enquanto houver efeito incerto | Execução além da primeira validade, restart, waiter cancelado e shutdown com producer pendente; nenhum efeito após revogação; histórico sem binário |
| P5.5 — instalação local pura | Instalar Nexus e Core em ambiente novo, sem aplicativo Connector; executar pelo serve e callers públicos | Confirmar ausência de Connector e WSS local; peer técnico pelo fluxo público, sem semear binding/operação no aceite; repetir com providers reais em M13 e governança completa de M08/M09 |

### Decomposição do ciclo remoto restante (P6)

O controle e o inventário já iniciam automaticamente. A ligação de runtime deve ser concluída em incrementos verificáveis, usando os contratos normativos de perfil, sessão, ticket e capability. Se faltar um campo público necessário, registrar a lacuna, ajustar a fonte contratual competente e testar os consumidores antes de adotá-lo.

| Passo | Mudança e fronteira | Prova de saída |
|---|---|---|
| P6.1 — configuração aprovada | Nexus expõe a configuração autorizada; Connector associa perfil, realização, configuração e revisões ao binding persistido. Compor ambiente e referências protegidas pelo Core; incluir instalações explícitas aprovadas no inventário completo | Nenhum ambiente sintético vazio usado como configuração de produção; perfil desabilitado, configuração alterada durante espera, segredo ausente e candidato fora do inventário falham antes do efeito; nenhuma credencial em logs/estado público |
| P6.2 — composição automática | Daemon obtém ticket do binding, espera ACK da lane atual e registra o consumidor de operações existente. Abrir somente após instalar lease; manter um owner por conexão e namespace | CLI de registro/onboarding → restart do daemon → admissão pública → Core, sem o teste chamar attach/adoption/execute manualmente; repetir com duas identidades e namespaces isolados |
| P6.3 — renovação e rotação | Ligar renovação de tickets/leases e lifecycle da capability; revalidar autorização e configuração após cada espera. Preservar request/serial e prazo monotônico; revogar somente no escopo correto | Sessão permanece correta além da primeira validade; replay não amplia prazo; ACK antigo, resposta tardia, revogação e mudança de owner não reautorizam efeito; capability ativa não é substituída por retry cego |
| P6.4 — recuperação não vazia | Substituir a aceitação exclusiva de namespace vazio por reconciliação paginada de journal, claims, slots, operações e watermarks. Retomar obrigações de publicação com P7 | Mais de 256 registros; crash após efeito possível; storage indisponível e cursor inválido mantêm recuperação pendente; nenhuma operação incerta é reenviada por ausência de resposta |
| P6.5 — composição instalada | Executar Server e daemon em processos independentes, usando estado persistido e entradas públicas. Vincular receipts ao ciclo real e confirmar shutdown dos owners | Open/submit/steer/interrupt/close com o mesmo Core instalado, sem forçar prontidão no aceite; depois incorporar decisões/input em P8 e providers/hosts reais em P13 |

Os subpassos admitem testes técnicos com peers e qualificação sintética explicitamente identificados durante o desenvolvimento. A saída de produto P6.5 exige prontidão obtida pelo contrato e pelo host. O fechamento de M06 permanece condicionado a todos os critérios normativos, inclusive CON-R4-02/04 e CN5 Q03.

### Conclusão da autoridade de sessão antes da adoção pelos hosts

O checkpoint publicado já emite e valida capabilities limitadas à sessão e protege oito ferramentas MCP na transação do domínio. Os próximos incrementos devem fechar as fronteiras abaixo. São partes de M02/M05/M06/M09, preservando o grafo de fechamento dos milestones.

| Ordem | Implementação restante | Testes e critério de aceite |
|---|---|---|
| 1 — guard Nexus (M02; aceite de domínio M09) | Partir dos oito handlers MCP e das três ações nativas HTTP publicados; integrar inbox limitado ao workspace e demais ferramentas aos mesmos casos de uso. Validar audiência, ação, sessão, binding, revisões e lease aplicada; preservar permissões de domínio e claims | Chamada autorizada pelo handler real; negar token reservado sem sessão ativa, audiência/ação/escopo incorretos, grant revogado, lease expirada e revisão alterada. A chave de agente tools-only mantém sua jornada própria |
| 2 — intenção e segredo Connector (M02/P6.1) | Partir do owner de emissão e do vault já integrados à porta de abertura; compor o ambiente aprovado automaticamente e adotar a porta de recuperação após reconciliação de restart, com retenção terminal e agendamento de renovação. Recuperar perda de resposta pelos metadados canônicos | Crash antes/depois do envio e da gravação; nenhuma credencial em argv, logs ou estado público; substituição apenas quando comprovadamente permitida; sessão em execução não recebe retry cego de emissão |
| 3 — adoção pelos hosts (M05/P6.2) | Conectar seleção, configuração e referências autorizadas ao owner embedded e ao daemon, usando as APIs públicas Core | Fluxo público de onboarding → open → ferramenta com pacote instalado, sem ambiente sintético de produção; local sem aplicativo Connector e remoto sem paths livres no Server |
| 4 — ciclo de vida (P6.3/M09/M11) | Renovar e revogar autoridade com a lease aplicada, sem reancorar replay ou substituir silenciosamente material ativo | Sessão ultrapassa a primeira validade; perda de ACK, resposta tardia, revogação e mudança de owner não permitem novo efeito. Falhar separadamente WSS e MCP HTTP e comprovar isolamento |

A emissão HTTP isolada e o port de autorização já testados não encerram esses aceites. Cada incremento atualiza o inventário com os nodeids executados e publica código, evidência e hashes juntos.

### Integração nativa: fronteira Server e adoção pelos hosts

A rota Server de M09 já compartilha o claim canônico usado pelos handlers MCP. A composição automática do caller com a configuração aprovada é a próxima fronteira; os hooks e o socket já têm prova técnica parcial. Sua implementação pode avançar antes do fechamento das dependências de M09; o aceite integral do marco continua subordinado a M08 e aos critérios normativos.

1. **Contrato e entrada Nexus implementados:** `POST /v1/runtime/native-actions` para `context`, `claim` e `complete`, com capability da audiência nativa, escopo exato e payload validado. Explicitar a tradução para os tipos públicos do Core e os limites de request; não exigir `tools/call` para a audiência nativa.
2. **Transação e repetição:** persistir identidade, digest e resultado do pedido junto ao efeito canônico quando houver mutação. Repetição idêntica recupera o resultado autorizado; mesmo ID com conteúdo diferente falha; perda da resposta não cria uma nova tentativa com ID diferente. Revalidar autoridade e permissões antes do efeito e do replay.
3. **Um único claim:** MCP, execução embedded e bridge Pi usam o mesmo caso de uso e a mesma propriedade de claim/epoch. Preservar isolamento por sessão, agente e workspace, budgets e causalidade de resultados. Não criar uma segunda máquina de estados de handoff no Core ou Connector.
4. **Caller dos hosts:** aproveitar os backends e hooks já implementados, conectá-los à configuração aprovada e às referências protegidas. O peer técnico já chama a extensão pelo child Pi; o aceite exige onboarding público, composição automática e provider qualificado.
5. **Prova:** sucesso de contexto/claim/complete; audiência e ações cruzadas negadas; lease/revisão/autoridade inválidas; disputa simultânea MCP/nativa; rollback na falha do armazenamento; restart e resposta perdida antes/depois do commit; replay e conflito de digest; resultados sem causalidade recusados. Capturar contagem de efeitos e conferir o mesmo claim persistido.

Concluir a composição do caller da bridge, inbox limitado ao workspace e as ferramentas restantes, integrar o ambiente dos hosts e exercitar o ciclo de vida das capabilities. O fechamento continua exigindo regressões de domínio, tools-only independente de WSS, superfície compacta e provider real quando aplicável.

### Aceite concreto do próximo fluxo de produto

A jornada abaixo deve existir como teste instalado de integração, primeiro com peer técnico e depois com os providers exigidos. O peer técnico verifica o encadeamento e não qualifica um provider.

1. Partir de identidade/configuração de laboratório válidas. Registrar ou selecionar executor pela entrada pública, publicar inventário e aprovar a realização no host correto.
2. Preparar binding e registrar consentimento do agente e prova de operador quando a política exigir. Vincular a prova ao sujeito, proposta, diff e revisões; outra identidade, prova expirada e alteração concorrente devem falhar.
3. Aplicar a proposta por API/CLI/UI: criar vínculo reutilizável com perfil aprovado, endpoint habilitado e autoridade canônica. A habilitação não pode decorrer apenas da autenticação do próprio agente. Emitir o grant de runtime explicitamente pela autoridade canônica, com ações, orçamento e validade; consentimento do binding não emite esse grant implicitamente.
4. Resolver e admitir `runtime.open` com um `client_intent_id`; persistir operação/outbox juntas e consultar o resultado após resposta perdida. Não semear binding, grant, sessão ou operação para contornar a jornada sob teste.
5. O dispatcher entrega o envelope inicial ao owner correto. O owner resolve a realização aprovada, obtém/instala a lease e só então prepara/abre no Core. Recibo correlacionado projeta o estado da sessão.
6. Admitir submit, steer, interrupt e close pela mesma autoridade; observar receipts/eventos e recuperar a mesma operação após replay/restart. Somar approval/input ao fluxo em M08.
7. Repetir local puro e remoto, com contagem de efeitos nativos e asserções de estado persistido. O caminho remoto não recebe paths livres nem depende de binários no Server.

Testes negativos obrigatórios desse fluxo: falta de consentimento, autoaprovação, perfil desabilitado, inventário stale, drift de root/binário, revisão alterada, perda de resposta de apply/open, lease ausente/expirada/revogada, ACK antigo, fila cheia e desconexão após efeito possível. Cada falha precisa de resposta própria em US English e preservar a consulta pelo ID original.

A preparação de Windows/Linux, Python suportado, providers autenticados e Servers A/C + executor B começa em M00. Ausência de laboratório mantém o aceite dependente pendente; WSL e processos locais não provam hosts independentes. Continuar os trabalhos sem essa dependência.

### Preservação do workspace

O Nexus contém alterações prévias: 599 exclusões em `plans/`, três assets HTTP modificados, uma evidência modificada e um diretório de teste não rastreado. O Core contém `=1`; a campanha instalada citada já foi publicada. Os incrementos de implementação e suas evidências são publicados separadamente dessas alterações prévias. Usar staging explícito, preservar esses itens e construir frontend em diretório isolado até comparar os assets existentes.

## Responsabilidades e invariantes de implementação

| Produto | Responsabilidade |
|---|---|
| Core | Catálogo, descoberta, qualificação, candidato completo, codecs/hashes/reducers, targeting, runtime nativo, journal, slots, contenção e fatos de efeito. Sem daemon, identidade canônica ou servidor MCP. |
| Nexus | Identidade, política, consentimento, domínio, admissão, outbox, leases, decisões, ingresso durável, UI/API/CLI, executor embedded e transporte remoto. Não importa a aplicação Connector nem executa paths remotos. |
| Connector | CLI, armazenamento local, credenciais, daemon, WSS outbound, realização física, publicação, recuperação e host do Core remoto. A CLI solicita e consulta operações; o dispatcher remoto produz efeitos. |

As sete ações são `runtime.open`, `turn.submit`, `turn.steer`, `turn.interrupt`, `runtime.close`, `approval.decide` e `input.provide`. O enum e o targeting vêm do Core. Rejeitar campos extras, argv/env livres, escopo incompleto, revisão antiga e autoridade autodeclarada antes de tocar no recurso.

Preservar `client_intent_id`, `operation_id`, hash, namespace, gerações e revisões de ponta a ponta. Resolve é sem efeito. Admissão e outbox fazem commit juntas. I/O nativo ocorre depois do commit. Resposta perdida exige consulta ao mesmo ID; `OUTCOME_UNKNOWN` não concede retry, novo processo ou troca de executor.

Socket conectado, lane admitida, reconciliação concluída, lease instalada e runtime pronto são estados diferentes. A prontidão local deve ser avaliada para o executor embedded; não herdar indiscriminadamente um booleano de disponibilidade remota. Anunciar R4 executável exige evidência do Core; anunciar um host pronto exige também suas próprias condições.

O envelope inicial `OPEN_AUTHORIZED_PENDING_LEASE` permite ao executor resolver a realização e pedir a lease. Não permite `prepare`, `open` ou spawn antes da instalação do contexto no Core. Essa sequência deve ser explícita para evitar a dependência circular entre abertura e lease inicial.

Negação explícita prevalece. O agente do endpoint vinculado é o sujeito da lane; o registrante técnico do executor não substitui a autoridade dos outros agentes. Rotação/revogação é escopada. Um ticket NXL não autentica MCP, e uma capability de sessão não vira chave administrativa.

## Marcos de execução e aceite

### M00 Auditoria e inventário de aceite

**Responsáveis:** três repositórios. **Cobertura:** NS00.01–03. **Dependências:** nenhuma.

Conferir branch, HEAD, dirty state, versões, lockfiles, wheel e hashes. Classificar cada requisito como existente com prova integral, parcial ou ausente. Relacionar cada teste a um nodeid realmente coletável; corrigir discrepâncias entre comandos propostos e testes existentes. Registrar provider/build/SO/arquitetura, ambientes de laboratório, credenciais disponíveis e executor de cada campanha.

Separar defeitos de código de dependências de laboratório. Um Core incompleto ou daemon sem integração é trabalho interno, não bloqueio externo. Uma máquina Linux ou credencial de provider ausente é requisito de ambiente a provisionar. Registrar os limites iniciais já definidos no documento 03 e conferir sua aplicação no código; fixar os orçamentos adicionais de bytes, shutdown e latência a partir da baseline medida antes da campanha de carga. Qualquer ajuste dos defaults exige justificativa e nova evidência.

**Saída:** inventário fechado, cobertura integral, ordem sem ciclos, catálogo dos comandos de teste e lista objetiva de ambientes a preparar. Testes de produto ainda não executados permanecem `NOT_RUN`.

### M01 Contrato Core executável e compartilhado

**Responsável principal:** Core. **Cobertura:** NS00.04–05, CORE-R4-01–03. **Dependência:** M00.

Concluir a fonte única geradora do bundle R4, schemas fechados dos 21 tipos de frame e sete verbos, vetores JCS/hash, tipos públicos e reducers de attach, reconcile, lease, operação, evento e aprovação. Completar validação de grant, geração/owner, target, expiração e aplicação/revogação do contexto. Exportar discovery, resolução de instalação, catálogo/capacidades e história paginada sem imports privados nos consumidores.

Preservar bytes e hashes históricos R3. Completar projeções verificadas de receipts e erros de todas as ações, inclusive decisão/input. Comparar operações equivalentes pelos dois hosts contra o mesmo peer Core, com casos negativos antes da escrita nativa. `R4_BUNDLE_EXECUTABLE` e o manifest só mudam após essa conformance; a mudança não habilita hosts automaticamente.

Construir uma vez o wheel de desenvolvimento, registrar SHA-256 e instalar o mesmo arquivo em Nexus e Connector, com pins e locks sincronizados. Testar importação isolada, recursos do pacote, schemas, APIs públicas, catálogo, duas instalações byte a byte iguais e fixtures R3/R4 cruzadas.

**Saída:** contrato executável consumível pelos dois aplicativos, exemplos públicos e conformance positiva/negativa. Qualificação de providers fica para a campanha própria.

### M02 Composição persistência e autoridade

**Responsável principal:** Nexus. **Cobertura:** NS01–NS03. **Dependência:** M01.

Concluir composição neutra, CLI principal, `/v1` direto e `/api/v1` legado, MCP apenas HTTP, extras instaláveis e migração CAS da configuração selecionada. Consolidar migrações aditivas, IDs estáveis, constraints, índices, readers históricos e fronteiras transacionais.

Completar autenticação de agente/operador, prepare/apply de política herdada, tickets por audiência/alvo/escopo, renovação, key rotation, revogação e capability MCP de sessão. Gerar comandos Bash/PowerShell com entrada protegida, sem chaves no argv ou tentativa de recuperar plaintext de hash. Usar o serviço de identidade existente e preservar negações.

**Testes:** NS01–03 e equivalentes TN/J; 100 mil agentes com lookup indexado; dois agentes por executor; dois Servers com IDs locais iguais; ticket cruzado, expirado, revogado e substituído; agente tentando autoaprovar; capability usada fora da sessão; configuração concorrente; import/help sem spawn. Verificar backup/restauração da expansão do schema.

**Saída:** fundação autenticada e persistente, com G0 revisável. Rotas de capability recebem integração de sessão novamente em M05/M09.

### M03 Inventário consentimento e bindings reutilizáveis

**Responsáveis:** Nexus e Connector, com APIs Core. **Cobertura:** NS04–NS05, CON-R4-05. **Dependência:** M02.

Ligar discovery ao executor correto e preservar o candidato completo, incluindo Node e script no Pi. Concluir publicação/refresh, sequência, digest, frescor e resolução pela revisão apresentada ao usuário. O Core qualifica localmente; o Server guarda projeções sem paths remotos. Completar respostas de opções e leitura de binding.

Implementar a jornada real de realização local/remota, consentimento no host da pasta, proposta agregada, aprovação requerida, apply CAS e recuperação do resultado por intenção. Integrar perfil aprovado, reuso de sessão, novo processo explícito, mudança de root/binário/config e login de provider como estado visível. O segundo uso não repete a configuração técnica aprovada.

**Testes:** snapshots stale/reordenados/adulterados; mesmo path/versão com bytes diferentes; dois binários idênticos; symlink/root alterado entre preview e apply; apply concorrente; resposta perdida; executor remoto em SO diferente; semeadura somente de pré-condições de identidade, nunca do binding que o teste pretende provar.

**Saída:** binding criado pelas entradas públicas, consultável e reutilizável, com negações e razões de indisponibilidade corretas.

### M04 Dispatcher canônico de operações

**Responsável principal:** Nexus; Connector adapta solicitantes. **Cobertura:** NS06. **Dependência:** M03.

Concluir `ExecutorPort` e o DTO autorizado comum. Implementar o loop de outbox, ownership de reservas, retomada após crash, filas finitas de itens/bytes, faixa independente de controle e revalidação após cada espera. Completar resolve/admit/query para todas as intenções e separar caminho local/remoto por executor elegível.

Ligar UI, CLI Nexus, CLI Connector, REST e entradas do domínio à mesma admissão. O Connector persiste a intenção de operação antes do POST e consulta o resultado; não chama Core em paralelo ao pedido canônico. Preservar consumo exclusivo, delivery/inbox/handoff, actor/subject, causalidade e claims de sessão. Uma abertura seguida de prompt são duas operações correlacionadas.

**Testes:** crash antes/depois de cada commit; perda de resposta; replay idêntico e hash conflitante; autorização alterada durante fila; controle com fila produtiva bloqueada; cancelamento do waiter sem cancelar producer; disputa MCP pull versus dois runtimes; reservas recuperadas uma vez. Contar chamadas nativas e registros, não apenas métodos mockados.

**Saída:** uma intenção produz uma operação durável e, quando autorizada, no máximo um efeito do dispatcher. O primeiro ciclo integrado usa peer técnico; M05/M06 conectam os hosts de produto.

### M05 Execução embedded pela entrada real do Nexus

**Responsáveis:** Nexus e Core. **Cobertura:** NS07. **Dependência:** M04.

Construir seleção e `ExecutionContext` a partir de binding, perfil, realização e autoridade canônicos. Ligar o dispatcher ao host persistente do `serve`, ao journal, ledger, eventos, slots e encerramento. O ambiente, segredos e cliente MCP são preparados por abertura, com contratos públicos Core. Compor portas de aprovação e bridge Pi para a integração de domínio posterior.

Executar abrir, submit, steer, interrupt e close pela UI/API/CLI autorizada, mantendo IDs e receipts. Testar reuso, `--new-session`, sessões simultâneas com seleções/ambientes distintos, waiter cancelado e serve sem harness instalado. Consultar história depois de remover o binário.

**Saída:** ciclo local de produto instalado sem Connector, demonstrado inicialmente com peer técnico e depois com um provider real. G1 final depende também de governança, migração e qualificação em M13.

### M06 Daemon remoto com lanes leases e execução

**Responsáveis:** Nexus e Connector, com Core. **Cobertura:** NS08–NS09, CON-R4-02/04; CN5 Q03. **Dependência:** M04. Pode avançar independentemente de M05 após os contratos comuns.

Extrair estado/SQL do router WSS para serviços/repositórios. Completar TLS/origin/subprotocolo, validação de todo frame, limites, watchdog, reconnect, senders/receivers owned, cancelamento e teardown. Integrar o cliente R4 ao daemon e StateStore; substituir o caminho de efeitos legado após paridade, sem fallback de grants R3.

Completar attach correlacionado, rotação com provider antigo ainda aguardando, renovação de ticket e isolamento entre agentes. Implementar reconciliação paginada de receipts, claims, ownership e watermarks, inclusive relatórios não vazios e falhas de storage. Readiness vem do aceite canônico por lane/sessão.

Implementar remote open por realização aprovada, lease inicial antes do efeito, `lease.applied`, renew/reconnect com request ID, serial crescente e t0 monotônico capturado antes do envio. Replay não reancora prazo; resposta tardia, geração antiga e permissão vazia não autorizam trabalho. Completar submit/steer/interrupt/close, targeting pelo Core e revogação sem takeover silencioso. Verificar desconexão do WSS independentemente de MCP HTTP.

**Testes:** Server e daemon reais em processos separados; report com mais de 256 registros e múltiplas páginas; ACK antigo após rotação; dois agentes e dois Servers; namespace repetido; atraso de grant; relógio de parede alterado; serial replay; link antigo durante nova conexão; filas cheias; nenhuma escrita nativa antes de lease instalada. Depois repetir entre hosts.

**Saída:** ciclo remoto pelo daemon e dispatcher reais. Receipts/eventos completos, decisões e provider/hosts finais são aceitos nos marcos seguintes.

### M07 Eventos receipts e replay duráveis

**Responsáveis:** três repositórios. **Cobertura:** NS10, CON-R4-06; CN5 Q04. **Dependência:** M06.

Unificar ingresso HTTPS/WSS/embedded de receipts, validando origem, escopo, hash e progressão Core. Integrar estágio da operação, outbox e sessão atomicamente. Ingressar eventos idempotentes com watermark contíguo pós-commit; SSE/UI são projeções observadoras. Separar leitura histórica finita de follower, aplicar ACK no Core uma vez e preservar o target do lote.

Recuperar publicadores após falha de leitura, reconnect e reboot sem depender de novo evento do harness. Definir quotas, retenção, gaps explícitos e preservação de terminais. Reads históricos não exigem provider ou processo vivo.

**Testes:** duplicação, out-of-order, lacuna, ACK perdido, ACK2 ausente enquanto lote2 espera, disco cheio, storage bloqueado, desconexão após commit, dois streams com IDs coincidentes em namespaces distintos. Demonstrar retomada do mesmo watermark e ausência de perda silenciosa.

**Saída:** status e histórico observados na aplicação correspondem a fatos duráveis do mesmo ciclo de execução.

### M08 Decisões canônicas e input nativo

**Responsáveis:** três repositórios. **Cobertura:** NS11, CON-R4-03/07; CN5 Q01/Q02. **Dependências:** M05 e M07.

Persistir pedido operacional íntegro separado da exibição redigida, preservando ID nativo tipado, canonical request ID, namespace, turno, generation, hash, revisão e expiry. Completar autoridade de operador, CAS, decisão idempotente e uma operação de aplicação na outbox. `approval.decision` é notificação; não aplica o efeito novamente.

Ligar `approval.decide` e `input.provide` ao Core por argumentos tipados. Diferenciar pedido administrativo e nativo. Conservar producer e resultado se o cliente cancelar, desconectar ou perder resposta. Implementar política explícita para retenção/proteção de input sensível, sem anunciar recuperação de conteúdo que não foi persistido de forma segura.

**Testes:** UI/CLI concorrentes, agente autoaprovando, decisão tardia, request hash alterado, mesmo ID em dois namespaces, turno/generation obsoletos, redaction sem alterar payload operacional, cancelamento depois do efeito possível, reboot e tombstones. Contar uma aplicação nativa e recuperar a mesma decisão/receipt.

**Saída:** aprovações e inputs completam o fluxo local e remoto de produto com integridade e aplicação única.

### M09 Ferramentas diretas e trabalho governado

**Responsável principal:** Nexus; Core/Connector integram a bridge. **Cobertura:** NS12. **Dependência:** M08.

Ligar MCP HTTP gerenciado à capability da sessão e à política canônica renovável. Preservar tools-only com a chave existente e sem Connector. Integrar a bridge Pi qualificada a `/v1/runtime/native-actions` com os mesmos casos de uso, sem servidor/proxy MCP no Core ou Connector.

Preservar contexto, claim, complete, handoff, exclusividade de consumo, correlação de resultados e superfície MCP compacta. Texto livre e término de turno não concluem trabalho governado. Publicar apenas capacidades demonstradas no build/host correspondente.

**Testes:** token com audiência errada, ação proibida, revogação com WSS ativo e vice-versa, tools-only antes/depois de parar daemon, corrida pull/push, resposta de outro agente, bridge sem autorização e resultados sem causalidade. Rodar regressões do domínio existente.

**Saída:** ferramentas e execução compartilham a identidade e o domínio, com canais independentes e autoridade consistente.

### M10 UI CLI completa e inglês US

**Responsáveis:** Nexus e Connector; Core revisa suas mensagens públicas. **Cobertura:** NS13 e LANG-US-01. **Dependência de fechamento:** M08; componentes e fixtures podem começar após M03/M04.

Concluir seleção executor → instalação → workspace, consentimento agregado, primeiro/segundo uso, reuso explícito, start opcional e acompanhamento por IDs. Mostrar estados técnicos e canônicos separadamente, operações desconhecidas, aprovação/input, executor offline, inventário stale, drift e login pendente. A CLI humana e headless deve ter paridade, erros estruturados, exit codes, aliases inequívocos, entrada protegida e logs apenas observadores.

Auditar todo texto autorado pelas aplicações: UI, títulos, tooltips, labels de acessibilidade, validação, estados vazios, CLI help/prompts, REST/MCP/WSS, erros Core, diagnósticos, logs e mensagens de retorno. Normalizar as mensagens próprias para US English, inclusive as legadas. Preservar conteúdo do usuário, nomes próprios, códigos estáveis e dados nativos; quando exibidos, identificar mensagens externas como tal em uma apresentação em inglês, sem reescrever evidência bruta ou hashes históricos.

Criar infraestrutura de testes de UI no frontend e ensaios de navegador dos fluxos reais. Usar fixtures para testes de componente e uma aplicação instalada para aceite. Cobrir teclado, foco, contraste, estados de espera/erro e ausência de secrets/path remoto indevido. Validar que os assets empacotados correspondem ao build revisado.

**Testes de idioma adicionais:**

- **TLANG-01:** inventário de strings autoradas nos três repos, incluindo recursos empacotados e mensagens de exceção; revisão humana US English e verificação automatizada com allowlist justificada. Uma regex de acentos não é prova suficiente.
- **TLANG-02:** navegador percorre onboarding, sucesso, vazio, loading, offline, drift, denied, approval/input e histórico; verifica texto visível e acessível em inglês.
- **TLANG-03:** matriz de CLI/API/MCP/WSS/Core captura sucesso e falhas de autenticação, validação, versão, capacidade, timeout e storage; mensagens próprias e corrective actions em inglês, códigos estáveis.
- **TLANG-04:** instalação dos wheels finais e frontend empacotado; repete a amostra de jornadas e confirma que conteúdo do usuário/histórico não foi traduzido nem re-hasheado.

**Saída:** todas as jornadas previstas têm entrada utilizável, feedback verdadeiro e textos próprios em US English. Não basta traduzir somente arquivos novos.

### M11 Recuperação revogação shutdown e limites

**Responsáveis:** três repositórios. **Cobertura:** NS14, CON-R4-01/08 e regressão completa CN5. **Dependência:** M08.

Recuperar journals, outbox, producers, claims, operações e decisões antes de admitir trabalho após restart. Invalidar caches, tickets, capabilities, lanes, leases e contexts quando a autoridade muda. Reconnect não toma uma sessão por mera coincidência de IDs. Consultar história mesmo sem binário.

Concluir shutdown com orçamento único, drain, `DRAINING_PENDING`, efeitos tardios e supervisão de recursos incertos. Se uma transferência de ownership for usada, prová-la no SO; exit code não substitui um supervisor vivo. Qualificar contenção/árvore de processos, PID reuse, sinais e autostart por plataforma.

**Testes:** kill do Server/daemon/provider nas fronteiras antes/depois de journal, envio e commit; reboot com operação unknown; partição prolongada; revogação online/offline; root/binary desaparecido; atraso de open depois do shutdown; lock de dados durante interrupt; journal bloqueado durante força; disco cheio e flood de eventos. As barreiras ficam ativas durante as asserções. Medir pico de memória, bytes/items de fila, journal, latência de controle e tempo de shutdown contra limites definidos em M00.

**Saída:** nenhum recurso próprio fica sem owner conhecido, nenhum processo alheio é encerrado, nenhuma incerteza é promovida a sucesso, e todas as filas/caches têm limites verificáveis.

### M12 Migração cutover e remoção de duplicação

**Responsáveis:** Nexus e Connector, com compatibilidade Core. **Cobertura:** NS15. **Dependências:** M09, M10 e M11.

Executar M0–M6 do plano de dados: backup/restauração, expansão aditiva, tradução de catálogo, endpoints/workspaces, sessões em curso, troca de owner, remoção de MCP stdio/duplicação e verificação/rollback. Manter checkpoints e mapas de IDs recuperáveis; preservar negações, identidade, histórico e hashes antigos.

Drenar o owner legado antes de atribuir recursos ao novo. Remover loaders, codecs e caminhos de efeitos duplicados somente após a prova de paridade. Migrar configurações selecionadas com diff, backup e CAS. Produzir runbooks para upgrade, downgrade compatível, restauração conjunta de banco/journal e retomada pendente; não reintroduzir MCP stdio como rollback.

**Testes:** banco novo e cópias legadas representativas, volume, interrupção em cada checkpoint, duas execuções da migração, journal pendente, sessão viva/unknown, migração concorrente, restore e rollback. Rodar regressões completas e auditoria de imports/dependências após a remoção.

**Saída:** instalação existente atualizável sem reset e com plano de recuperação executado em laboratório.

### M13 Artefatos finais e aceite completo

**Responsáveis:** três repositórios. **Cobertura:** NS16, CORE-R4-04 e revalidação de todo o escopo. **Dependência:** M12.

Congelar o conjunto de três commits e construir wheels/sdists imutáveis. Cada consumidor recebe o mesmo wheel Core pelo hash. Executar testes de contratos instalados, regressões, UI, CLI, processos, providers e hosts descritos abaixo. Corrigir o pipeline do Connector e disponibilizar execução reproduzível para Nexus; hosted CI depende da configuração real do projeto, não de presumir que um workflow desabilitado rodou.

Nenhum teste de aceite pode depender de `sys.path` apontando para clone irmão, monkeypatch de prontidão, bind/operação semeada para evitar a jornada, ou fake provider sendo contado como provider real. Essas técnicas continuam úteis em unit/contract com sua classificação correta.

**Saída:** G1 local, G2 remoto e G3 escopo completo sustentados por artefatos exatos, evidências e restrições normativas. Entregar hashes, release tuple, relatório de testes, matriz provider/SO, migrações, runbooks, notas de incompatibilidade, checklist de idioma e mapa requisito → código → teste → execução. Commits/pushes na branch estão autorizados; publicação em PyPI, deployment e uso de contas de produção não são consequência automática deste plano.

## Campanhas de teste e ambientes

### Campanhas obrigatórias por entrega

Cada campanha tem um responsável por consolidar a evidência; os três
repositórios corrigem suas falhas. Os IDs abaixo organizam execuções, sem
substituir os IDs normativos TR4/TN/J/TLANG.

| Campanha | Responsável | Execução e momento | Critério de aprovação |
|---|---|---|---|
| C01 — contrato e pacote | Core | A cada alteração contratual; repetir M13 em venv novo | Mesmos bytes Core nos consumidores; APIs públicas, schemas, recursos, sete ações e histórico R3; rejeição antes do efeito |
| C02 — onboarding e admissão | Nexus | M02–M04; repetir caminhos afetados e M13 | Entradas públicas, consentimento, replay/CAS, outbox atômica, ID original após resposta perdida |
| C03 — local puro | Nexus | P5; governança em M08/M09; repetir M13 | Serve instalado sem Connector e sem WSS local; todas as ações aplicáveis, eventos, ferramentas e recuperação |
| C04 — remoto automático | Connector | P6/P7; governança em M08/M09; repetir M13 | Registro persistido → boot → lane reconciliada → lease → efeito; A/B/C independentes no aceite final |
| C05 — domínio e decisões | Nexus | M08/M09; repetir M13 | Aprovação/input únicos, disputa MCP/Pi, consumo exclusivo, causalidade, tools-only e canais independentes |
| C06 — interface e idioma | Nexus + Connector | M10 e frontend de M13 | Browser/CLI reais, sucesso e erro, acessibilidade dos textos, TLANG-01–04 e recursos do wheel |
| C07 — falhas e atualização | Três repos | M11/M12; repetir provas afetadas em M13 | Crash/partição/saturação, autoridade e ownership preservados, upgrade/restore/rollback sem perda |
| C08 — aceite integral | Três repos | M13 sobre commits e artefatos congelados | Regressões completas, matriz real de provider/SO/topologia, todos os casos aplicáveis aprovados e G0–G3 fechados |

Se um teste falhar, registrar o defeito com requisito, reprodução, owner,
milestone e impacto. Corrigir e reexecutar a campanha afetada; preservar a
tentativa que falhou. Após congelar os artefatos, qualquer mudança de código,
dependência ou asset cria um novo conjunto de artefatos e invalida as provas
afetadas. O relatório final deve identificar quais execuções pertencem
exatamente ao conjunto entregue.

### Preparação obrigatória do laboratório em M00

| Recurso | Responsável | Como comprovar disponibilidade | Estado nesta revisão |
|---|---|---|---|
| Windows e Linux, Python 3.11/3.12/3.13 | Três repositórios | Instalação limpa, coleta/regressão e relatório por combinação | Matriz completa ainda não verificada |
| Servers A/C e executor B independentes | Nexus + Connector | Identidade de host, isolamento de disco, TLS, rede outbound e dois Servers ativos | Aceite entre hosts pendente |
| Codex, Pi e Claude com contas de laboratório | Core + hosts | Binário/build/fingerprint, autenticação e capacidade exercitada por modo/SO | Qualificação final pendente |
| Navegador e frontend empacotado | Nexus | Runner reproduzível, fluxo real e correspondência assets–wheel | Infraestrutura/aceite pendentes |
| Bases e journals legados de laboratório | Nexus + Connector | Backup consistente, migração interrompida e restauração ensaiada | Campanha final pendente |
| Destino de logs e artefatos de teste | Três repositórios | Manifest com hashes, redaction e correlação de operações por host | Consolidar em M00 |

Disponibilidade é registrada sem incluir segredos nos relatórios. Para cada recurso ausente, registrar responsável, ação de preparação e quais cenários dependem dele; continuar os trabalhos independentes. WSL ou um peer sintético não encerram a célula de hosts independentes ou de provider real.

| Camada | Ambiente e prova exigida |
|---|---|
| Documento | Validador R4 original e validador deste plano; cobertura e grafo, sem alegação de produto. |
| Unit e contrato | Clock controlado, peers estritos, fault barriers, schemas e hashes; todos os inputs inválidos relevantes antes do efeito. |
| Core real com peer técnico | Core instalado, journal/ledger reais e processos de laboratório; não conta como provider. |
| Integração entre aplicativos | Entradas HTTP/WSS reais, autenticação real, daemon e dispatcher; capturar causalidade e IDs. |
| Processo e SO | Subprocessos, restart/crash, sinais, autostart, locks, contenção e ownership nos sistemas efetivamente testados. |
| UI e CLI | Navegador contra aplicativo instalado; comandos humanos/headless, vault, cancelamento, reconnect e assets do wheel. |
| Provider local | Nexus + Core sem Connector importável/instalado; binário e conta de laboratório reais, versão/fingerprint registrados. |
| Provider remoto | Server A e Connector B em hosts distintos, rede real, mesmo Core; Server sem binários e paths de B. |
| Qualificação completa | Matriz de builds/SOs/modos e 164 cenários aplicáveis reavaliados no conjunto final, mais os quatro de idioma. |

A matriz mínima de plataforma automatizada deve preservar Windows e Linux e Python 3.11, 3.12 e 3.13, já declarados nos projetos/CI. Isso não implica repetir toda chamada paga de provider em cada versão Python: regressões e pacote rodam em todas; a campanha nativa usa combinações explicitamente registradas e amplia quando houver dependência de plataforma/Python. macOS ou outro sistema anunciado como suportado entra como célula própria antes dessa promessa de release.

Para providers, cada linha registra adapter, modo, versão/build, fingerprint, SO/arquitetura, contenção, autenticação, targeting e capacidades efetivamente exercitadas. Managed: Codex, Pi e Claude. Attach: trilha própria para descoberta/alvo explícito, evidência de processo/socket/UID quando aplicável, não propriedade do processo externo, controles e limitações reais. Uma capacidade ausente no provider deve ser recusada corretamente; não simulada como sucesso.

A matriz de providers abaixo inicia com aceite final `NOT_RUN`. M00 deve preencher versão/build, arquitetura e credencial de laboratório por linha; não usar “latest” como versão de evidência. Cada célula local/remota exige o ciclo aplicável, decisões/input, ferramentas, histórico e recuperação; capacidades indisponíveis exigem recusa comprovada.

| Adapter/modo | Sistema do executor | Nexus local | Connector remoto | Fechamento |
|---|---|---|---|---|
| Codex app-server / managed | Windows | NOT_RUN | NOT_RUN | M13 |
| Codex app-server / managed | Linux | NOT_RUN | NOT_RUN | M13 |
| Pi RPC / managed | Windows | NOT_RUN | NOT_RUN | M13 |
| Pi RPC / managed | Linux | NOT_RUN | NOT_RUN | M13 |
| Claude stream / managed | Windows | NOT_RUN | NOT_RUN | M13 |
| Claude stream / managed | Linux | NOT_RUN | NOT_RUN | M13 |
| Claude attach | Cada SO compatível fixado em M00 | NOT_RUN | NOT_RUN | Trilha própria de qualificação; onde não qualificado, executar o teste de indisponibilidade e conservar a restrição normativa |

Uma linha acima não declara suporte já obtido. A restrição normativa de attach deve ser mantida até qualificação explícita; não transformar ausência de laboratório numa exclusão de capacidade managed exigida.

Topologias de aceite:

1. **Local puro:** Nexus + Core instalados num ambiente sem aplicativo Connector; ciclo e ferramentas diretas.
2. **Remoto heterogêneo:** Server Linux A sem providers, Connector Windows B com pasta inacessível a A; repetir a execução no host Linux para os adapters/SOs prometidos.
3. **Isolamento:** Connector B ligado a Servers A e C, dois agentes por Server, IDs locais coincidentes e revogação de apenas um vínculo.
4. **Rede outbound:** firewall do executor bloqueia ingresso; WSS/HTTPS partem de B; falhar separadamente controle e ferramentas.
5. **Migração:** cópia legada preservada, operação pendente e owner vivo; upgrade, crash, retomada e restore verificados.

As 34 condições J continuam obrigatórias nos destinos mapeados. Essas topologias organizam a campanha, sem substituir casos de consumo, HITL, unknown, eventos, saturação e drift.

### Limites e carga que precisam de prova

Aplicar os defaults do [plano de dados, seção 9](../03_DADOS_MIGRACAO_E_RECUPERACAO.md), sujeitos à qualificação de carga prevista ali:

| Recurso | Baseline e asserção |
|---|---|
| Wire e payload | Frame 1 MiB; chunk/operação inline 64 KiB; request/input nativo 16 KiB; rejeitar excesso antes do efeito |
| Admissão | 32 pendentes produtivos por executor; oito controles e orçamento próprio de bytes; reservar antes de criar tasks |
| Runtime/journal | Oito slots por instalação por default; journal lógico 256 MiB com reserva crítica de 16 MiB |
| Inventário/reconcile | 128 instalações por snapshot inicial; até 256 IDs por reconcile; páginas de claims/slots default 128 e máximo 4096 |
| Canal e autoridade | Heartbeat 15 s, ausência 45 s; lease até 120 s/renovação 30 s; ticket até 600 s, renovação em 70% com jitter |
| Cache/recovery | Até 4096 chaves positivas, TTL máximo 60 s com invalidação de epoch; backoff 0,5–30 s e uma task por obrigação/stream |

M00 registra configuração, máquina e orçamento em bytes das filas, tempo total de shutdown e percentis de latência; M11 mede sob pressão e falha. Não anunciar capacidade além da medida. Os cenários incluem 100 mil agentes com lookup indexado, sem presumir 100 mil runtimes; nenhum timeout transforma resultado desconhecido em retry autorizado.

## Riscos de entrega e ação de resolução

| Risco observado | Responsável / marco | Ação e evidência exigida |
|---|---|---|
| Contrato válido sem integração de produto | Core + consumidores / M01–M06 | Conformance instalada e ciclo real separado, sem forçar flags de prontidão |
| Dependência circular entre open e lease | Nexus + hosts / M04–M06 | Bootstrap `OPEN_AUTHORIZED_PENDING_LEASE`, instalação antes de prepare/open e teste de zero efeito antecipado |
| Dupla execução após timeout, notificação ou restart | Três repos / M04, M07, M08, M11 | Outbox/producer owned, IDs duráveis, contagem de efeitos e recuperação do mesmo resultado |
| Prova parcial tratada como aceite | Três repos / todos | Registrar camada, dirty state, skips e sobreposição; retestar o conjunto final imutável em M13 |
| Regressões legadas e grant com expiry ISO-offset inválido | Nexus / M02, M09, M12 | Reproduzir, corrigir validação/contrato e adicionar regressão; entrada inválida não deve produzir INTERNAL_ERROR |
| Empacotamento contaminado por clone/artefato antigo | Três repos / M13 | Build limpo, cwd externo, `python -I`, hashes de recursos; executar regressão final após correções |
| Laboratório/provider indisponível | Três repos / M00, M13 | Preparar Windows/Linux e A/B/C cedo; manter o caso pendente até execução na topologia exigida |
| Cutover deixa recurso sem owner ou perde histórico | Nexus + Connector / M11–M12 | Drain, checkpoints, backup e restore conjunto; falhar durante cada fronteira e confirmar retomada |

## Execução reproduzível e evidência

Os comandos abaixo distinguem os existentes dos que precisam ser criados. Executar a partir da raiz indicada, com ambiente de laboratório e o wheel Core fixado. Neste workspace, comandos de shell usam `rtk`.

| Repositório | Comando ou trabalho necessário |
|---|---|
| Nexus, documental | `rtk proxy python -X utf8 plans/validar_pacote.py` e `rtk proxy python -X utf8 plans/r4_execution/validate_delivery_plan.py --write-report` |
| Nexus, ambiente atual | `rtk proxy uv sync --extra serve-lite --extra dev --frozen --find-links vendor/wheels` |
| Nexus, dirigido | `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests/execution_r4 -q` no Windows; usar o interpretador do venv equivalente em Linux. Cenários ausentes devem ser implementados e coletados primeiro. |
| Nexus, regressão | `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests -q`; classificar falhas preexistentes e skips por causa, sem removê-los para obter verde. |
| Core | `rtk proxy python -m pytest tests -q`, `rtk proxy python contracts/generate.py --check`, `rtk proxy python contracts/generate_r4.py --check`, `rtk proxy python tools/build_artifacts.py`, verificadores de wheel e instalação offline existentes. O check R4 já existe; completar a conformance sem confundir geração válida com execução qualificada. |
| Connector | `rtk proxy python -m pytest tests -q` após instalação do mesmo Core e extra `test`; corrigir workflow, paths de artefato e pins antigos. |
| Frontend | `rtk proxy npm ci` e `rtk proxy npm run build` existentes; criar scripts de teste de componentes e navegador, fixar dependências e registrar comandos no catálogo M00. Não presumir que `npm test` existe. |
| Instalação final | Criar runners que instalem wheels em venvs novos e executem fora dos clones, com `python -I`, sem editable install/PYTHONPATH. Verificar também assets, SQL, schemas, extensão Pi e dependências offline declaradas. |
| Conjunto distribuído | Criar orquestrador da campanha A/B/C com configuração redigida, health/readiness explícitos, timeouts, fault injection e coleta de evidência por host. |

Cada execução guarda: run ID, requisito/teste/nodeid, camada, repo/commit e dirty state, versão/SHA dos artefatos instalados, Python/SO/arquitetura, provider/build quando houver, topologia, comando exato, início/fim, exit code, coleta/passed/failed/skipped, motivo de skip, hashes dos logs redigidos e IDs de operações/decisões/eventos. Evidência visual de UI complementa as asserções; não substitui estado persistido.

Estados de teste: `NOT_RUN`, `RUNNING`, `PASS`, `FAIL`, `BLOCKED_EXTERNAL` e `NOT_APPLICABLE` justificado. `SKIP` não é PASS. Ausência de host/credencial é `NOT_RUN`/`BLOCKED_EXTERNAL`. Uma exclusão normativa é acompanhada do motivo e teste de recusa. Não somar reexecuções, testes parametrizados e suites sobrepostas para inflar cobertura. O relatório distingue conjunto coletado, casos únicos e execuções.

Estados de tarefa: `PENDING`, `IN_PROGRESS`, `READY_FOR_ACCEPTANCE`, `DONE`, `BLOCKED_EXTERNAL`. Para `DONE`, exigir código pelo caller real, teste positivo e negativo, instalação aplicável, migração/recuperação quando persistente, textos US English, evidência rastreável e commit/push. Um commit com helper ou um teste parcial não fecha automaticamente a tarefa.

## Sequência operacional e gates de conclusão

A ordem inicial é M00 → M01 → M02 → M03 → M04. Depois, M05 e M06 podem avançar como frentes independentes; M07 segue M06; M08 une local/remoto/eventos. M09, M10 e M11 concluem domínio, jornadas e robustez. M12 faz o cutover e M13 aceita os artefatos finais. Isso descreve independência técnica; não pressupõe agentes paralelos nem divide ownership sem coordenação.

Os próximos incrementos devem incorporar a evidência existente à auditoria, integrar o incremento Pi publicado e concluir as lacunas de contrato, configuração/segredos e composição automática local/remota. O fechamento respeita a ordem de auditoria, contrato, autoridade/onboarding e dispatcher. Essa ordem evita acumular novos previews de UI/WSS sem integrar os callers que produzem efeitos.

| Gate | Condição de encerramento |
|---|---|
| G0 | Baseline, rastreabilidade, contrato Core de desenvolvimento executável, consumidores compatíveis, migrações e autoridade da fundação verificados em M02. Não anuncia provider. |
| G1 | Ciclo local instalado sem Connector, com controles, decisões, ferramentas, eventos, recuperação, migração e testes negativos no conjunto final. |
| G2 | Mesmo ciclo pelo Server e Connector reais em hosts separados, com mesmo Core, daemon, lease, reconciliação e falhas de rede. |
| G3 | Todos os requisitos e casos aplicáveis, versões/SOs/providers declarados, CN5, idioma, regressões, pacote e runbooks aceitos. |

Marcos intermediários podem demonstrar G1/G2 antecipadamente, mas M13 reexecuta as provas dependentes dos artefatos finais. Não declarar entrega total com requisito obrigatório `PENDING`, teste necessário `NOT_RUN`, provider coberto apenas por fake, prontidão forçada ou decisão aplicada por dois caminhos. Alterações de escopo precisam ser explícitas e rastreáveis.

Manter commits coerentes, testados e com push em `feature/v0.2.0` de cada repositório alterado. Alteração do Core produz primeiro artefato/hash, depois pins/locks nos consumidores e evidência integrada. Registrar o conjunto dos três SHAs a cada marco conjunto. Publicar progresso parcial com esse nome e fechar o marco somente após seus aceites.

O calendário depende da auditoria M00, das regressões encontradas e da disponibilidade de hosts/providers. Não há prazo de conclusão comprovado nesta baseline. Após M00, estimar cada pacote restante, reservar capacidade para correções dos testes de falha e atualizar a previsão a cada marco; a ordem e os critérios acima já permitem iniciar o trabalho sem depender de uma estimativa fictícia.

## Entrega final verificável

### Checklist de fechamento por milestone

Cada milestone deve produzir um registro único com:

1. Requisitos NS/CORE/CON, cenários TR4/TN/J/TLANG e rotas/ações atendidos, com links para caller público e implementação.
2. Resultado dos testes positivos, negativos, recuperação e compatibilidade exigidos pelo marco; skips e casos não executados com causa explícita.
3. Conjunto dos commits dos três repositórios, hash do Core usado, versões/pins/locks, ambiente e comandos reproduzíveis.
4. Mudanças de schema/configuração e evidência de upgrade/rollback, quando aplicável; mensagens próprias em US English.
5. Defeitos restantes com destino e impacto no aceite. Defeito que viola critério do próprio marco impede `DONE`.
6. Commit/push dos incrementos, revisão do relatório e atualização do status. Se houver novo código após o teste, reexecutar as provas afetadas antes de fechar.

M13 consolida esses registros em um manifesto final e repete as campanhas sobre os artefatos congelados. Uma melhoria em um dos produtos só é aceita como integração quando os consumidores correspondentes foram exercitados.

Entregar os três repositórios coerentes na branch autorizada, o conjunto de commits e artefatos imutáveis, mesmo hash Core nos consumidores, migrações e rollback demonstrados, matriz completa de testes e capacidades, UI/CLI utilizáveis, textos próprios US English, runbooks e restrições técnicas explícitas. O relatório final deve permitir partir de qualquer requisito e encontrar sua implementação, entrada pública, cenário, execução e artefato.

O validador deste plano comprova somente cobertura documental. A conclusão do produto requer as campanhas descritas e o encerramento dos gates com evidência de execução.
