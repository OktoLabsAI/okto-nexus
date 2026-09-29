# Backlog de implementação — NS00 a NS16

**Todas as tarefas estão PENDING.** Este é o backlog ativo do Server. A lista de comandos de teste nomeia arquivos/funções **a serem criados**, não afirma que já existem no repositório. Não executar uma tarefa como mero ajuste documental.

Cada tarefa tem arquivos/símbolos de partida, passos obrigatórios, atalho proibido e aceite observável. O executor deve abrir o arquivo real, preservar alterações, implementar os passos e registrar teste, commit/diff e evidência. Quando um artefato do Core/Connector estiver bloqueado, desenvolver código independente com fixtures; o gate de efeito real permanece BLOCKED_EXTERNAL. Não usar essa condição para copiar adapters ou fabricar grants.

Dependências entre fases são gates para concluir a fase; desenvolvimento de UI/contratos com fixtures pode começar em paralelo. Dentro da fase, executar na ordem indicada. Shared work CORE-R4/CON-R4 está em 06_HANDOFF_CORE_CONNECTOR.md e não deve ser implementado silenciosamente neste repo.


| Fase | Objetivo | Depende de |
|---|---|---|
| NS00 | Baseline, unificação e contrato executável | Nenhuma |
| NS01 | Bootstrap neutro e remoção correta de MCP stdio | NS00 |
| NS02 | Schema, identidades e extensões persistentes | NS01 |
| NS03 | Autenticação centrada no agente e credenciais derivadas | NS02 |
| NS04 | Catálogo, disponibilidade e snapshots por executor | NS02, NS03 |
| NS05 | Realização e bindings sem atrito recorrente | NS03, NS04 |
| NS06 | Intenções, admissão única e dispatcher | NS02, NS03, NS05 |
| NS07 | Executor local via Core público | NS03, NS05, NS06 |
| NS08 | Canal WSS R4 e lanes autenticadas | NS03, NS06 |
| NS09 | Abertura remota, lease e controle completo | NS05, NS06, NS08 |
| NS10 | Eventos duráveis, ACK e replay | NS06, NS08, NS09 |
| NS11 | Decisão canônica e aprovação nativa íntegra | NS06, NS07, NS09, NS10 |
| NS12 | Ferramentas diretas e governança de trabalho | NS03, NS06, NS07, NS11 |
| NS13 | Dashboard e CLI orientados por dados | NS04, NS05, NS06, NS11 |
| NS14 | Recuperação, revogação, shutdown e limites | NS07, NS08, NS09, NS10, NS11 |
| NS15 | Migração, cutover e eliminação de cópias | NS01, NS02, NS07, NS12, NS13, NS14 |
| NS16 | Artefatos, integração vertical e liberação | NS09, NS10, NS11, NS12, NS13, NS14, NS15 |

## NS00 — Baseline, unificação e contrato executável

**Arquivos/símbolos:** `pyproject.toml`; `01_PLANO_IMPLEMENTACAO.md e planos legados`; `plans/nexus-server-r4/`; `contratos do Core`.


### NS00.01 — Registrar branch, HEAD, fonte e capacidade realmente instalada

**Responsável:** Server. **Estado:** PENDING. **Dependências:** nenhuma.

**Implementação obrigatória:**

1. Confirmar feature/v0.2.0 e registrar git rev-parse HEAD, git status --short, Python, SO e lock de dependências.
2. Comparar com 7ed52c2 sem reset e guardar hashes dos arquivos antes de alterar.
3. Registrar versões/SHA reais do Core e Connector; separar CN5 como plano de correção pendente de prova.

**Não fazer:** Não usar main do Nexus ou assumir que 0.2.10 equivale a um wheel qualificado.

**Teste TR4-00-01 — preparação:** Clone de laboratório na branch e diretório com alteração não commitada. **Ação:** Gerar baseline e executar novamente sem editar código.

**Aceite obrigatório:** Mesmo HEAD e alteração local preservados; manifest distingue fonte, wheel e qualificação; nenhuma alteração destrutiva.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns00.py::test_ns00_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS00.02 — Encerrar planos concorrentes sem perder requisito

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS00.01.

**Implementação obrigatória:**

1. Instalar este pacote como backlog ativo.
2. Gerar crosswalk por N00.1–N13.5 e TN/J usando 07_RASTREABILIDADE_R3.md.
3. Marcar planos antigos superseded somente em metadados; manter arquivo/evidência legados.

**Não fazer:** Não apagar exigências de HTTP direto, consumo exclusivo, attach condicionado ou 100 mil identidades.

**Teste TR4-00-02 — preparação:** Planos R3, CN1–CN5 e arquivos de planejamento presentes. **Ação:** Validar crosswalk e procurar tarefas sem sucessor.

**Aceite obrigatório:** 70 tarefas originais e 79 cenários TN/J possuem destino; nenhuma tarefa está DONE só por estar descrita.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns00.py::test_ns00_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS00.03 — Fixar responsabilidades e interfaces R4 entre repositórios

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS00.02.

**Implementação obrigatória:**

1. Copiar decisões de 02_CONTRATOS_HTTP_NXL_E_ESTADOS.md para ADR R4.
2. Registrar Core como owner dos schemas/reducers, Server da admissão e Connector da execução remota.
3. Produzir fixtures de /v1 direto e erro tipado; registrar mudanças necessárias no cliente atual.

**Não fazer:** Não tratar HTTP bool de aprovação ou payload genérico r3 como autorização suficiente.

**Teste TR4-00-03 — preparação:** Peer de contrato sem provider; payloads válidos e respostas com envelope legado. **Ação:** Exercitar fixtures de protocolo e comparar representação.

**Aceite obrigatório:** Objetos /v1 diretos são aceitos; ok/data legado não é confundido; divergências produzem VERSION_INCOMPATIBLE antes de efeito.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns00.py::test_ns00_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS00.04 — Solicitar bundle Core R4 e preservar histórico r3

**Responsável:** Server + Core. **Estado:** PENDING. **Dependências:** NS00.03.

**Implementação obrigatória:**

1. Abrir entregas CORE-R4-01–CORE-R4-04 do handoff com schemas fechados.
2. Exigir novos ACKs de attach/reconcile, grant correlacionado e owner obrigatório conforme delta.
3. Importar o artefato no Server somente depois de conformance/hash; desenvolver demais fases com fixtures enquanto estiver pendente.

**Não fazer:** Não editar os JSONs embarcados do Core dentro do Server nem declarar R4 já publicado.

**Teste TR4-00-04 — preparação:** Bundle r3 fixado e fixtures-alvo R4. **Ação:** Validar rejeição cruzada e leitura histórica explícita.

**Aceite obrigatório:** R3 não executa efeitos R4; receipts históricos continuam interpretáveis; gate remoto permanece BLOCKED_EXTERNAL até artefato compartilhado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns00.py::test_ns00_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS00.05 — Construir harness de testes e limites de evidência

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS00.04.

**Implementação obrigatória:**

1. Criar peers Server/Connector e native de laboratório com barreiras causais.
2. Separar unit/contract, Core real, processo de SO, provider e dois hosts.
3. Testes de produto começam NOT_RUN; registrar versões, comandos e exit codes.

**Não fazer:** Não promover sentinela de spawn a prova de que provider funcionou.

**Teste TR4-00-05 — preparação:** Ambiente sem credenciais de providers. **Ação:** Rodar um controle de fixture e validar o manifesto de evidência.

**Aceite obrigatório:** Campanha pode passar em contrato sem marcar provider/multihost como PASS; segredos de laboratório identificados e isolados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns00.py::test_ns00_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS01 — Bootstrap neutro e remoção correta de MCP stdio

**Arquivos/símbolos:** `adapters/inbound/mcp/server.py`; `adapters/inbound/http/app.py`; `bootstrap/dependencies.py`; `adapters/inbound/cli/main.py`; `pyproject.toml`.


### NS01.01 — Extrair Deps e composição antes de remover transporte

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS00.05.

**Implementação obrigatória:**

1. Mover Deps, construção de repositórios e dependências compartilhadas para bootstrap/dependencies.py.
2. Mover registro de tools/resources/instructions para mcp/registration.py preservando nomes e schemas.
3. Alterar imports do HTTP/CLI para módulos neutros; evitar efeito colateral no import.

**Não fazer:** Não apagar mcp/server.py inteiro enquanto HTTP ainda importa seus símbolos.

**Teste TR4-01-01 — preparação:** Server atual com /mcp e REST saudável em fixture. **Ação:** Importar nova composição e comparar catálogo HTTP antes/depois.

**Aceite obrigatório:** HTTP mantém tools/resources e identidade; import não abre listener ou subprocesso; não há dependência do Connector.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns01.py::test_ns01_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS01.02 — Remover o ramo MCP stdio sem shim

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.01.

**Implementação obrigatória:**

1. Inventariar chamadas SDK de stdio, entrypoints e exemplos command/args Nexus.
2. Retirar transporte, branch de CLI e fallback; preservar protocolos nativos do Core.
3. Comando antigo falha com instrução HTTP ou ajuda, sem iniciar um servidor.

**Não fazer:** Não criar stdio→HTTP proxy nem instalar helper MCP local.

**Teste TR4-01-02 — preparação:** Configuração legada selecionada e captura de stdin/stdout/processos. **Ação:** Invocar comandos antigos e novas opções HTTP.

**Aceite obrigatório:** Nenhuma sessão MCP stdio nasce; serve continua HTTP; nenhum adaptador nativo é removido por usar stdin/stdout.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns01.py::test_ns01_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS01.03 — Definir CLI principal e extras de instalação

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.02.

**Implementação obrigatória:**

1. Apontar okto-nexus para módulo CLI neutro.
2. Preservar serve/serve-lite, comandos existentes e help; declarar Core nos extras de execução local.
3. Manter mcp>=1,<2 e funcionalidades de embedding sem mudança implícita.

**Não fazer:** Não incluir pacote Connector ou modelos pesados novos no serve-lite.

**Teste TR4-01-03 — preparação:** Wheel em ambiente limpo sem clone irmão. **Ação:** Executar help, serve-lite e import dos adaptadores.

**Aceite obrigatório:** CLI não inicia stdio sem argumentos; extras contêm o Core necessário e não exigem a aplicação Connector.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns01.py::test_ns01_03 -q`; camada `packaging`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS01.04 — Montar routers /v1 com autenticação específica

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.03.

**Implementação obrigatória:**

1. Adicionar connections_v1/runtime_v1 e link WSS na composição HTTP.
2. Preservar /api/v1 e envelope legado; resposta /v1 direta com revisão em header.
3. WebSocket valida ticket explicitamente, sem depender do middleware BaseHTTP ou da conveniência de operador loopback.

**Não fazer:** Não liberar WebSocket por ser loopback ou confiar em agent_id do corpo.

**Teste TR4-01-04 — preparação:** Requests HTTP e upgrade local/remoto com chaves/tickets inválidos. **Ação:** Consultar protocolo público, /me e fazer upgrades positivos/negativos.

**Aceite obrigatório:** Só protocolo público expõe dados não privados; endpoints escopados rejeitam credenciais de audiência errada antes do handler.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns01.py::test_ns01_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS01.05 — Migrar configuração MCP apenas selecionada

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.04.

**Implementação obrigatória:**

1. Gerar plano de diff para uma entrada Nexus stdio escolhida pelo operador.
2. Escrever HTTP direto com backup e CAS, sem buscar/rotacionar key.
3. Manter demais MCPs e guardar ownership dos campos migrados.

**Não fazer:** Não varrer home atrás de secrets ou converter todas as configurações do usuário.

**Teste TR4-01-05 — preparação:** Arquivo com duas entradas de terceiros e uma Nexus selecionada. **Ação:** Aplicar migração, repetir e simular edição concorrente.

**Aceite obrigatório:** Somente entrada selecionada muda; key/id intactos; concorrência recusa sem sobrescrever terceiros; stdio não retorna como rollback.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns01.py::test_ns01_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS02 — Schema, identidades e extensões persistentes

**Arquivos/símbolos:** `domain/execution/keys.py`; `adapters/outbound/sqlite/execution_*.py`; `migrations/`; `application/identity.py`; `agent_endpoints/runtime_profiles existentes`.


### NS02.01 — Definir chaves de escopo imutáveis

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.05.

**Implementação obrigatória:**

1. Implementar ExecutorKey/BindingKey/SessionKey/StreamKey/ApprovalKey da arquitetura.
2. Exigir chaves completas nas mutações internas e usar IDs curtos só no resolver humano inequívoco.
3. Tipar gerações/revisões separadamente; não truncar campos.

**Não fazer:** Não concatenar IDs em strings com separadores ambíguos.

**Teste TR4-02-01 — preparação:** Dois Servers/executores com mesmos binding/session/request IDs. **Ação:** Inserir, consultar e remover um namespace.

**Aceite obrigatório:** Nenhuma colisão ou remoção cruzada; UI pede escopo quando alias curto é ambíguo.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns02.py::test_ns02_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS02.02 — Criar extensões aditivas e índices

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.01.

**Implementação obrigatória:**

1. Aplicar tabelas/colunas do documento 03 com FKs para entidades existentes.
2. Reusar política de agent_endpoints/runtime_profiles sem flags duplicadas.
3. Criar índices de idempotência, outbox, subject/executor e stream antes do hot path.

**Não fazer:** Não duplicar inbox ou criar user/tenant para ownership.

**Teste TR4-02-02 — preparação:** Banco vazio e cópia legada consistente. **Ação:** Migrar, repetir e conferir constraints/índices.

**Aceite obrigatório:** Migrações idempotentes; dados legados e negações preservados; consulta indexada encontra escopo exato.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns02.py::test_ns02_02 -q`; camada `migration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS02.03 — Persistir identidade técnica local e remota

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.02.

**Implementação obrigatória:**

1. Criar server_id persistido e embedded_executor_id único pela migração.
2. Registrar connector_id remoto sob autenticação e retornar executor_id canônico.
3. Separar clone de estado de posse válida: generation CAS e reconciliação antes de efeito.

**Não fazer:** Não derivar identidade somente do hostname ou gerar executor diferente a cada restart.

**Teste TR4-02-03 — preparação:** Duas inicializações locais e dois pedidos idempotentes de registro remoto. **Ação:** Reabrir a base e repetir registro com mesma intenção.

**Aceite obrigatório:** IDs estáveis, nenhum Agent novo e nenhum takeover automático por clone de diretório.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns02.py::test_ns02_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS02.04 — Separar workspace lógico da realização física

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.03.

**Implementação obrigatória:**

1. Manter IDs legados baseados em path.
2. Acrescentar workspace_executor_binding com handle de root validado no executor.
3. Rotas remotas nunca chamam realpath/isdir/stat sobre handle/path de outro host.

**Não fazer:** Não mesclar por Git remote, nome ou igualdade textual de pasta.

**Teste TR4-02-04 — preparação:** Server Linux, fixture de realização Windows e duas pastas do mesmo repo. **Ação:** Preparar vínculos lógicos e tentar falsa equivalência.

**Aceite obrigatório:** Nenhuma resolução de filesystem remoto em A; associação depende de permissão e aprovação explícita; histórico não é re-hasheado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns02.py::test_ns02_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS02.05 — Implementar writers transacionais e readers de histórico

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.04.

**Implementação obrigatória:**

1. Criar repos para operações/outbox/receipts/ingresso/decisões conforme T1–T5.
2. Readers consultam namespace sem compor runtime.
3. Todas as transações são curtas e livres de chamadas nativas/rede.

**Não fazer:** Não usar SQL no router ou abrir transação durante await de provider.

**Teste TR4-02-05 — preparação:** Instrumentação da connection factory e peer que bloqueia I/O. **Ação:** Admitir operação e bloquear o dispatcher externo.

**Aceite obrigatório:** Commit termina antes do I/O; consultas continuam responsivas e reproduzem os registros por IDs exatos.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns02.py::test_ns02_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS03 — Autenticação centrada no agente e credenciais derivadas

**Arquivos/símbolos:** `application/auth.py`; `application/execution_leases.py`; `connections_v1.py`; `execution_link_tickets`; `execution_session_capabilities`.


### NS03.01 — Implementar /me pela autoridade já existente

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.05.

**Implementação obrigatória:**

1. Reusar AgentKeyAuthService.resolve e cache limitado.
2. Responder somente agente autenticado, server_id, permissões e revisões.
3. Conferir hint de agente em onboarding e recusar divergência sem listagem global.

**Não fazer:** Não criar outro resolvedor por Connector ou retornar todos os agentes.

**Teste TR4-03-01 — preparação:** 100 mil registros sintéticos com índice por key hash. **Ação:** Autenticar uma key e enviar hint de outro agente.

**Aceite obrigatório:** Lookup escopado/indexado; spoof recusado; nenhum cadastro ou rotação ocorre.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns03.py::test_ns03_01 -q`; camada `contract_scale`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS03.02 — Implementar proposta/aplicação com política herdada

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.01.

**Implementação obrigatória:**

1. Resolver sujeito e política atual; comparar revisões e diff.
2. Permitir self-bind só nas capacidades já autorizadas e exigir operador para escalada.
3. Apply usa CAS e auditoria ator/sujeito sem side effects de processo.

**Não fazer:** Não conceder método negado porque catálogo diz supported.

**Teste TR4-03-02 — preparação:** Agente com negação explícita e operador de fixture. **Ação:** Tentar self-escalation e depois aprovação autorizada.

**Aceite obrigatório:** Agente não autoaprova; operador aplica uma revisão; repetição retorna a mesma proposta aplicada sem gerar outra identidade.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns03.py::test_ns03_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS03.03 — Emitir tickets escopados e revogáveis

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.02.

**Implementação obrigatória:**

1. Persistir hash, audiência, scopes, epochs, validade e conexão de consumo.
2. Bootstrap permite só fatos técnicos daquele executor; binding ticket permite só sua lane.
3. Rotação invalida derivados e emissão velha; renovação legítima é idempotente por intenção.

**Não fazer:** Não emitir chave raiz de Connector nem usar ticket de A para B.

**Teste TR4-03-03 — preparação:** Dois bindings/agentes, dois executores e relógio controlado. **Ação:** Reusar ticket em outro alvo, expirar e rotacionar key.

**Aceite obrigatório:** Alvo/audiência/epoch incorretos recusados; outro agente permanece operacional; novo ticket não revive key revogada.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns03.py::test_ns03_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS03.04 — Implementar capability MCP de sessão com audiência própria

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.03.

**Implementação obrigatória:**

1. Emitir segredo uma vez/no-store para sessão reservada autorizada.
2. Guard HTTP resolve capability para mesmo agente e limita casos de uso, workspace, owner e lease.
3. Renovar validade canônica sem presumir hot reload; tokens NXL/EPT não são MCP.

**Não fazer:** Não entregar key administrativa/canônica ao runtime como fallback.

**Teste TR4-03-04 — preparação:** Harness HTTP de laboratório com token de sessão e ticket NXL. **Ação:** Chamar tool permitida, proibida e depois revogar sessão.

**Aceite obrigatório:** Só ações permitidas têm efeito; ticket errado falha; revogação bloqueia MCP sem depender de proxy Connector.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns03.py::test_ns03_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS03.05 — Gerar comando protegido e não recuperar hash como segredo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.04.

**Implementação obrigatória:**

1. UI gera comando connect com URL e hint; chave entra por stdin/entrada mascarada no Connector.
2. Preservar chave já usada pelo MCP; só rotação explícita usa issue_key.
3. Validar shell quoting e origem antes de transmitir credencial.

**Não fazer:** Não colocar segredo em argv, copiar hash como key ou girar key para montar snippet.

**Teste TR4-03-05 — preparação:** Agente hash-only e captura de issue_key/argv. **Ação:** Gerar comando em Bash e PowerShell e usar key existente.

**Aceite obrigatório:** Comando sem segredo de longa duração; nenhuma chamada de emissão; MCP anterior continua autenticando o mesmo agente.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns03.py::test_ns03_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS04 — Catálogo, disponibilidade e snapshots por executor

**Arquivos/símbolos:** `application/executor_inventory.py`; `adapters/outbound/execution/embedded.py`; `runtime_v1.py`; `Core catalog/availability/installation APIs`.


### NS04.01 — Consumir catálogo sem compor runtime falso

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.05, NS03.05.

**Implementação obrigatória:**

1. Usar get_runtime_catalog como consulta síncrona de metadados.
2. Expor nomes/IDs/modos/suporte sem classes ou módulos.
3. Server sem binário inicia APIs normalmente e mostra inventário local vazio/inconclusivo.

**Não fazer:** Não chamar create_runtime com candidato inventado nem manter lista de IDs em frontend.

**Teste TR4-04-01 — preparação:** Ambiente sem harnesses e Core instalado. **Ação:** Consultar catálogo antes de iniciar journal/runtime.

**Aceite obrigatório:** Catálogo vem do Core sem spawn/porta/credencial; attach continua registrado não qualificado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns04.py::test_ns04_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS04.02 — Preservar candidatos e avaliar no host correto

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS04.01.

**Implementação obrigatória:**

1. Adapter local usa discovery público e conserva todos os campos InstallationCandidate.
2. Avaliar pelo Core no executor; nunca refazer qualified_build no Server remoto.
3. Disponibilidade insuficiente permanece NOT_PROBED/PREPARATION_REQUIRED.

**Não fazer:** Não reduzir Pi a Node nem preencher arquitetura/version por suposição.

**Teste TR4-04-02 — preparação:** Par Node/CLI de laboratório e duas versões da mesma família. **Ação:** Discovery → avaliação → serialização.

**Aceite obrigatório:** Refs/build/version/architecture preservados; avaliação remota utiliza host remoto; nenhum provider é iniciado para listar.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns04.py::test_ns04_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS04.03 — Gerar e ingressar revisão completa do inventário

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS04.02.

**Implementação obrigatória:**

1. Calcular hash canônico de evidence e formatos sem timestamp.
2. Validar ticket, executor, sequence, digest, tamanho e projection antes do commit.
3. Snapshot antigo não substitui atual; TTL/restart requer refresh.

**Não fazer:** Não usar schema_version do StateStore, ref+version apenas ou ordem de array como revisão.

**Teste TR4-04-03 — preparação:** Mesmos paths/versão com bytes alterados e inventário reordenado. **Ação:** Publicar snapshots repetidos, adulterados e antigos.

**Aceite obrigatório:** Bytes/qualificação alterados mudam revisão; reorder/timestamp isolado não muda; stale/adulterado recusados antes de binding.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns04.py::test_ns04_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS04.04 — Expor opções com estados técnicos e canônicos separados

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS04.03.

**Implementação obrigatória:**

1. GET runtime-options exige executor selecionado e permissão de agente.
2. Combinar fatos recebidos com freshness/conectividade e políticas sem reescrever assessment.
3. Devolver can_prepare/can_bind/can_start e reason_codes separados.

**Não fazer:** Não transformar daemon online em runtime pronto ou READY técnico em permissão.

**Teste TR4-04-04 — preparação:** Executor offline, candidato unqualified e agente sem autorização. **Ação:** Consultar opções e comparar estados.

**Aceite obrigatório:** UI recebe razões verdadeiras; nenhuma combinação bloqueante habilita start; dados de outro executor não são apresentados ao principal errado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns04.py::test_ns04_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS04.05 — Resolver instalação da revisão exibida

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS04.04.

**Implementação obrigatória:**

1. Resposta de seleção leva executor/adapter/ref/revisão.
2. Resolver somente no executor produtor pelo helper Core público e conferir a revisão/TTL antes de apply.
3. Legacy ref baseada em fingerprint migra só com alvo único.

**Não fazer:** Não usar candidates[0], label ou hash de build como instalação.

**Teste TR4-04-05 — preparação:** Duas cópias byte-idênticas A/B e revisão inicial. **Ação:** Selecionar B, reordenar e depois alterar B antes do apply.

**Aceite obrigatório:** B continua B após reorder; drift/stale recusa antes de efeito; ref legada ambígua exige reseleção.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns04.py::test_ns04_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS05 — Realização e bindings sem atrito recorrente

**Arquivos/símbolos:** `application/execution_intents.py`; `application/endpoints.py`; `execution_bindings`; `execution_workspace_bindings`; `AgentEndpointSetup.tsx`.


### NS05.01 — Registrar realização no executor proprietário

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.05, NS04.05.

**Implementação obrigatória:**

1. Executor valida diretório/candidato/perfil e consentimento local.
2. Publicar handle/prova limitada no Server, sem argv/env ou paths por default.
3. Registrar realization_ref/revision ligada ao agente/executor/workspace.

**Não fazer:** Não autorizar uma pasta por estar no payload do Server.

**Teste TR4-05-01 — preparação:** Realização Windows remota e Server sem esse path. **Ação:** Registrar e tentar usar ref em outro executor/agente.

**Aceite obrigatório:** Somente escopo correto resolve; Server não testa filesystem remoto; nenhum spawn ao preparar.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns05.py::test_ns05_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS05.02 — Compor proposta agregada de vínculo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS05.01.

**Implementação obrigatória:**

1. Prepare recebe snapshot/realização exatos e calcula diff de confiança/política.
2. Retornar IDs técnicos gerados internamente e aprovações requeridas.
3. Dados legados não observados bloqueiam start sem pedir JSON manual.

**Não fazer:** Não gerar formulário que exige comando nativo ou profile_id para uso normal.

**Teste TR4-05-02 — preparação:** Primeiro uso local/remoto com opções inequívocas. **Ação:** Preparar proposta pela mesma API usada pela UI.

**Aceite obrigatório:** Uma confirmação mostra agente, host, instalação, projeto e escopo; backend já resolveu detalhes técnicos.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns05.py::test_ns05_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS05.03 — Aplicar proposta com CAS e recibo recuperável

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS05.02.

**Implementação obrigatória:**

1. Exigir proposal_revision e approved_diff_hash válidos.
2. Atualizar endpoint/profile/binding em T1 e retornar mesma resolução após retry.
3. Mudança concorrente de policy/inventory/root invalida proposta.

**Não fazer:** Não considerar POST reenviado uma nova criação.

**Teste TR4-05-03 — preparação:** Falha de resposta depois de commit e alteração concorrente de perfil. **Ação:** Repetir client_intent_id e depois tentar proposta obsoleta.

**Aceite obrigatório:** Sem duplicação; resposta recupera mesmo binding; mudança de escopo exige nova aprovação.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns05.py::test_ns05_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS05.04 — Implementar reuso e novo processo explícito

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS05.03.

**Implementação obrigatória:**

1. Resolver alias com filtros de executor/workspace e política.
2. Reusar só sessão compatível com mesma realização/grant vigente.
3. new_session cria intenção própria; prompt inicial é operação filha separada após READY.

**Não fazer:** Não reiniciar ao detectar timeout nem distribuir prompt a todos os bindings.

**Teste TR4-05-04 — preparação:** Duas sessões/candidatos e uma operação de open incerta. **Ação:** Pedir start repetido, novo explícito e caso ambíguo.

**Aceite obrigatório:** Reuso não cria processo; new_session autorizado é distinto; unknown/ambiguidade não escolhe substituto.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns05.py::test_ns05_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS05.05 — Tratar drift e login de provider como estados explícitos

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS05.04.

**Implementação obrigatória:**

1. Prepare/open revalidam evidências no Core.
2. Erro de login/binário/build vai ao executor correto com ação local guiada.
3. Rebind altera revisão e exige diff; não retorna binding antigo como se tivesse aplicado candidato novo.

**Não fazer:** Não instalar/atualizar provider silenciosamente nem enviar credencial de provider ao Server.

**Teste TR4-05-05 — preparação:** Atualização de binário, root movido e provider sem login. **Ação:** Iniciar pela API e rebind após consentimento.

**Aceite obrigatório:** Recusas anteriores ao efeito têm diagnóstico; rebind efetivo preserva agente/key e não desliga outra sessão.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns05.py::test_ns05_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS06 — Intenções, admissão única e dispatcher

**Arquivos/símbolos:** `application/execution_intents.py`; `application/execution_dispatch.py`; `runtime_open.py`; `runtime_control.py`; `delivery_outbox`; `execution_dispatch_outbox`.


### NS06.01 — Implementar resolve sem executar

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS02.05, NS03.05, NS05.05.

**Implementação obrigatória:**

1. Persistir client_intent_id/body_hash antes de devolver IDs.
2. Produzir IntentResolution com scope e revisões fechadas.
3. Não adicionar outbox de efeito nem chamar executor em resolve.

**Não fazer:** Não tratar resolve como start nem deixar client inventar grant.

**Teste TR4-06-01 — preparação:** Peer contador de chamadas nativas e resposta perdida de resolve. **Ação:** Resolver duas vezes mesma intenção e consultar por client_intent_id.

**Aceite obrigatório:** Zero efeitos; mesmos IDs; body diferente conflita; consulta recupera resposta perdida.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns06.py::test_ns06_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS06.02 — Admitir operação e outbox atomicamente

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.01.

**Implementação obrigatória:**

1. POST operations confirma resolução/intent_hash e autorização atual.
2. Gravar operação + outbox + claim lógico pertinente em T2.
3. Retornar 202 após commit, nunca antes; replay idêntico retorna status existente.

**Não fazer:** Não fazer rede/processo em UoW nem criar segunda delivery.

**Teste TR4-06-02 — preparação:** Injeções antes/depois de commit. **Ação:** Admitir, perder resposta e repetir chave.

**Aceite obrigatório:** Uma operação/outbox lógica e um claim; falha pré-commit não anuncia sucesso; pós-commit é consultável.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns06.py::test_ns06_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS06.03 — Implementar dispatcher com reserva e revalidação

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.02.

**Implementação obrigatória:**

1. Reservar item/bytes por token exato antes de create_task.
2. Selecionar Embedded ou Remote por executor_id canônico e revalidar autorização após espera.
3. Controle usa capacidade independente; liberar custo reservado uma vez em todos os caminhos.

**Não fazer:** Não permitir que quatro submits bloqueiem interrupt nem recalcular outro JSON para devolver quota.

**Teste TR4-06-03 — preparação:** Fila pequena saturada e rotação durante espera. **Ação:** Enfileirar submits e um controle, alterar grant antes do despacho.

**Aceite obrigatório:** Controle progride; operação obsoleta produz zero efeito; quota volta exatamente a zero ao concluir.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns06.py::test_ns06_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS06.04 — Separar dispatch, receipt e consulta

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.03.

**Implementação obrigatória:**

1. Criar rota de receipts e mesma aplicação para WSS receipt.
2. Receipt valida operação/scope/hash e grava fatos sem dispatch.
3. Em resultado de rede incerto, alterar outbox para consulta/reconcile e manter operation_id.

**Não fazer:** Não publicar receipt em POST operations com payload text_length como nova intenção.

**Teste TR4-06-04 — preparação:** Peer registra uma execução e perde ACK do receipt. **Ação:** Reenviar receipt idêntico e consultar operação.

**Aceite obrigatório:** Receipt idempotente não cria trabalho; um efeito máximo por intenção demonstrada; unknown não é retry seguro por timeout.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns06.py::test_ns06_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS06.05 — Preservar consumo exclusivo e causalidade do domínio

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.04.

**Implementação obrigatória:**

1. Conectar RuntimeDeliveryPlanner/outbox existente ao novo dispatcher.
2. MCP pull/local/remoto disputam mesmo claim.
3. Observer context-only não recebe prompt executável; turn final não completa handoff automaticamente.

**Não fazer:** Não criar nova inbox técnica ou remover limites de relay.

**Teste TR4-06-05 — preparação:** Mesma delivery disputada por MCP e dois runtimes. **Ação:** Concorrer claim e encerrar um turno sem handoff_complete.

**Aceite obrigatório:** Um executor lógico; observers não executam; handoff permanece pendente até caso de uso governado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns06.py::test_ns06_05 -q`; camada `domain_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS07 — Executor local via Core público

**Arquivos/símbolos:** `bootstrap/runtime_host.py`; `adapters/outbound/execution/embedded.py`; `launch_context.py`; `Core create_runtime/Journal/ledger`.


### NS07.01 — Compor stores e runtime por ownership explícito

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.05, NS05.05, NS06.05.

**Implementação obrigatória:**

1. Abrir SQLiteJournal/ledger Core fora do loop bloqueante, single-flight.
2. Criar runtime por sessão/realização selecionada, com mapa local e callbacks públicos.
3. Compartilhar ledger da instalação e não usar private factory/state.

**Não fazer:** Não criar uma nova quota de oito para cada binding por stores separados.

**Teste TR4-07-01 — preparação:** Dois starts concorrentes e cancelamento de um waiter. **Ação:** Compor instâncias e contar stores/workers/reservas.

**Aceite obrigatório:** Uma inicialização possuída por store; nenhum worker órfão; quota física agregada respeitada.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns07.py::test_ns07_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS07.02 — Adaptar prepare/open/control preservando IDs

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS07.01.

**Implementação obrigatória:**

1. Converter AuthorizedExecution em DTOs Core com argumentos nomeados.
2. Contexto completo e deadline já aprovado permanecem íntegros.
3. CoreError projeta code/stage/retry_safe/possible_effect sem inferências.

**Não fazer:** Não fabricar native_turn_id ou ignorar configuração/owner divergente.

**Teste TR4-07-02 — preparação:** Core real + peer nativo e contextos válidos/invalidos. **Ação:** Executar open/submit/steer/interrupt/close pelo Server.

**Aceite obrigatório:** IDs conservados e erros tipados; operação legítima funciona; scope/generation errados não alcançam peer.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns07.py::test_ns07_02 -q`; camada `core_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS07.03 — Gerar ambiente e cliente MCP por abertura

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS07.02.

**Implementação obrigatória:**

1. Criar ownership de config por digest da tupla completa, sem truncar IDs.
2. Template Core produz URL/capability consumíveis pelo harness; environment callback exclusivo daquela abertura.
3. Verificar marker antes de write, aplicar atomicamente e manter credenciais fora do prompt/argv.

**Não fazer:** Não reutilizar HOME/token da primeira sessão de um binding.

**Teste TR4-07-03 — preparação:** Duas sessões e dois Servers com IDs longos semelhantes. **Ação:** Preparar lançamento e inspecionar env/arquivos reais de laboratório.

**Aceite obrigatório:** Configurações distintas, URL correta, tokens por sessão; marker estrangeiro impede sobrescrita; nenhum MCP proxy.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns07.py::test_ns07_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS07.04 — Compor aprovação e bridge Pi por portas públicas

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS07.03.

**Implementação obrigatória:**

1. Habilitar native approvals somente com grants necessários e callback completo.
2. Pi native-action backend chama casos de uso canônicos locais; no remoto isso pertence ao Connector HTTP.
3. Resume usa CodexResumeGrant público só quando autorizado e qualificado.

**Não fazer:** Não importar CopiedAdapterFactory nem interpretar texto como claim/complete.

**Teste TR4-07-04 — preparação:** Core real e bridges de laboratório sem provider. **Ação:** Invocar pedido nativo, ação Pi limitada e tentativa fora de escopo.

**Aceite obrigatório:** Ação canônica passa pelo guard; fora de escopo recusa; capability não implementada é explicitamente indisponível.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns07.py::test_ns07_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS07.05 — Ligar eventos e encerramento ao host persistente

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS07.04.

**Implementação obrigatória:**

1. Registrar pumps/producers por SessionKey antes de aguardar.
2. Fechar clientes CLI/MCP não fecha runtime; serve owner conserva lifecycle.
3. Shutdown usa Core.shutdown e preserva unknown/releases, sem apagar instância/stores prematuramente.

**Não fazer:** Não fazer sys.exit como prova de que supervisor continua vivo.

**Teste TR4-07-05 — preparação:** Open tardio, close bloqueado e release pendente. **Ação:** Cancelar waiter, iniciar shutdown e restaurar backend.

**Aceite obrigatório:** Mesma abertura/handle permanece alcançável; controles independentes; consultas relatam físico e durável separadamente.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns07.py::test_ns07_05 -q`; camada `core_fault_injection`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS08 — Canal WSS R4 e lanes autenticadas

**Arquivos/símbolos:** `adapters/inbound/http/executor_link.py`; `adapters/outbound/execution/remote.py`; `execution_executors`; `Core NXL R4 bundle`.


### NS08.01 — Autenticar upgrade e negociar versão antes de efeitos

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.05, NS06.05.

**Implementação obrigatória:**

1. Verificar TLS/origem/subprotocolo/ticket/audiência antes de aceitar link.
2. Conferir server/executor com principal e alocar connection_id/generation por CAS.
3. Rejeitar r3 para efeitos R4 sem fallback de grants.

**Não fazer:** Não confiar na sessão HTTP de operador loopback para autenticar Connector.

**Teste TR4-08-01 — preparação:** Peers válidos e ticket cruzado, expirado ou versão antiga. **Ação:** Tentar upgrades e enviar operation antes do welcome.

**Aceite obrigatório:** Somente namespace/protocolo correto progride; zero efeito em negociação inválida; secrets ausentes do log.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns08.py::test_ns08_01 -q`; camada `transport_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS08.02 — Confirmar attach explicitamente e isolar agentes

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS08.01.

**Implementação obrigatória:**

1. Validar ticket de cada binding/agente e token capturado de attach.
2. Persistir/admitir lane e emitir binding.attached da mesma tentativa.
3. Rotação/revogação fecha proof antiga e resultado tardio não marca epoch nova como pronta.

**Não fazer:** Não equiparar write no socket a aceite do Server.

**Teste TR4-08-02 — preparação:** Dois agentes e attach antigo bloqueado durante rotação. **Ação:** Admitir A/B, rotacionar A e liberar resposta velha.

**Aceite obrigatório:** B permanece válido; A só abre sob ACK novo; ticket A não concede B; ausência de ACK mantém PENDING.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns08.py::test_ns08_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS08.03 — Implementar reconciliação e readiness por sessão

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS08.02.

**Implementação obrigatória:**

1. Executar reconcile paginado e aguardar reconcile.accepted.
2. Falha de storage fica RECOVERING; vazio só após consulta bem-sucedida.
3. Separar CONTROL_READY, lane ADMITTED, lease instalada e runtime READY.

**Não fazer:** Não marcar online=true após capturar falha e substituir report por vazio.

**Teste TR4-08-03 — preparação:** Journal indisponível e depois recuperado. **Ação:** Concluir handshake, simular falha e restaurar.

**Aceite obrigatório:** Operação nova fica bloqueada até recuperação; controles/história permitidos conforme escopo; nenhuma falsificação de liveness.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns08.py::test_ns08_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS08.04 — Validar escopo de todos os frames

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS08.03.

**Implementação obrigatória:**

1. Conferir origem autenticada em operation, ACK, reconcile, approval, detach, lease e query.
2. DTO interno retém connection_id/generation e scope completo até último recurso.
3. Revalidação após filas impede token antigo; handlers nunca resolvem pelo primeiro registro.

**Não fazer:** Não limitar verificação aos frames produtivos.

**Teste TR4-08-04 — preparação:** Canal B pede receipt/approval/session de A com IDs iguais. **Ação:** Percorrer receiver→handler→repo/Core de laboratório.

**Aceite obrigatório:** Zero dados/efeitos estrangeiros; caso legítimo passa; consultas durante handshake não ganham scope adicional.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns08.py::test_ns08_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS08.05 — Controlar filas, watchdog e cancelamento do link

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS08.04.

**Implementação obrigatória:**

1. Limitar itens/bytes antes de tasks e reservar classe de controle.
2. Watchdog periódico mede atividade válida e não lease; backoff só reconecta.
3. Socket perdido não cancela producer durável aceito; filas de geração velha não executam depois do reconnect.

**Não fazer:** Não manter milhares de tasks esperando semáforo ou reenviar efeitos para drenar fila.

**Teste TR4-08-05 — preparação:** Flood, peer silencioso e queda durante execução. **Ação:** Saturar e mandar interrupt/revoke/ACK; reconectar.

**Aceite obrigatório:** Memória/pendências limitadas; controles progridem; receipt é recuperado por ID sem duplicar trabalho.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns08.py::test_ns08_05 -q`; camada `transport_fault_injection`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS09 — Abertura remota, lease e controle completo

**Arquivos/símbolos:** `application/execution_leases.py`; `adapters/outbound/execution/remote.py`; `runtime_v1.py`; `contrato Connector R4`.


### NS09.01 — Despachar remote open por realização aprovada

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS05.05, NS06.05, NS08.05.

**Implementação obrigatória:**

1. NXL runtime.open transmite refs/candidato/modelo/perfil e scope, nunca executable/argv/path.
2. Connector valida snapshot e resolve localmente pelo Core; Server aguarda receipt/evento para declarar ready.
3. CLI Connector solicita operação canônica e não aplica localmente por fora.

**Não fazer:** Não condicionar implementação do verbo ao teste futuro nem anunciar suporte por constar no enum.

**Teste TR4-09-01 — preparação:** Server sem binários e Connector peer com Core/realização local. **Ação:** Abrir remotamente sem CLI ter criado sessão antes.

**Aceite obrigatório:** Um open com mesmo ID em Core; Server não acessa filesystem B; modo não suportado recusa antes de spawn.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns09.py::test_ns09_01 -q`; camada `cross_repo_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS09.02 — Instalar lease inicial e renovar com correlação

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS09.01.

**Implementação obrigatória:**

1. Solicitante captura t0 por request_id antes do envio.
2. Server emite serial/duração e contexto completos; Connector instala deadline=t0+budget, rejeita replay/reboot.
3. Subsequentemente Core.renew_lease confirma geração antes de lease.applied/novo trabalho.

**Não fazer:** Não usar agora+120 a cada frame nem heartbeat como renovação.

**Teste TR4-09-02 — preparação:** Relógios independentes, RTT alto e resposta duplicada. **Ação:** Solicitar initial/renew/reconnect e atrasar resposta.

**Aceite obrigatório:** Replay não estende deadline; resposta tardia não permite efeito; gerações/revisões correspondem ao grant legítimo.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns09.py::test_ns09_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS09.03 — Completar matriz de verbos e targeting

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS09.02.

**Implementação obrigatória:**

1. Suportar submit/steer/interrupt/close/approval/input por operação e capacidade.
2. Targeting nativo/current-run vem do Core e eventos observados.
3. Remote close conserva ID e receipt; nenhum segundo resolve local.

**Não fazer:** Não converter steer em interrupt+reprompt nem inventar native turn para Pi.

**Teste TR4-09-03 — preparação:** Adapters de contrato com targeting distinto. **Ação:** Exercitar cada verbo anunciado e verbos não suportados.

**Aceite obrigatório:** Somente capacidades reais passam; expected_turn preservado; operação desconhecida gera erro tipado antes do efeito.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns09.py::test_ns09_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS09.04 — Revogar sem troca silenciosa de ownership

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS09.03.

**Implementação obrigatória:**

1. Server fecha novos grants/capabilities e emite revoke/detach correlacionados.
2. Canal novo exige CAS/reconcile; old owner/credential/config fences permanecem.
3. Unknown não é realocado a outro executor disponível.

**Não fazer:** Não copiar permissões de linha de lease ou do frame para fazer passar Core.

**Teste TR4-09-04 — preparação:** Dois canais/executores concorrentes e um turno desconhecido. **Ação:** Avançar generation, revogar A e tentar execução antiga em B.

**Aceite obrigatório:** Contexto obsoleto recusado; nenhum processo substituto; histórico continua consultável no scope autorizado.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns09.py::test_ns09_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS09.05 — Qualificar desconexão de controle e ferramentas separadamente

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS09.04.

**Implementação obrigatória:**

1. Testar WSS perdido com HTTP MCP ativo e inverso.
2. Session capability continua sujeita à lease/grant; tools-only independente não exige daemon.
3. Estados de tool_path/controller/processo são separados no Server.

**Não fazer:** Não criar túnel MCP ou stdio fallback para reparar partição.

**Teste TR4-09-05 — preparação:** Dois canais controlados e uma conversa tools-only. **Ação:** Derrubar canais individualmente e expirar capability.

**Aceite obrigatório:** Sem bypass/replay de tool mutável; tools-only legítimo permanece independente; runtime gerenciado respeita sua autorização.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns09.py::test_ns09_05 -q`; camada `cross_repo_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS10 — Eventos duráveis, ACK e replay

**Arquivos/símbolos:** `application/execution_ingress.py`; `execution_event_ingress`; `execution_event_watermarks`; `dashboard SSE`; `Core Journal events/ack`.


### NS10.01 — Ingressar evento com deduplicação e watermark contíguo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.05, NS08.05, NS09.05.

**Implementação obrigatória:**

1. Validar StreamKey, bytes/hash e owner/canal.
2. Em T3 comparar duplicatas e persistir inéditos, avançando apenas trecho contíguo.
3. Emitir ACK após commit, não após enqueue/UI.

**Não fazer:** Não tratar ACK de UI como durabilidade nem confirmar além de gap.

**Teste TR4-10-01 — preparação:** Seq1/seq3, duplicata1 e duplicata com hash diferente. **Ação:** Ingressar lote e perder conexão antes/depois de commit.

**Aceite obrigatório:** Watermark só chega a1 até seq2; duplicata legítima não duplica projeção; conflito de hash é explícito.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns10.py::test_ns10_01 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS10.02 — Separar leitura finita de follower contínuo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS10.01.

**Implementação obrigatória:**

1. Core history adapter lê snapshot finito de eventos pelo Journal port.
2. Follower contínuo tem task própria, não é usado para aguardar lote cheio.
3. Batches 0/1/127/128/129 retornam conforme disponível e respeitam bytes.

**Não fazer:** Não esperar 128 eventos para publicar um único registro.

**Teste TR4-10-02 — preparação:** Um evento real persistido e nenhum posterior. **Ação:** Pedir página e publicar sem produzir outro evento.

**Aceite obrigatório:** Página termina; seq1 é enviada prontamente; próximo snapshot vazio não prende o request.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns10.py::test_ns10_02 -q`; camada `core_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS10.03 — Usar target correto e aplicar ACK local uma vez

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS10.02.

**Implementação obrigatória:**

1. Bridge fixa target do batch e aceita só ACK do stream/canal até sequência escrita.
2. Manter remote_acked/core_applied separados.
3. Igualdade satisfaz replay correspondente, não lote novo.

**Não fazer:** Não limpar ACK1 nem usar current>0 para confirmar batch2.

**Teste TR4-10-03 — preparação:** ACK1 conhecido, lote2 sem ACK2 e replay1. **Ação:** Aguardar dois alvos e injetar falha em Core acknowledge.

**Aceite obrigatório:** Replay1 conclui; batch2 aguarda; obrigação de aplicar ACK converge sem novo send_turn.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns10.py::test_ns10_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS10.04 — Recuperar publicador sem evento novo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS10.03.

**Implementação obrigatória:**

1. Registro de stream possui task/cursores/retry timer e função ensure_publisher.
2. Falha transitória de read/send/ack preserva obrigação; reconnect assegura task viva e acorda stream.
3. Drain cancela timers de observers sem reativar após fechamento.

**Não fazer:** Não sinalizar Event de task morta como se fosse recuperação.

**Teste TR4-10-04 — preparação:** Primeira leitura falha e journal contém seq1. **Ação:** Restaurar storage e sinalizar reconnect sem publish novo.

**Aceite obrigatório:** Task é retomada uma vez, seq1 publicada/confirmada, payloads offline não crescem ilimitadamente em RAM.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns10.py::test_ns10_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS10.05 — Preservar projeções canônicas e retenção

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS10.04.

**Implementação obrigatória:**

1. Mapear lifecycle/turn/tool/approval/input/error sem rotular tudo como tool.
2. Preservar native_type e last_projection offset.
3. Compactar somente dados elegíveis/ACK aplicados; gap irrecuperável explícito; terminal não perdido em flood.

**Não fazer:** Não inventar reasoning interno ausente nem usar final de turno como handoff_complete.

**Teste TR4-10-05 — preparação:** Eventos fora de ordem, terminal cedo e UI offline. **Ação:** Ingressar e reconstruir projeções duas vezes.

**Aceite obrigatório:** Estado idempotente e auditável; ACK não depende UI; handoff/causalidade continuam íntegros.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns10.py::test_ns10_05 -q`; camada `domain_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS11 — Decisão canônica e aprovação nativa íntegra

**Arquivos/símbolos:** `application/execution_decisions.py`; `application/approvals.py`; `execution_decisions`; `NativeApprovalInput.tsx`; `Core NativeApprovalOperation`.


### NS11.01 — Persistir proposta operacional separada de exibição

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS06.05, NS07.05, NS09.05, NS10.05.

**Implementação obrigatória:**

1. Validar evento Core e scope completo; armazenar immutable operational_request e hash original.
2. Produzir display_projection redigida separada.
3. Canonical request ID referencia native request/turn sem converter tipos ou colidir entre sessões.

**Não fazer:** Não substituir hashes hexadecimais por redacted nem recalcular o request recebido.

**Teste TR4-11-01 — preparação:** Pedido real observado no journal Core e pipeline de ingresso/UI. **Ação:** Receber, redigir para tela e recuperar pedido operacional.

**Aceite obrigatório:** Hash/JSON operacional byte-semanticamente preservados; UI não vaza secrets; dois namespaces não se sobrescrevem.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns11.py::test_ns11_01 -q`; camada `core_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS11.02 — Autorizar operador e aplicar CAS antes do efeito

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS11.01.

**Implementação obrigatória:**

1. Validar principal/proof de operador, subject, pedido/hash/revision/expiry e decisão.
2. Em T4 confirmar decisão e criar operation/outbox única.
3. Chave do agente que transporta solicitação não se autoaprova.

**Não fazer:** Não chamar Core antes do Server nem aceitar applied=true sem decisão correlacionada.

**Teste TR4-11-02 — preparação:** Operador válido, agente solicitante e duas decisões concorrentes. **Ação:** Tentar approve sem autoridade e CAS concorrente approve/deny.

**Aceite obrigatório:** Sem autoridade zero operação nativa; uma decisão canônica vence; perdedora recebe conflito consultável.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns11.py::test_ns11_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS11.03 — Despachar aplicação única e traduzir pelo contrato

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS11.02.

**Implementação obrigatória:**

1. Mapear approve/deny confirmado para accept/decline/cancel conforme pedido.
2. Usar operation.submit com decision_id e proposta íntegra; notification approval.decision não aplica.
3. NativeApprovalOperation usa argumentos nomeados e SessionKey validada.

**Não fazer:** Não deixar CLI aplicar nativo depois do POST em paralelo com dispatcher.

**Teste TR4-11-03 — preparação:** Server→Connector→Core reais nas fronteiras de laboratório. **Ação:** Decidir pedido e repetir resposta HTTP/notificação.

**Aceite obrigatório:** Uma aplicação por operation_id; request/turn/scope corretos; accept/decline legítimos passam e pedido velho não afeta turno novo.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns11.py::test_ns11_03 -q`; camada `cross_repo_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS11.04 — Conservar producers, recibos e incerteza de decisão

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS11.03.

**Implementação obrigatória:**

1. DecisionAttempt guarda token, client intent, producer e resultado canônico/nativo.
2. Cancelamento do waiter só encerra espera; resultados ficam consultáveis.
3. Depois de confirmação, CoreError seguro vira native_refused e efeito possível vira unknown, nunca novo pending.

**Não fazer:** Não cunhar op_appr_request_id sem namespace/digest nem repetir POST por timeout.

**Teste TR4-11-04 — preparação:** POST recebido bloqueado, cancelamento IPC e write nativo incerto. **Ação:** Cancelar waiter, consultar e restaurar backend.

**Aceite obrigatório:** Producer permanece ou resultado é classificado; mesma decisão converge; nenhuma execução duplicada ou estado pending fictício.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns11.py::test_ns11_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS11.05 — Tratar input sensível e administrativo explicitamente

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS11.04.

**Implementação obrigatória:**

1. Tipo nativo versus administrativo vem do pedido validado.
2. Guardar digest/ref e limitar raw response; implementar AUTHORIZED_INPUT_UNAVAILABLE se crash perder dado não persistido.
3. Negativa temporalmente permitida conserva action/scope; resposta expirada positiva não passa.

**Não fazer:** Não converter sessão nativa ausente em administrativa nem logar input bruto.

**Teste TR4-11-05 — preparação:** Pedido input, administrative e native session inexistente. **Ação:** Decidir, expirar e simular crash antes da aplicação.

**Aceite obrigatório:** Limite de recuperação declarado; nenhuma resposta inventada ou desvio de namespace; consultar decisão não revela conteúdo sensível.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns11.py::test_ns11_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS12 — Ferramentas diretas e governança de trabalho

**Arquivos/símbolos:** `/mcp guards`; `application/handoff*`; `application/runtime_delivery.py`; `application/runtime_causality.py`; `/v1/runtime/native-actions`.


### NS12.01 — Unificar acesso MCP e native-actions no domínio

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS03.05, NS06.05, NS07.05, NS11.05.

**Implementação obrigatória:**

1. Adaptar capability/principal para casos de uso existentes de contexto/inbox/claim/complete.
2. Bridge Pi aceita ações/payloads tipados limitados e ids idempotentes.
3. Mesmo claim lógico é compartilhado com pull MCP.

**Não fazer:** Não criar inbox ou motor de handoff no Core/Connector.

**Teste TR4-12-01 — preparação:** Uma delivery concorrida por MCP, local e Pi remoto. **Ação:** Solicitar claim/complete via caminhos distintos.

**Aceite obrigatório:** Um claimant lógico; repeat é idempotente; policy/delivery budget preservados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns12.py::test_ns12_01 -q`; camada `domain_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS12.02 — Aplicar autorização da sessão ao MCP HTTP

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS12.01.

**Implementação obrigatória:**

1. Resolver capability de sessão no guard existente sem perder AgentKeyAuthService para chaves canônicas.
2. Restringir cada tool por grant/sessão/workspace/revocation.
3. Tools-only mantém sua política separada.

**Não fazer:** Não permitir tools/call como permissão universal.

**Teste TR4-12-02 — preparação:** Capability limitada e key tools-only do mesmo agente. **Ação:** Testar tool permitida, negada, root outro e revoke.

**Aceite obrigatório:** Mesmo agente, scopes diferentes; managed não contorna lease; tools-only não depende do WSS.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns12.py::test_ns12_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS12.03 — Preservar causalidade e resultado governado

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS12.02.

**Implementação obrigatória:**

1. Ligar receipt/eventos a delivery/root/parent/correlation sem regenerar budgets.
2. Fim de turno atualiza execução, não complete de handoff.
3. Reply routing e evidence passam pelo caso de uso existente.

**Não fazer:** Não enviar resultado para primeiro agente ou restaurar hop_count após reconnect.

**Teste TR4-12-03 — preparação:** Turno final sem complete e cadeia de replies próxima do limite. **Ação:** Reconectar e completar explicitamente.

**Aceite obrigatório:** Sem complete automático nem aumento do orçamento causal; destinatário e evidência preservados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns12.py::test_ns12_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS12.04 — Publicar capacidades apenas demonstradas

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS12.03.

**Implementação obrigatória:**

1. Interseccionar implementação Core, versão/build, SO, perfil e política; separar conversation de execute_work.
2. execute_work exige caminho MCP HTTP/native-actions comprovado.
3. Attach/external só quando Core qualificado; espelhamento não executa.

**Não fazer:** Não inferir managed_work pelo nome do adapter.

**Teste TR4-12-04 — preparação:** Runtime conversacional sem tool path e outro com ponte válida. **Ação:** Consultar opções/capacidades e despachar trabalho governado.

**Aceite obrigatório:** Primeiro não recebe execute_work; segundo segue grant/claim; nenhum false READY por metadado estático.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns12.py::test_ns12_04 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS12.05 — Manter superfície MCP compacta

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS12.04.

**Implementação obrigatória:**

1. Reusar ferramentas por intenção e recursos de referência; não gerar tool por executor/adapter.
2. Medir esquema/tokens antes/depois com muitos hosts.
3. Atualizar instructions para workspace handles/remoto sem forçar CLI manual no agente.

**Não fazer:** Não exigir nova coleção de tools proporcional aos hosts.

**Teste TR4-12-05 — preparação:** Catálogo com poucos e muitos executores, mesma toolset. **Ação:** Comparar nomes/schema e executar preflight HTTP.

**Aceite obrigatório:** Número de ferramentas não cresce por host; orientação compatível com identidade/workspace e sem stdio.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns12.py::test_ns12_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS13 — Dashboard e CLI orientados por dados

**Arquivos/símbolos:** `frontend/src/components/AgentConnectionsPanel.tsx`; `AgentEndpointSetup.tsx`; `NativeApprovalInput.tsx`; `frontend/src/api.ts`; `adapters/inbound/cli/main.py`.


### NS13.01 — Implementar seleção executor→instalação→workspace

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS04.05, NS05.05, NS06.05, NS11.05.

**Implementação obrigatória:**

1. Consumir runtime-options da API e renderizar rótulos/razões do Core.
2. Armazenar executor/ref/revisão da escolha, nunca índice.
3. Refresh/revoke entre seleção e apply invalida formulário e mostra ação.

**Não fazer:** Não manter enum autoritativo em TS ou escolher primeiro candidato após reorder.

**Teste TR4-13-01 — preparação:** Duas cópias idênticas e Server Linux com executor Windows. **Ação:** Selecionar B e alterar snapshot no peer API.

**Aceite obrigatório:** UI mantém alvo correto quando válido e recusa stale; fatos remotos não são reavaliados pelo OS do Server.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns13.py::test_ns13_01 -q`; camada `ui_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS13.02 — Substituir configuração técnica por consentimento agregado

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS13.01.

**Implementação obrigatória:**

1. Separar tools-only de managed e futuro attach.
2. Ocultar IDs/profile/JSON/TTL de connection-key no caminho comum.
3. Exibir resumo de agente/host/projeto/escopo e aprovação real uma vez.

**Não fazer:** Não eliminar política para reduzir clicks nem instalar Connector no Server local.

**Teste TR4-13-02 — preparação:** Primeiro uso e uso recorrente local/remoto. **Ação:** Concluir wizard duas vezes com mesmo binding.

**Aceite obrigatório:** Segundo uso reutiliza sem chave/JSON manual; local não exige Connector; remoto não pede provider secret ao Server.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns13.py::test_ns13_02 -q`; camada `ui_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS13.03 — Implementar acompanhamento por IDs e estados honestos

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS13.02.

**Implementação obrigatória:**

1. Start/interrupt/stop/decision devolvem operação/decision_id e consulta.
2. Exibir canonical acceptance separado de native stage e unknown.
3. Timeout mantém cartão consultável, sem auto-retry de efeito.

**Não fazer:** Não mostrar sucesso porque o POST recebeu 202.

**Teste TR4-13-03 — preparação:** Resposta perdida após admissão e evento terminal posterior. **Ação:** Operar UI e reconectar SSE.

**Aceite obrigatório:** Mesmo ID reaparece e estado converge sem segundo start; UI offline não altera ACK durável.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns13.py::test_ns13_03 -q`; camada `ui_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS13.04 — Concluir CLI humana/headless e logs observadores

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS13.03.

**Implementação obrigatória:**

1. Comandos runtime usam mesmos casos de uso e `--json`.
2. Cliente grava client_intent_id antes de mutações e respeita non-interactive.
3. Ctrl+C no follower não encerra supervisor; daemon/serve têm namespaces próprios.

**Não fazer:** Não pedir segredo por argv ou converter headless em autoapprove.

**Teste TR4-13-04 — preparação:** Ambiguidade de aliases e prompt desabilitado. **Ação:** Executar start/status/logs/stop com timeouts.

**Aceite obrigatório:** Erros estáveis e ação corretiva; identidade correta; follower termina sem matar runtime.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns13.py::test_ns13_04 -q`; camada `cli_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS13.05 — Expor diagnóstico e aprovações sem vazar dados

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS13.04.

**Implementação obrigatória:**

1. Doctor/status separa API, controle, lane, inventário, runtime, provider, ferramenta e storage.
2. Decisão mostra autoridade e resultado canônico/nativo; preservar operacional íntegro fora da exibição.
3. Conferir acessibilidade/locale/paths com espaços e redaction.

**Não fazer:** Não enviar raw operational proposal ou chave para qualquer observador.

**Teste TR4-13-05 — preparação:** Usuário de teste autorizado e agente com leitura restrita. **Ação:** Consultar views/log/export e responder pedido por UI.

**Aceite obrigatório:** Scopes/reasons úteis sem secrets; canal de apresentação não torna agente seu próprio aprovador.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns13.py::test_ns13_05 -q`; camada `ui_security`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS14 — Recuperação, revogação, shutdown e limites

**Arquivos/símbolos:** `application/execution_recovery.py`; `bootstrap/runtime_host.py`; `execution_leases.py`; `auth cache`; `execution history`.


### NS14.01 — Recuperar histórico antes de admitir após restart

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS07.05, NS08.05, NS09.05, NS10.05, NS11.05.

**Implementação obrigatória:**

1. Abrir journal/ledger independentemente de provider e consultar claims/recibos/fences paginados.
2. Reconstituir obrigações e consultar execuções incertas.
3. Refresh do inventário e reconcile precedem novo efeito.

**Não fazer:** Não retornar vazio por journal_if_open=None nem exigir binário para ler receipt.

**Teste TR4-14-01 — preparação:** Receipt real em disco, processo aplicativo novo e binário removido. **Ação:** Reiniciar host e consultar client intent/operation/session.

**Aceite obrigatório:** Histórico responde; ownership desconhecido permanece; nenhum novo spawn para recuperar dados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns14.py::test_ns14_01 -q`; camada `restart_integration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS14.02 — Invalidar autoridade em todas as superfícies

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS14.01.

**Implementação obrigatória:**

1. Rotação/revogação altera epochs e fecha caches/lanes/capabilities online.
2. Manter hold conservador em commit incerto e comparar linha completa na recuperação.
3. Processo local/remote respeita prazo sem importar permissões da linha.

**Não fazer:** Não limpar hold por timeout ou Future.done.

**Teste TR4-14-02 — preparação:** CAS perdido para geração mais nova e ACK perdido após revoke. **Ação:** Consultar, tentar submit antigo e recuperar storage.

**Aceite obrigatório:** Contexto antigo zero efeito; rollback comprovado recupera disponibilidade; verdadeiramente unknown continua restrito.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns14.py::test_ns14_02 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS14.03 — Implementar shutdown DRAINING_PENDING com orçamento único

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS14.02.

**Implementação obrigatória:**

1. Fechar novas admissões e agendar Core.shutdown em paralelo com controles urgentes.
2. Ao esgotar prazo, retornar relatório por recurso e conservar loop/IPC de recuperação se unknown.
3. Stores só fecham depois de producers/obrigações resolvidos ou transferência qualificada explícita.

**Não fazer:** Não sair com code1 supondo que supervisor segue vivo; não serializar N vezes 50 s.

**Teste TR4-14-03 — preparação:** Dois runtimes, open tardio, close travado e release pendente. **Ação:** Parar Server e depois restaurar backend.

**Aceite obrigatório:** Prazo público limitado; ambos relatados; força não espera storage; segunda recuperação alcança mesmos owners sem duplicação.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns14.py::test_ns14_03 -q`; camada `core_fault_injection`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS14.04 — Aplicar quotas e cache limitados com medições

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS14.03.

**Implementação obrigatória:**

1. Implementar limites de itens/bytes, fair scheduling e reserva crítica.
2. Cache positivo limitado/TTL com invalidação; métricas sem cardinalidade por agente.
3. Ensaio sintético com 100 mil identidades e churn.

**Não fazer:** Não usar número de agentes como promessa de concorrência física.

**Teste TR4-14-04 — preparação:** Base sintética e flood de um executor com outro legítimo. **Ação:** Medir lookup/memória/filas e enviar controle sob carga.

**Aceite obrigatório:** Sem full enumeration por onboarding; memória bounded; controles e outro agente progridem; resultados e hardware registrados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns14.py::test_ns14_04 -q`; camada `load`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS14.05 — Testar falhas de processo e limites de plataforma

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS14.04.

**Implementação obrigatória:**

1. Usar processo inofensivo possuído em SO qualificado para shutdown/crash do owner.
2. Validar birth/guardian/árvore e retain unknown quando falta prova.
3. Separar os testes de provider e de máquina remota da simulação.

**Não fazer:** Não remover require_containment para obter PASS.

**Teste TR4-14-05 — preparação:** Backend real disponível ou bloqueio documentado. **Ação:** Matar supervisor de laboratório e observar árvore própria.

**Aceite obrigatório:** Apenas ownership comprovado é controlado; backend ausente é BLOCKED/NOT_RUN, não PASS universal.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns14.py::test_ns14_05 -q`; camada `os_backend`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS15 — Migração, cutover e eliminação de cópias

**Arquivos/símbolos:** `migrations/`; `execution_migration_map`; `adapters/outbound/harness/*`; `application/adapter_registry.py`; `runbooks`.


### NS15.01 — Executar M0–M3 com preservação e retomada

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS01.05, NS02.05, NS07.05, NS12.05, NS13.05, NS14.05.

**Implementação obrigatória:**

1. Gerar backup consistente e conteagens/digests.
2. Backfill por batches idempotentes com migration_map e tradução legada fechada.
3. Preservar keys/IDs/políticas e marcar candidato incompleto para rediscovery.

**Não fazer:** Não apagar coluna/linha para caber no schema novo.

**Teste TR4-15-01 — preparação:** Snapshot legado com endpoints negados, jobs históricos e keys. **Ação:** Interromper backfill e retomar duas vezes.

**Aceite obrigatório:** Mesmos IDs/negações/conteagens; batches convergem; nenhuma migração abre processo.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns15.py::test_ns15_01 -q`; camada `migration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS15.02 — Drenar owner antigo antes de trocar execução

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS15.01.

**Implementação obrigatória:**

1. Bloquear novos efeitos no supervisor legado e conservar queries.
2. Encerrar/observar recursos pelo owner que realmente os possui.
3. Só habilitar Core após resolução ou bloqueio explícito por unknown; nunca adotar PID.

**Não fazer:** Não transferir pipes/handle por copiar estado.

**Teste TR4-15-02 — preparação:** Sessão antiga ativa e outra com resultado incerto. **Ação:** Executar cutover controlado e tentar abrir substituto.

**Aceite obrigatório:** Ativa encerra pelo mecanismo correto; unknown não duplica; rollback não reativa stdio.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns15.py::test_ns15_02 -q`; camada `migration_runtime`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS15.03 — Remover loaders/codecs duplicados depois de paridade

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS15.02.

**Implementação obrigatória:**

1. Substituir usos do registry e classes nativas pelo Core em todas as superfícies.
2. Remover parsers/spawn antigos e wrappers transitórios já sem consumidores.
3. Manter migração de IDs legados isolada, sem catálogo paralelo no hot path.

**Não fazer:** Não remover domínio/planner/handoff junto com a física.

**Teste TR4-15-03 — preparação:** Busca estática de imports/Popen e testes de comportamento local. **Ação:** Executar verificação de fronteiras e paridade delimitada.

**Aceite obrigatório:** Runtime físico só existe no Core; domínio e HTTP MCP preservados; nenhum import da aplicação Connector.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns15.py::test_ns15_03 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS15.04 — Migrar configuração e documentar rollback seguro

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS15.03.

**Implementação obrigatória:**

1. Layout novo de HOME/config usa owner digest e marker verificado.
2. Sessão ativa mantém caminho original até resolução.
3. Runbook diferencia rollback pré-efeito, drain posterior e restore explícito.

**Não fazer:** Não mover pasta ativa nem excluir journal para voltar versão.

**Teste TR4-15-04 — preparação:** Falha de apply e tree com marker de outro binding. **Ação:** Aplicar/repetir/migrar configuração e ensaiar restore.

**Aceite obrigatório:** Config alheia intacta; rollback recusado quando inseguro; histórico e operações unknown preservados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns15.py::test_ns15_04 -q`; camada `migration`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS15.05 — Atualizar documentação e instruções operacionais

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS15.04.

**Implementação obrigatória:**

1. Remover rituais/stdin/fachada e orientar HTTP direto + Core local.
2. Documentar estados/capacidades/limites de suporte e comandos reais.
3. Declarar protocolos/versionamento e proofs que faltam, sem herdá-los de mock.

**Não fazer:** Não anunciar quatro adapters operacionais porque catálogo tem quatro entradas.

**Teste TR4-15-05 — preparação:** README/help/resources/dashboard atualizados. **Ação:** Comparar docs com APIs e matriz de capacidade.

**Aceite obrigatório:** Nenhum comando fictício apresentado como existente; docs não contradizem gate/qualificação e negações.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns15.py::test_ns15_05 -q`; camada `unit_contract`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


## NS16 — Artefatos, integração vertical e liberação

**Arquivos/símbolos:** `CI`; `tests/execution_r4/`; `wheels Nexus/Core/Connector`; `matriz TN/J`; `release report`.


### NS16.01 — Construir artefatos imutáveis e contratos instalados

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS09.05, NS10.05, NS11.05, NS12.05, NS13.05, NS14.05, NS15.05.

**Implementação obrigatória:**

1. Build wheel/sdist em cópia limpa; fixar Core por versão/hash e revisão R4.
2. Instalar sem clones irmãos nem app Connector no modo local.
3. Testar import -I, assets/UI, CLI, catálogo, disponibilidade e conformance.

**Não fazer:** Não usar último wheel por ordem lexical ou main no runtime.

**Teste TR4-16-01 — preparação:** Ambiente isolado sem fonte no sys.path. **Ação:** Instalar e executar smoke público.

**Aceite obrigatório:** Hashes/versões registrados; serve-lite funcional sem torch novo; nenhum schema é obtido remotamente em execução.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns16.py::test_ns16_01 -q`; camada `packaging`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS16.02 — Executar conjunto completo de regressões sem inflar números

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS16.01.

**Implementação obrigatória:**

1. Rodar suíte Nexus e testes R4; incorporar causas CN1–CN5 relevantes nas fronteiras.
2. Comparar falhas preexistentes/ambiente, não somar subconjunto como teste novo.
3. Preservar controles positivos e registrar adaptação de fixture causal.

**Não fazer:** Não xfail bugs ou fazer revisor parecer autor de XML recebido.

**Teste TR4-16-02 — preparação:** Ambiente atual e fixtures de fault injection. **Ação:** Rodar duas vezes casos de corrida e uma suíte completa.

**Aceite obrigatório:** Resultados por camada/node/versão; nenhum PASS sem execução; falha externa distinguida de defeito funcional.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns16.py::test_ns16_02 -q`; camada `regression_suite`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS16.03 — Qualificar ciclo local sem Connector instalado

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS16.02.

**Implementação obrigatória:**

1. Nexus+Core no host com um harness autorizado e qualificado.
2. UI/CLI usa catálogo/realização, abre, envia tarefa inofensiva, recebe eventos, decide, interrompe e para.
3. MCP HTTP direto opera com mesma identidade e capability limitada.

**Não fazer:** Não usar peer fake como prova de provider real.

**Teste TR4-16-03 — preparação:** Um SO/provider autorizado e pacote Nexus/Core apenas. **Ação:** Executar caminho local ponta a ponta.

**Aceite obrigatório:** Mesmo adapter Core; nenhum Connector/WSS local obrigatório; governança e shutdown demonstrados.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns16.py::test_ns16_03 -q`; camada `provider_local`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS16.04 — Qualificar ciclo remoto heterogêneo

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS16.03.

**Implementação obrigatória:**

1. Instalar Server A sem binários/paths/providers de B; Connector B com mesmo Core e revisão.
2. Configurar agente existente, publicar inventário, selecionar instalação e despachar runtime.open do Server.
3. Exercitar tarefa inofensiva, evento/ACK, approval/input, interrupt/close, partições/restart e recibo perdido; depois repetir em outro host delimitado.

**Não fazer:** Não declarar G2 por localhost ou por testar Core sem aplicativos.

**Teste TR4-16-04 — preparação:** Topologia A/B/C autorizada com ao menos um Windows/Unix pertinente. **Ação:** Executar J01–J34 e TR4 correspondentes com artefatos exatos.

**Aceite obrigatório:** Nenhum filesystem remoto resolvido em A, nenhuma execução duplicada, mesmos IDs; limitações de provider/SO explícitas.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns16.py::test_ns16_04 -q`; camada `multi_host`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.


### NS16.05 — Emitir decisão por escopo e handoff final

**Responsável:** Server. **Estado:** PENDING. **Dependências:** NS16.04.

**Implementação obrigatória:**

1. Gerar relatório com G0/G1/G2/G3 e capacidades realmente demonstradas.
2. Anexar artefatos, hashes, migrations, testes, owners e bloqueios; atualizar crosswalk.
3. Não publicar release/push automaticamente; aprovação de entrega não amplia permissão de agentes.

**Não fazer:** Não marcar integralmente DONE enquanto remote open/approvals/estado incerto estiverem sem implementação ou evidência.

**Teste TR4-16-05 — preparação:** Todas as evidências anteriores e casos NOT_RUN remanescentes. **Ação:** Revisar cada gate e requisito original preservado.

**Aceite obrigatório:** Decisão proporcional, sem ambiguidades; outro agente consegue instalar artefato e repetir campanha sem inferir campos/rotas.

**Prova a entregar:** diff/commit e resultado de `python -m pytest tests/execution_r4/test_ns16.py::test_ns16_05 -q`; camada `release_review`. O arquivo de teste deve ser implementado antes de rodar; ausência de ambiente não vira PASS.
