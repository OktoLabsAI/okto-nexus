# Fontes, baseline e natureza das decisões

## 1. O que foi feito nesta elaboração

Foram lidos os dois documentos anexados pelo usuário, o plano original completo, os relatórios e o handoff CN5 disponíveis na conversa, arquivos selecionados da branch do Nexus pelo conector GitHub e os contratos atuais do Core e Connector. As três pontas foram identificadas por commit, sem inferir que `main` de um repositório representa o código de outro.

**Não foi realizada uma auditoria integral de bugs do Server. Não foram executados testes dos produtos, providers, UI ou dois hosts. Nenhum código de repositório, banco de usuário, permissão, branch ou release foi alterado.** A validação incluída neste pacote verifica os documentos, dependências, rastreabilidade e exemplos de schema de planejamento; não valida os produtos.

A inspeção tem abrangência dirigida: bootstrap/CLI/MCP, HTTP/auth, abertura local, registry, identidade/workspace, política de endpoints, persistência de endpoints, entrega/outbox e painel de conexões. Arquivos não relidos ficam explicitamente a confirmar em NS00. A ausência de leitura de um arquivo não é usada como prova de inexistência de funcionalidade.

## 2. Baseline confirmado nesta elaboração

| Componente | Ref efetiva | Commit | Versão | Natureza |
|---|---|---|---|---|
| Nexus Server | `feature/v0.2.0` | `7ed52c22865a92c3768bc32508ed9e35dc5efdc3` | `0.2.0` | Branch localizada no GitHub; coincide com referência R3. |
| Core | `main` | `1560d314ed2b478515dcbbe533436d7d0b027b09` | `0.2.10.dev0` | API/contratos C11 verificados; não equivale a qualificação de todos os providers. |
| Connector | `main` | `87b8fd2e3e403cb6a70a1ce265618e29c7a6b86c` | `0.4.0.dev0` | Último snapshot examinado na auditoria CN5; Q01–Q04 permanecem pendentes até nova evidência. |

O pedido escreveu `feature/0.2.0`; a busca de branches encontrou `feature/v0.2.0`, e a coleção de branches confirmou o SHA acima. Não se criou nem renomeou uma branch. O agente executor deve repetir a consulta no seu checkout e preservar alterações posteriores.

A implementação pública C11 do Core distingue instalação (`nexus-install-v1:`) de conteúdo. O texto antigo em parte de `docs/api.md` que ainda chama candidate_ref de fingerprint não altera a semântica do código/versionamento 2: usar `resolve_installation` e as referências de instalação. Registrar essa divergência documental, não reproduzi-la no Server.

## 3. Hierarquia de autoridade

1. Decisão explícita do usuário em `ALTERACOES_R3_MCP_HTTP(1).md`: HTTP MCP direto, sem MCP stdio/shim/proxy no Core/Connector, sem mudar o agente.
2. Plano R3 anexado: requisitos de domínio, experiência, separação de projetos, migração e testes TN/J preservados pelo crosswalk.
3. APIs e schemas executáveis nos SHAs efetivos: descrevem o que existe, não o que já está qualificado entre os aplicativos.
4. Auditorias CN1–CN5: evidências históricas e requisitos corretivos do Connector; este pacote não declara nova execução dessas campanhas.
5. Decisões novas R4 deste pacote: arquitetura de integração proposta para implementação. Não são apresentadas como código já existente ou como decisão anterior do usuário.

Se um comportamento do código conflitar com requisito normativo, corrigir o comportamento; não reclassificar o bug como requisito. Se um contrato novo deste pacote exigir alteração coordenada, manter o gate externo explícito e produzir o artefato compartilhado antes do efeito, sem inventar defaults locais.

## 4. Decisões R4 deliberadamente novas

| ID | Decisão de implementação | Por que foi escolhida | O que muda / o que não muda |
|---|---|---|---|
| DR4-01 | Server é o único admitente/dispatcher de intenções produtivas; CLI remota propõe e consulta. | Eliminar autoria híbrida e duplicação entre POST de operação e execução local imediata. | Requer adaptar fluxo do Connector; não muda shutdown proprietário, domínio nem Core nativo. |
| DR4-02 | Nova revisão NXL r4 fechada e explicitamente negociada. | r3 é parcial e não fecha ACK de lane/reconcile, lease correlacionada e abertura remota com contrato completo. | Core publica codecs; Server/Connector consomem. r3/histórico não são sobrescritos. |
| DR4-03 | `/v1` novo usa objetos diretos; `/api/v1` legado conserva envelope atual. | Reconciliar a interface existente do Server com a superfície de gestão já usada pelo Connector. | Casos de uso são únicos; não duplicar efeito nem redirecionar POST. |
| DR4-04 | Inventory snapshot por HTTPS versionado com revisão integral, sequência e TTL. | Availability2 não cabe como campos extras no frame r3 e deve ser produzida no executor correto. | Reutiliza Core; o host acrescenta origem/frescor/política. Não cria outro catálogo. |
| DR4-05 | Decisão canônica gera uma operação de aplicação, expedida pelo dispatcher. | Não usar bool HTTP para duas superfícies aplicarem a mesma decisão; preservar CAS e namespace. | Connector CLI não responde ao Core por fora da operação. Modelo de operador existente é preservado. |
| DR4-06 | Lease calculada do t0 do request local, sem compartilhar relógios monotônicos. | Conservar prazo após filas/replay/RTT e não reancorar autorização em cada mensagem. | Requer nonce/serial e prova de aplicação; heartbeat não concede lease. |
| DR4-07 | Recursos incertos mantêm supervisor e interface limitada em DRAINING_PENDING. | Código de saída não conserva ownership nem producer. | Saída alternativa só com transferência de contenção qualificada e evidência. |
| DR4-08 | Input bruto sensível não entra em journal/log; sem store sensível qualificado, crash antes da entrega é limitação explícita. | Não prometer recuperação de conteúdo que não foi persistido e não introduzir secret service implicitamente. | Digest/decisão são duráveis; após crash pode exigir fornecimento explícito autorizado. |
| DR4-09 | Camada nova usa IDs 1–160, sem truncamento; legado continua consultável. | Alinhar APIs do Core, NXL e reconciliação, preservando histórico já aceito. | Não alterar hashes/IDs antigos; chave de diretório deriva de owner completo. |

Defaults de 120 s de lease/frescor, budgets de filas e shutdown são decisões iniciais para testar, não resultados de benchmark. O plano permite restringir suporte por evidência, mas não esconder funcionalidades não implementadas como se estivessem entregues.

## 5. Fontes primárias lidas e âncoras

**S01 — Plano R3 anexado:** `01_PLANO_NEXUS_SERVER(1).md`, referência original de 25/09/2026. Uma cópia exata está em `referencias/`. Os 70 requisitos de tarefa e 79 testes foram extraídos sem substituição silenciosa; consultar documento 07.

**S02 — Correção MCP HTTP anexada:** `ALTERACOES_R3_MCP_HTTP(1).md`. É a autoridade explícita para remover stdio sem legado, não uma opção de transporte a escolher pelo executor.

**S03 — Branches do Nexus:** https://api.github.com/repos/OktoLabsAI/okto-nexus/branches. Consulta efetuada nesta elaboração. O URL de coleção é mutável; o plano usa o SHA imutável da tabela de baseline.

**S04 — Metadados e dependências do Nexus:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/pyproject.toml. Confirma MCP `>=1.0,<2`, Python >=3.11, extras serve/serve-lite e entrypoint compartilhado com mcp.server; o Core ainda não consta como dependência.

**S05 — Abertura existente:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/runtime_open.py. Confirma reserva idempotente e chamada direta a construct/supervisor.open após owner_guard. Preservar reserva e autoridade, substituir a física pela porta.

**S06 — Identidade:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/auth.py e https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/identity.py. Confirma AgentKeyAuthService, retorno de plaintext uma vez, cache, touch e workspace legado por path do servidor. As novas extensões não substituem a identidade canônica.

**S07 — Registro e política:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/adapter_registry.py e https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/domain/endpoints.py. Registry local possui factories; endpoint conserva política e interseção de capacidades. Remover duplicação física, não regras canônicas.

**S08 — Bootstrap e HTTP:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/adapters/inbound/mcp/server.py e https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/adapters/inbound/http/app.py. HTTP importa Deps/registro do módulo compartilhado. A remoção de stdio deve extrair bootstrap antes de eliminar transporte, sem apagar tools ou resources.

**S09 — Rotas atuais de conexão:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/adapters/inbound/http/connections.py. Superfícies locais existentes não constituem o conjunto distribuído `/v1` proposto neste plano.

**S10 — Painel existente:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/frontend/src/components/AgentConnectionsPanel.tsx. Confirma lista legada de labels, endpoints, emissão de connection key, autorização por uma hora e mensagem de execução na máquina do Server. Arquivos vizinhos `AgentEndpointSetup.tsx`, `NativeApprovalInput.tsx` e `frontend/src/api.ts` foram localizados na árvore; NS00 deve inspecioná-los integralmente antes de alterar.

**S11 — Entrega existente:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/application/runtime_delivery.py. Planner transacional, consumo exclusivo, causalidade/outbox e observadores devem ser preservados, não substituídos por uma fila paralela no Connector.

**S12 — Persistência de endpoints:** https://github.com/OktoLabsAI/okto-nexus/blob/7ed52c22865a92c3768bc32508ed9e35dc5efdc3/src/okto_nexus/adapters/outbound/sqlite/endpoints_repo.py. Os nomes `agent_endpoints`, `runtime_profiles`, `runtime_boot_bindings`, `runtime_execution_grants` e `runtime_open_requests` foram observados. O schema definitivo de migração depende do inventário completo de migrations em NS00/NS02.

**S13 — Core atual:** https://api.github.com/repos/OktoLabsAI/okto-nexus-connector-core/branches e https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/1560d314ed2b478515dcbbe533436d7d0b027b09/docs/api.md. APIs públicas de catálogo, availability2, instalação, runtime, histórico, lease e ledger; helpers nativos privados não são contrato dos consumidores.

**S14 — Bundle existente:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/1560d314ed2b478515dcbbe533436d7d0b027b09/src/nexus_connector_core/contracts/nxl/v1/manifest.json. Revisão r3 com `development-partial`. O campo histórico `core_version=0.1.0.dev0` desse manifest não substitui a versão 0.2.10.dev0 do pacote. Refs R4 neste pacote são especificação nova, não artefato já publicado.

**S15 — Instalação e disponibilidade C11:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/1560d314ed2b478515dcbbe533436d7d0b027b09/src/nexus_connector_core/installation.py e https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/1560d314ed2b478515dcbbe533436d7d0b027b09/src/nexus_connector_core/availability.py. Conforme código recuperado na conversa e documentação atual: ref opaca por alvo; formato2; resolução exata; Core do host avalia, não UI central.

**S16 — Connector atual:** https://api.github.com/repos/OktoLabsAI/okto-nexus-connector/branches. Confirma 87b8fd2; código e análise CN5 desta conversa distinguem o que já foi ligado do que permanece bloqueado. Não foi executada uma nova suíte do Connector na presente elaboração.

**S17 — Último handoff CN5:** `REAVALIACAO_CONNECTOR_87B8FD2_CN5/04_STATUS_E_HANDOFF.md`, disponibilizado na conversa e relido nesta elaboração. Explicita abertura remota indisponível até contrato integrado, pendências de intenção/decisão/recibo persistentes, publicação/UI e qualificações. Cópia de referência acompanha este pacote. Q01–Q04 são correções do Connector, não tarefas para o Server contornar com permissões ampliadas.

## 6. Limites dos artefatos deste pacote

`contratos/http-target.schema.json` especifica corpos de planejamento, exemplos e validações de forma. `contratos/nxl-r4-delta.json` é uma solicitação de evolução ao Core, não uma implementação de codec. Os hashes dos exemplos são placeholders sintaticamente válidos, não vetores JCS calculados. A implementação deverá usar o canonicalizador real do Core e seus vetores completos.

`validar_pacote.py` verifica organização, rastreabilidade, DAG e casos de schema dos exemplos. Seu resultado PASS não é um teste de Nexus, Connector, Core, TLS, processo, provider ou UI. Todos os 164 cenários de produto permanecem NOT_RUN na matriz entregue. Não atribuir PASS a TN/J a partir do validador documental.

A matriz R3 foi mantida como camada de requisitos, não como segunda autoridade de contrato: exemplos antigos de rotas, APIs incompletas e wire r3 são substituídos explicitamente pelo documento 02. Não executar dois planos concorrentes nem apagar a evidência anterior.
