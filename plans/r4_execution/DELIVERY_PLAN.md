# Plano de entrega completa do Nexus Connector e Core

Este plano organiza a conclusão dos três produtos na branch `feature/v0.2.0`, com implementação, integração, testes, migração e aceite final. O resultado exigido é utilizar os harnesses diretamente no Nexus e remotamente pelo Connector, pelas entradas reais de UI, CLI e API, com o mesmo Core instalado. Todos os textos produzidos pelas aplicações devem estar em inglês dos Estados Unidos, inclusive superfícies legadas e mensagens de retorno.

Data da baseline: 29 de setembro de 2026. Este documento é um plano de conclusão; sua validação documental não executa testes de produto nem encerra gates de release. O trabalho anterior é aproveitado como implementação parcial a verificar.

## Fontes e cobertura obrigatória

A ordem normativa continua sendo [arquitetura R4](../01_ARQUITETURA_E_PLANO_MESTRE.md), [contratos](../02_CONTRATOS_HTTP_NXL_E_ESTADOS.md), [dados e migração](../03_DADOS_MIGRACAO_E_RECUPERACAO.md), [backlog](../04_BACKLOG_EXECUCAO.md), [testes e aceite](../05_TESTES_E_ACEITE.md) e [handoff Core e Connector](../06_HANDOFF_CORE_CONNECTOR.md). Este documento organiza a execução e acrescenta o requisito de idioma; não reduz requisitos nem cria uma autoridade de contrato concorrente.

A cobertura inclui as 85 tarefas NS00–NS16, os 164 cenários originais (85 TR4, 45 TN e 34 J), as quatro entregas CORE-R4, as oito entregas CON-R4, os quatro achados CN5, as 23 rotas HTTP/WSS e os sete verbos de operação. Acrescenta quatro cenários de idioma. O mapeamento completo é verificável em [delivery_plan.json](delivery_plan.json) e [delivery_coverage.json](delivery_coverage.json).

Cada tarefa mantém seus critérios e dependências originais. O marco indica quando ela deve ser encerrada, não quando é permitido começar um protótipo. Dentro do mesmo marco, vale o grafo do backlog. Um componente necessário a um marco posterior pode receber contratos e fixtures antes, sem declarar a integração pronta.

## Resultado de produto esperado

O operador seleciona um agente existente, o executor local ou remoto, uma instalação descoberta pelo Core e um workspace aprovado. A proposta mostra o consentimento necessário. Após aplicação, o vínculo é reutilizável. Iniciar, enviar um turno, controlar, aprovar, fornecer input, observar e encerrar passam pela admissão canônica do Nexus, que cria a operação durável e a despacha uma única vez.

O Nexus executa localmente com o Core dentro do owner de `serve`, sem instalar o aplicativo Connector. Remotamente, um daemon Connector inicia o WSS para o Server, resolve referências no próprio host, instala a autoridade concedida e chama o mesmo Core. O Server remoto funciona sem binários ou acesso ao filesystem do executor.

MCP permanece HTTP direto no Nexus. Conversas tools-only funcionam sem daemon. A bridge nativa do Pi usa os casos de uso canônicos com capacidade limitada. Aprovações, trabalho, consumo exclusivo, causalidade, histórico e política existentes continuam preservados.

Codex app-server, Pi RPC e Claude stream devem ser qualificados por build e sistema operacional nas modalidades local e remota. Claude attach mantém uma trilha explícita de qualificação nos sistemas compatíveis; presença no catálogo não permite execução. Uma capacidade excluída normativamente precisa aparecer indisponível e ter teste negativo. Falta de ambiente, credencial ou implementação de uma capacidade exigida mantém a entrega incompleta; não permite remover a linha da matriz.

Continuam fora do escopo normativo: novo login de usuário Nexus, SSO, tenant obrigatório, A2A completo, sincronização de checkouts, instalação automática de providers, orquestração cloud, HA multiwriter, migração major do SDK MCP e reescrita dos protocolos nativos.

## Baseline e lacunas que orientam a sequência

| Repositório | HEAD de referência | Pacote observado |
|---|---|---|
| Nexus | `2ce437d5189f0fdf08b1332e836249b2a838dbf3` | `0.2.0` |
| Connector | `208a9c90e14e4995951c805ccc6585596160ca1c` | `0.5.0.dev0` |
| Core | `79a315ff634bcfc8e5c4d4bab95ab46eff4579c8` | `0.2.22.dev0` |

Wheel Core corrente: SHA-256 `a909fab422f506c9631ef1ed57cea4ec09d235bc44f9e92ab1f84b4e289e02db`. A versão do pacote não equivale à revisão do wire. O contrato histórico R3 continua separado do preview R4.

O [status de implementação](IMPLEMENTATION_STATUS.md) registra inventário, identidade, tickets, realizações, prepare/apply, resolução, admissão, reservas, receipts, adapter embedded e negociação WSS parciais. Há ensaios de Core com peer nativo sintético e testes verticais em processo. As seguintes lacunas continuam determinantes:

| Área | Lacuna de entrega |
|---|---|
| Core R4 | `R4_BUNDLE_EXECUTABLE=False`; completar e qualificar contrato, reducers, targeting e aplicação de autoridade antes de anunciá-lo executável. |
| Execução local | O adapter embedded ainda recebe seleção/contexto das fixtures; faltam composição canônica, dispatcher de produto, ambiente por abertura e integração da jornada. |
| Execução remota | O cliente `wss_r4.py` negocia, mas não integra o daemon/StateStore, o ciclo de tickets, lanes, leases e o dispatcher de efeitos. |
| Reconciliação | O Server apenas promove o caso vazio confirmado; faltam páginas, merge de receipts/claims/watermarks, ownership e readiness por sessão. |
| Governança | Completar operador versus agente, capability de sessão, decisões, inputs, native-actions, eventos e consumo exclusivo nos novos caminhos. |
| Organização | Extrair SQL e transições do handler WSS para casos de uso e repositórios, conforme as fronteiras normativas. |
| Testes | Finalizar os casos ausentes e substituir, nos testes de aceite, semeadura de operações e readiness simulada por entradas públicas reais. |
| CI e UI | O workflow do Connector contém `if: false` e referência antiga ao Core; o `frontend/package.json` não declara testes de UI. Criar uma campanha reproduzível local antes de depender de hosted runners. |
| Idioma | Novas mensagens foram escritas em inglês; a auditoria de todo o conteúdo das três aplicações ainda é necessária. |

G0, G1, G2 e G3 continuam abertos nesta baseline. Resultados anteriores não serão somados como se fossem execução dos artefatos finais. Esta leitura identifica lacunas estáticas e evidências registradas; não substitui uma nova execução de regressões.

O Nexus contém alterações prévias do usuário: 599 exclusões em `plans/`, três assets HTTP modificados, uma evidência modificada e um diretório de teste não rastreado. O Core contém o arquivo não rastreado `=1`. Preservar esses itens, trabalhar com staging por caminhos explícitos e não executar reset/clean. Builds de frontend devem usar staging isolado até comparar os assets existentes.

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

Separar defeitos de código de dependências de laboratório. Um Core incompleto ou daemon sem integração é trabalho interno, não bloqueio externo. Uma máquina Linux ou credencial de provider ausente é requisito de ambiente a provisionar. Definir limites de payload, fila, journal, tempo de shutdown e métricas de latência a partir do contrato e da baseline medida antes da campanha de carga.

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

Ligar UI, CLI Nexus, CLI Connector, REST e entradas do domínio à mesma admissão. O Connector persiste a intenção antes do POST e consulta o resultado; não chama Core em paralelo ao pedido canônico. Preservar consumo exclusivo, delivery/inbox/handoff, actor/subject, causalidade e claims de sessão. Uma abertura seguida de prompt são duas operações correlacionadas.

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

Topologias de aceite:

1. **Local puro:** Nexus + Core instalados num ambiente sem aplicativo Connector; ciclo e ferramentas diretas.
2. **Remoto heterogêneo:** Server Linux A sem providers, Connector Windows B com pasta inacessível a A; repetir a execução no host Linux para os adapters/SOs prometidos.
3. **Isolamento:** Connector B ligado a Servers A e C, dois agentes por Server, IDs locais coincidentes e revogação de apenas um vínculo.
4. **Rede outbound:** firewall do executor bloqueia ingresso; WSS/HTTPS partem de B; falhar separadamente controle e ferramentas.
5. **Migração:** cópia legada preservada, operação pendente e owner vivo; upgrade, crash, retomada e restore verificados.

As 34 condições J continuam obrigatórias nos destinos mapeados. Essas topologias organizam a campanha, sem substituir casos de consumo, HITL, unknown, eventos, saturação e drift.

## Execução reproduzível e evidência

Os comandos abaixo distinguem os existentes dos que precisam ser criados. Executar a partir da raiz indicada, com ambiente de laboratório e o wheel Core fixado. Neste workspace, comandos de shell usam `rtk`.

| Repositório | Comando ou trabalho necessário |
|---|---|
| Nexus, documental | `rtk proxy python -X utf8 plans/validar_pacote.py` e `rtk proxy python -X utf8 plans/r4_execution/validate_delivery_plan.py --write-report` |
| Nexus, ambiente atual | `rtk proxy uv sync --extra serve-lite --extra dev --frozen --find-links vendor/wheels` |
| Nexus, dirigido | `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests/execution_r4 -q` no Windows; usar o interpretador do venv equivalente em Linux. Cenários ausentes devem ser implementados e coletados primeiro. |
| Nexus, regressão | `rtk proxy .venv/Scripts/python.exe -X utf8 -m pytest tests -q`; classificar falhas preexistentes e skips por causa, sem removê-los para obter verde. |
| Core | `rtk proxy python -m pytest tests -q`, `rtk proxy python contracts/generate.py --check`, `rtk proxy python tools/build_artifacts.py`, verificadores de wheel e instalação offline existentes. Ampliar geração/check para cobrir R4 integralmente. |
| Connector | `rtk proxy python -m pytest tests -q` após instalação do mesmo Core e extra `test`; corrigir workflow, paths de artefato e pins antigos. |
| Frontend | `rtk proxy npm ci` e `rtk proxy npm run build` existentes; criar scripts de teste de componentes e navegador, fixar dependências e registrar comandos no catálogo M00. Não presumir que `npm test` existe. |
| Instalação final | Criar runners que instalem wheels em venvs novos e executem fora dos clones, com `python -I`, sem editable install/PYTHONPATH. Verificar também assets, SQL, schemas, extensão Pi e dependências offline declaradas. |
| Conjunto distribuído | Criar orquestrador da campanha A/B/C com configuração redigida, health/readiness explícitos, timeouts, fault injection e coleta de evidência por host. |

Cada execução guarda: run ID, requisito/teste/nodeid, camada, repo/commit e dirty state, versão/SHA dos artefatos instalados, Python/SO/arquitetura, provider/build quando houver, topologia, comando exato, início/fim, exit code, coleta/passed/failed/skipped, motivo de skip, hashes dos logs redigidos e IDs de operações/decisões/eventos. Evidência visual de UI complementa as asserções; não substitui estado persistido.

Estados de teste: `NOT_RUN`, `RUNNING`, `PASS`, `FAIL`, `BLOCKED_EXTERNAL` e `NOT_APPLICABLE` justificado. `SKIP` não é PASS. Ausência de host/credencial é `NOT_RUN`/`BLOCKED_EXTERNAL`. Uma exclusão normativa é acompanhada do motivo e teste de recusa. Não somar reexecuções, testes parametrizados e suites sobrepostas para inflar cobertura. O relatório distingue conjunto coletado, casos únicos e execuções.

Estados de tarefa: `PENDING`, `IN_PROGRESS`, `READY_FOR_ACCEPTANCE`, `DONE`, `BLOCKED_EXTERNAL`. Para `DONE`, exigir código pelo caller real, teste positivo e negativo, instalação aplicável, migração/recuperação quando persistente, textos US English, evidência rastreável e commit/push. Um commit com helper ou um teste parcial não fecha automaticamente a tarefa.

## Sequência operacional e gates de conclusão

A ordem inicial é M00 → M01 → M02 → M03 → M04. Depois, M05 e M06 podem avançar como frentes independentes; M07 segue M06; M08 une local/remoto/eventos. M09, M10 e M11 concluem domínio, jornadas e robustez. M12 faz o cutover e M13 aceita os artefatos finais. Isso descreve independência técnica; não pressupõe agentes paralelos nem divide ownership sem coordenação.

Os próximos incrementos devem fechar primeiro a auditoria de cobertura e o contrato compartilhado, depois concluir autoridade/onboarding e o loop canônico de dispatch. Essa ordem evita acumular novos previews de UI/WSS sem integrar os callers que produzem efeitos.

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

Entregar os três repositórios coerentes na branch autorizada, o conjunto de commits e artefatos imutáveis, mesmo hash Core nos consumidores, migrações e rollback demonstrados, matriz completa de testes e capacidades, UI/CLI utilizáveis, textos próprios US English, runbooks e restrições técnicas explícitas. O relatório final deve permitir partir de qualquer requisito e encontrar sua implementação, entrada pública, cenário, execução e artefato.

O validador deste plano comprova somente cobertura documental. A conclusão do produto requer as campanhas descritas e o encerramento dos gates com evidência de execução.
