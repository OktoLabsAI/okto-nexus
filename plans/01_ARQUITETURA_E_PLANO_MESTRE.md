# Nexus Server — plano unificado R4

**Documento normativo de implementação. Data: 29/09/2026.**

**Repositório:** `OktoLabsAI/okto-nexus`. **Branch efetivamente encontrada:** `feature/v0.2.0`. O nome `feature/0.2.0` informado no pedido não apareceu na listagem consultada. **Baseline conferido:** `7ed52c22865a92c3768bc32508ed9e35dc5efdc3`, pacote `0.2.0`. Não fazer reset para esse commit.

**Dependências examinadas:** Core `0.2.10.dev0`, commit `1560d314ed2b478515dcbbe533436d7d0b027b09`; Connector `0.4.0.dev0`, commit `87b8fd2e3e403cb6a70a1ce265618e29c7a6b86c`. O CN5 é o último plano de correção recebido para o Connector; não há evidência, nesta elaboração, de sua implementação posterior. Ver `08_FONTES_BASELINE_E_DECISOES.md`.

**Natureza da entrega:** análise estática dirigida, revisão dos documentos e especificação consolidada. Não é auditoria completa do Nexus, execução de sua suíte, qualificação dos providers, alteração de código ou publicação. Os testes do produto previstos neste pacote começam `NOT_RUN`; as tarefas começam `PENDING`.

## 1. Hierarquia documental e escopo

Este pacote substitui o **plano de execução do Server** da revisão 3 e seus anexos de interface nos pontos expressamente atualizados. As decisões de identidade, MCP e separação de responsabilidades de R3 são preservadas. Os documentos históricos em `referencias/` não constituem um segundo backlog ativo. A tabela `07_RASTREABILIDADE_R3.md` mapeia as 70 tarefas N00–N13 e conserva os 45 TN e 34 J.

Ordem normativa dentro deste pacote: arquitetura deste documento; contrato `02_CONTRATOS_HTTP_NXL_E_ESTADOS.md`; persistência/migração em `03_DADOS_MIGRACAO_E_RECUPERACAO.md`; tarefas em `04_BACKLOG_EXECUCAO.md`; critérios em `05_TESTES_E_ACEITE.md`. Em caso de divergência descoberta durante execução, abrir uma correção documental identificada antes de implementar o trecho divergente. Não escolher silenciosamente uma interpretação.

São três classes de afirmação: **EXISTENTE VERIFICADO**, sustentado por código/documento identificado; **REQUISITO PRESERVADO**, originado de R3/CN; e **DECISÃO R4 A IMPLEMENTAR**, detalhamento normativo deste plano, ainda não presente nas dependências. O número R4 do plano não anuncia versão lançada do software, do MCP ou do Core.

O objetivo é permitir a mesma identidade de agente em MCP HTTP direto, runtime gerenciado local e runtime gerenciado remoto, com configuração por intenção, uso recorrente sem ritual técnico e execução governada sem duplicação.

Ficam fora: login de usuário Nexus, tenant obrigatório, SSO novo, A2A completo, sincronização de checkouts, instalação automática de providers, orquestração cloud, HA multiwriter, migração de SDK MCP major e reescrita dos protocolos nativos. Attach permanece no escopo original como capacidade futura condicionada à qualificação; não é habilitado por constar no catálogo.

## 2. Decisões fechadas

| ID | Decisão vinculante |
|---|---|
| D01 | A identidade canônica é `agent_id`, resolvida por `AgentKeyAuthService`. Executor, instalação, sessão e conversa nativa não são agentes. Não introduzir `user_id` para viabilizar conexão. |
| D02 | MCP existe somente no endpoint HTTP(S) do Nexus. Remover execução MCP stdio, comandos, configurações e shim. Stdio dos protocolos de Codex/Pi/Claude continua permitido. |
| D03 | Server e Connector dependem do mesmo wheel do Core. Server nunca importa a aplicação Connector. Física de processos, codecs, qualificação e catálogo pertencem ao Core. |
| D04 | Execução local usa Core no processo proprietário de `serve`, sem Connector instalado e sem WSS em loopback como intermediário. |
| D05 | Controle remoto continua por WSS/NXL iniciado pelo Connector. HTTPS é gestão/publicação. SSE do dashboard permanece para observação. Não trocar WSS por SSE nesta unificação. |
| D06 | O catálogo da UI deriva do Core do executor selecionado. Disponibilidade técnica e autorização de binding são dimensões diferentes. |
| D07 | Uma instalação é escolhida por executor + adaptador + referência opaca + revisão do inventário. Bytes iguais não tornam dois alvos a mesma instalação. |
| D08 | **Novo:** toda execução produtiva, inclusive solicitada pela CLI do Connector, é admitida no Server e despachada por um único dispatcher. A CLI não executa localmente e depois solicita outra execução ao Server. |
| D09 | `intents:resolve` não executa. `POST /runtime/operations` admite uma operação/outbox. Publicação de receipt tem rota própria e jamais inicia trabalho. |
| D10 | **Novo:** as rotas de integração usam `/v1`, sem envelope `ok/data`, porque esse é o prefixo consumido pelo Connector. `/api/v1` e seu envelope são preservados nas rotas legadas. Não redirecionar POST entre prefixos. |
| D11 | Operação e pedido recebem identificadores estáveis antes de qualquer mutação remota. Timeout não cria ID novo nem comprova ausência de efeito. |
| D12 | Server faz commit de eventos antes do ACK contíguo. UI/SSE não participa da confirmação de durabilidade. |
| D13 | Aprovação canônica antecede aplicação nativa. Proposta operacional íntegra e projeção redigida são objetos diferentes. Não redigir ou recalcular `request_hash` no caminho operacional. |
| D14 | Shutdown termina sua espera, não a propriedade de Future/processo/commit. Unknown conserva supervisão; STOPPED e release persistido são fatos separados. |
| D15 | Campos/revisões novos não entram clandestinamente em NXL r3. A revisão executável R4 descrita no documento de contratos deve ser produzida no Core e adotada pelos dois aplicativos. |
| D16 | Uma falha do Connector continua sendo uma falha do Connector. O Server não concede permissões adicionais, copia adapters ou emite respostas fictícias para contornar CN5. |

## 3. Baseline realmente observado

As seguintes observações são de inspeção, não novas reproduções de defeitos:

| Área | Estado observado | Consequência para a implementação |
|---|---|---|
| `pyproject.toml` | CLI aponta para `adapters.inbound.mcp.server:main`; não declara Core; MCP v1 é delimitado por `<2`; há extras `serve` e `serve-lite`. | Extrair bootstrap e retificar entrypoint antes de remover stdio. Acrescentar Core em ambos os extras que prometem execução local, sem adicionar Connector. |
| `http/app.py` | `/mcp`, `/api/v1` e SPA compartilham processo; importa `Deps`, registro de tools e outros símbolos de `mcp/server.py`. | Não apagar esse módulo inteiro antes de mover suas partes compartilhadas. Preservar endpoint HTTP, tools/resources e autenticação. |
| `runtime_open.py` | Reserva requisição durável, chama `construct(...)` e `supervisor.open(...)`; controle restrito ao owner de serve. | Conservar admissão e adaptar realização a `ExecutorPort`. Não transformar owner loopback em transporte remoto. |
| `adapter_registry.py` | Registro local contém factory e metadados próprios. | Substituir fonte autoritativa por projeção do Core; manter apenas tradutor legado fechado e temporário. |
| `identity.py` | Workspace legado deriva do path resolvido no Server. | Preservar IDs existentes; novos vínculos remotos são lógicos e resolvem path somente no executor. |
| `http/connections.py` | Rotas existentes de connections/connection-keys e opening chamam services via ferramentas MCP. | Extrair composição para módulo neutro e adicionar APIs `/v1` reutilizando os mesmos casos de uso, sem importar ferramenta MCP para governar REST. |
| `AgentConnectionsPanel.tsx` | Interface ainda gira em endpoints/perfis, conexão de curta duração e autorização de abertura por uma hora; há rótulos estáticos legados. | Nova jornada usa agente → executor → instalação → workspace → diff/consentimento, sem emissão recorrente manual. |
| `runtime_delivery.py` | Há planner transacional, consumo exclusivo, projeção de observadores e causalidade. | Preservar esses mecanismos. Alterar o destino do despacho não significa reconstruir inbox/handoff. |
| `endpoints_repo.py` | `agent_endpoints`, `runtime_profiles`, `runtime_boot_bindings`, `runtime_execution_grants` e auditoria de configuração já existem. | Extensões referenciam essas entidades. Não criar políticas concorrentes para o mesmo endpoint. |
| Core 0.2.10 | Catálogo, availability v2, installation ref e resolver público existem. NXL continua r3 com manifest `development-partial`. | Usar as APIs existentes; não promover presença no catálogo a READY nem a qualificação operacional. |
| Connector atual | Ainda tem pendências de aprovação, task de decisão, rotação concorrente de attach e recuperação do publicador, conforme CN5. | Integrar por contrato e testes cruzados; nenhum aceite integral por mera importação. |

Fontes: S01–S17 em `08_FONTES_BASELINE_E_DECISOES.md`. O registro do Core contém `claude_attach`, mas a preparação desse modo permanece não qualificada. Não reinterpretar documentos antigos que mencionam “quatro adapters” como quatro modos prontos.

## 4. Arquitetura de destino e dependências de importação

```text
UI / CLI Nexus / MCP HTTP / CLI Connector
                       |
        casos de uso canônicos do Nexus Server
        autenticação → política → operação/outbox
                       |
                 ExecutorPort
                 /           \
 EmbeddedExecutor             RemoteExecutor
      |                           |
 Core no owner de serve       WSS NXL R4
      |                           |
 protocolo nativo             Connector + mesmo Core
      |                           |
 harness local                harness remoto

Ferramentas: harness MCP HTTP → endpoint /mcp do Nexus, sem passar no Connector.
Pi sem MCP HTTP: extensão nativa limitada → casos de uso HTTPS canônicos.
```

### 4.1. Organização concreta a implementar

Os módulos abaixo são caminhos-alvo novos, não alegações de existência. Adaptar o nome somente quando já existir um módulo com a mesma responsabilidade e registrar o mapeamento, sem duplicar serviço.

```text
src/okto_nexus/
  bootstrap/
    dependencies.py       # Deps e composição neutra extraídos de mcp/server
    runtime_host.py       # ownership de EmbeddedExecutor, stores e tasks
  domain/execution/
    keys.py               # chaves de escopo e tipos de identidade
    intents.py            # intenção, invariantes e estágios canônicos
    decisions.py          # proposta íntegra, decisão e causalidade
  application/
    execution_ports.py    # ExecutorPort e repositórios abstratos
    execution_intents.py  # resolve e admissão, sem I/O nativo em UoW
    execution_dispatch.py # outbox, reservas e revalidação após espera
    execution_ingress.py  # receipts/eventos/ACK pós-commit
    executor_inventory.py # projeção/cache, não qualificação duplicada
    execution_leases.py   # autoridade, CAS e revogação
    execution_recovery.py # scans paginados, unknown e recuperação
    execution_decisions.py# decisão canônica e operação de aplicação
  adapters/outbound/execution/
    embedded.py           # converte contratos do Server na API pública Core
    remote.py             # converte mesma operação no NXL compartilhado
    core_history.py       # consulta Journal sem binário/processo
    launch_context.py     # config/env/segredos POR abertura, não por binding
  adapters/inbound/http/
    connections_v1.py     # /v1/connections; respostas diretas
    runtime_v1.py         # /v1/runtime; sem efeito duplicado
    executor_link.py      # endpoint WSS, autenticação própria de upgrade
  adapters/inbound/cli/main.py
  adapters/inbound/mcp/
    registration.py       # tools/resources/instructions usados só via HTTP
  adapters/outbound/sqlite/
    execution_*.py        # UoW canônico, nunca SQL ad hoc nos handlers
frontend/src/
  components/AgentConnectionsPanel.tsx
  components/AgentEndpointSetup.tsx
  components/NativeApprovalInput.tsx
  api.ts
```

Domínio e casos de uso dependem de portas; adaptadores de execução importam o Core. Evitar que o domínio dependa de FastAPI, MCP, subprocess ou classes de providers. O `AdapterRegistry` antigo deixa de carregar classes próprias. Sua eventual fachada temporária só traduz consultas para o catálogo recebido do Core; remover no cutover.

### 4.2. Porta de execução

Definir no Server `ExecutorPort` com operações assíncronas `prepare`, `dispatch`, `inspect`, `reconcile` e `request_shutdown`. `dispatch` recebe `AuthorizedExecution`, não payload JSON cru. Embedded e Remote produzem a mesma categoria de receipt e fatos. O adapter remoto não autoriza; ele transporta autoridade já decidida e reconfirmada. O adapter local não expõe `Popen`, a factory privada ou estado `_sessions` do Core.

Não usar `asyncio.run()` por request HTTP. O owner de serve possui um loop e um registro de producers. Handlers síncronos existentes podem chamar o caso de uso por uma ponte controlada para esse loop; a resposta pode ser 202 e consulta. Não criar uma segunda instância de Core por chamada de status.

O catálogo estático funciona antes de qualquer composição de runtime. `create_runtime()` atual exige candidato e workspace não vazios: **não inventar um candidato fictício só para iniciar Server sem harness**. Discovery utiliza helpers públicos de discovery do Core através de um adapter local de inventário; estes helpers devem ser explicitamente estabilizados no contrato da dependência. Somente após seleção/realização compor uma instância executável.

### 4.3. Composição local por execução

Manter um journal técnico compartilhado do executor embutido e um ledger de slots por instalação, ambos implementados pelo Core e abertos fora do event loop bloqueante. O domínio canônico conserva seu `nexus.db`; não adaptar de imediato todo o UoW do Server para Journal Core, evitando fingir atomicidade entre processo e domínio.

Uma entrada do host por `SessionKey` referencia a instância Core, contexto de abertura, candidato exato, workspace, produtores, pump e obrigações. O callback `environment(PreparedLaunch)` captura contexto exclusivo daquela abertura. Reutilizar uma instância por sessão; não reutilizar por binding um callback fechado sobre a capability da primeira sessão. Instâncias distintas compartilham o ledger para não multiplicar o limite físico.

O Server pode iniciar sem providers e continuar a servir MCP/REST/dashboard e executores remotos. Ausência local aparece no inventário local; não falha a construção global do aplicativo.

## 5. Identidades e escopos — significado obrigatório

| Identidade | Quem a define | Regra |
|---|---|---|
| `server_id` | Instalação canônica persistida | Hostname não é identidade; restauração intencional conserva ID, clonagem ativa não prova ownership. |
| `agent_id` | Domínio existente | Derivado da credencial; payload só confirma igualdade. |
| `connector_id` | Instalação local do Connector | Técnico, sem autoridade sozinho. |
| `executor_id` | Server após registrar executor | Um por local de execução autorizado; runtime local também possui ID. |
| `adapter_id` | Catálogo Core | Mecanismo, não nome de agente; não hardcode no frontend. |
| `candidate_ref` | Core no executor | `nexus-install-v1:...`; identifica alvo local, não conteúdo nem permissão. |
| `build_identity` / fingerprint | Core | Evidência de conteúdo/qualificação; não converter em identidade da instalação. |
| `inventory_revision` | Produtor do snapshot, algoritmo R4 comum | Identifica evidência completa e ordenada; timestamp de publicação é separado. |
| `binding_id` | Server | Liga agente, endpoint, executor, candidato e realização aprovados. |
| `workspace_id` | Domínio canônico | Lógico; não re-hashear IDs legados. |
| `workspace_binding_id` | Server com prova de realização local | Handle de diretório no executor, não path resolvido pelo Server remoto. |
| `session_id` | Server para sessão governada | Não reutilizar um ID de abertura histórica sob novo processo. |
| `native_session_id` / `native_turn_id` | Harness, observado pelo Core | Subordinados ao namespace; não são chaves globais. |
| `operation_id` | Server na resolução/admissão | Estável para intenção, mantido pelo Core. |
| `client_intent_id` | Cliente antes do primeiro POST | Idempotência recuperável quando a resposta com operation_id se perdeu. |
| `request_id` canônico | Server ao ingressar pedido nativo | Diferente do request ID nativo, que pode ser inteiro; guardar ambos. |

Tipos imutáveis mínimos: `ExecutorKey(server_id, executor_id)`, `BindingKey(server_id, executor_id, binding_id)`, `SessionKey(server_id, executor_id, session_id)`, `StreamKey(server_id, executor_id, session_id, stream_epoch)`, `ApprovalKey(server_id, executor_id, binding_id, agent_id, workspace_id, session_id, session_owner_generation, canonical_request_id, kind)`. Não resolver mutação por `next(iter(...))`, primeiro binding, rótulo, path ou concatenação truncada.

`connection_generation`, `session_owner_generation`, `credential_epoch`, `authorization_revision`, `configuration_revision`, `binding_revision` e `inventory_revision` são fatos distintos. O contrato define qual pertence ao hash da intenção e qual apenas impede um canal antigo de executar. Nenhuma geração recebida pode ser descartada e substituída pela sessão local para “fazer passar”.

## 6. Catálogo, instalação disponível e seletor

### 6.1. Fluxo fechado

1. O Core do executor produz `get_runtime_catalog()` e discovery sem lista manual de IDs.
2. Preservar integralmente cada `InstallationCandidate`: executável, script, versão, arquitetura, trust/source, fingerprint, build e installation ref. No Pi, Node + CLI é o candidato; não reconstruir Node isolado.
3. O Core avalia `evaluate_runtime_availability(inventory)` no próprio host. `NOT_PROBED` e `UNQUALIFIED_BUILD` não são READY. Attach continua indisponível.
4. O produtor gera um snapshot R4 com catálogo, availability v2, revisão, sequência de publicação e validade. A projeção não contém paths ou segredos.
5. Server valida origem/escopo/formato e guarda a projeção; não roda seu próprio qualificador sobre um candidato remoto.
6. UI solicita opções para **um executor selecionado**. O envelope `RuntimeOptions` fornece `freshness`; cada `RuntimeOption` fornece `technical_state`, `technical_reasons`, `policy_reasons`, `can_prepare`, `can_bind` e `can_start`. Não criar outro vocabulário de payload no frontend.
7. UI devolve executor, adaptador, candidate_ref, inventory_revision e workspace escolhido. O executor original resolve pelo helper público `resolve_installation` sobre o snapshot apresentado.
8. Diferença de revisão, ref ausente ou ambígua impede apply/start e exige refresh/reseleção. `prepare/open` ainda verifica drift físico depois da resolução.

### 6.2. Regra de elegibilidade

`can_start = formato conhecido AND snapshot atual/fresco AND executor elegível AND candidato presente/qualificado/selecionado/contido AND política do agente permite AND workspace/realização aprovados`.

Para criar proposta ainda sem realização, o Server pode retornar `PREPARATION_REQUIRED` e permitir o passo de preparação/consentimento; isso não habilita `start`. Separar `can_prepare`, `can_bind` e `can_start` evita um único booleano enganoso.

Duas instalações iguais no mesmo host aparecem como duas opções com refs distintas e rótulos fornecidos pelo Core. Um alias/symlink para o mesmo alvo pode ser deduplicado pelo Core. Não reproduzir esse algoritmo em TypeScript. O prefixo de catálogo `mcp` não se torna um adapter de processo: tools-only é um caminho separado.

### 6.3. Projeção remota e privacidade

A revisão R4 inclui uma API de snapshot do aplicativo, fora do `inventory.snapshot` reduzido do NXL r3. Não adicionar availability inteira a um frame com `additionalProperties=false`. Ver contrato exato de `PUT /v1/runtime/executors/{executor_id}/inventory`.

Core version, formato de catálogo, formato de availability, digest da evidência e contagem de registros são validados. IDs novos desconhecidos podem aparecer desabilitados como incompatíveis, nunca carregar módulo recebido. O Server usa os nomes remotos para apresentação, mas só despacha se a revisão do contrato e a capacidade forem compatíveis. Cache não é uma lista editável; atualizações são snapshots autenticados, imutáveis por revisão.

Localidade da referência deve ser validada no envelope. Um hash de path igual em duas máquinas não comprova que o alvo é o mesmo; `candidate_ref` sozinho não incorpora autorização de executor.

## 7. Onboarding e uso recorrente

### Local

Tela do agente → executar neste Server → catálogo/instalação local → pasta aprovada → proposta de vínculo → aprovação agregada → aplicação → iniciar opcionalmente. CLI equivalente: `okto-nexus runtime start <agente-ou-alias>`. Não exigir connection key de uma hora ou recuperar plaintext do hash canônico. A autenticação administrativa local existente autoriza representar o agente; o runtime recebe capability limitada, nunca a chave administrativa.

### Remoto

Tela do agente gera `okto-nexus-connector connect --server <origem-HTTPS> --agent <id>`, sem chave no argv. A CLI pede a chave existente protegida, chama `/me`, registra/reutiliza executor técnico, descobre/seleciona, publica evidência e solicita prepare/apply. A aprovação do projeto ocorre no host que possui a pasta. `--start` é intenção explícita adicional; discovery/importação nunca abre todos os harnesses.

Não exigir listagem de todos os agentes para resolver uma chave. Não rotacionar `nxs_...` só para gerar comando. Chave revogada não volta a valer por renovação de ticket. Um ticket de link não autentica MCP.

### Recorrente e reuso

Usar binding por alias inequívoco; se houver dois executores ou instalações possíveis, apresentar escolha, não priorizar por ordem de lista. Reusar somente sessão viva com mesma realização/configuração, autorização vigente e suporte efetivo. `--new-session` cria outra intenção explicitamente. Prompt inicial após open é **segunda operação identificada**, condicionada ao sucesso de abertura; nunca execução implícita duplicada no Server e no Connector.

## 8. Execução, decisões e recuperação

A sequência normativa de operação é: autenticação → resolução → idempotência → autorização → transação canônica operação/outbox → despacho fora da transação → journal Core → efeito nativo → receipt/observações → ingresso durável → projeções. O client HTTP e o socket podem desaparecer sem apagar operação ou producer.

`SUBMITTED` não é SUCCEEDED; pipe escrito não é aceitação do provider; ACK do evento não é exibição pela UI; turno concluído não é handoff completo; `possible_effect` não é “forced”. Stages do domínio e Core devem ser projetados sem inventar observações.

Aprovação: evento nativo íntegro → pedido canônico com scope/turn/hash → operador autorizado decide com CAS e intenção estável → Server cria UMA operação de aplicação → dispatcher → Core → receipt. UI/CLI apresenta e consulta, não aplica no harness depois do POST. Isso substitui a cadeia híbrida e frágil encontrada no Connector, que deve ser adaptado pelo seu agente.

Se um trabalho ficou `OUTCOME_UNKNOWN`, consultar o mesmo ID. Não mudar executor, reenviar prompt, reabrir processo ou liberar claim para outro agente automaticamente. Reinício consulta o journal sem exigir que o binário ainda exista. Contexto mais novo no storage invalida o antigo; não instalar permissões a partir de uma linha de lease.

O documento de contratos especifica máquina de estados de canal, lane, lease, operação, decisão e ACK. O documento de dados fixa ownership e shutdown inclusive para aberturas tardias e releases pendentes.

## 9. Segurança preservada e simplificação de UX

Simplificação remove trabalho técnico repetitivo, não consentimento real. `allowed_actions=[]` continua vazio. Negação explícita prevalece sobre defaults, catálogo e presença de binário. O agente não aprova sua própria escalada. Um operador pode agir sobre agente-alvo com auditoria separada de `actor` e `subject`, sem criar conta de usuário Nexus.

Managed MCP usa capability de sessão de audiência própria e validação contra estado canônico renovável. O segredo fica estável durante a sessão quando o harness não suporta hot reload; o Server restringe validade/ações em seu armazenamento. Revogação e lease não são contornadas pelo canal MCP. Tools-only com chave canônica mantém política independente do daemon.

Nenhum path remoto entra em `Path.resolve`, `os.stat`, `isdir` ou `Popen` do Server. Nenhum `argv`, plugin, nome de módulo ou env livre vindo do peer vira execução. Core monta os argumentos; Server transmite intenção/refs de realização previamente aprovadas.

## 10. Sequência de implementação e gates

O backlog detalha NS00–NS16. Em paralelo: agente Server extrai bootstrap e constrói domínio/API/UI com fixtures; agente Core publica a revisão de contrato e exemplos públicos; agente Connector conclui CN5 e adota a cadeia de execução R4. Não é necessário esperar toda qualificação para começar migrações ou UI.

A barreira obrigatória é **contrato executável compartilhado antes do primeiro efeito remoto**. Até lá, peers de contrato servem ao desenvolvimento, sem marcar runtime remoto como pronto.

| Gate | Critério |
|---|---|
| G0 — base/documento | Fonte, migrações e contratos definidos; catálogo/UI com fixtures; nenhuma alegação operacional. |
| G1 — Server local | Nexus+Core abre/controla/encerra um runtime qualificado sem app Connector; MCP HTTP e legado preservados; testes negativos passam. |
| G2 — remoto delimitado | Server A sem binários/paths remotos, Connector B e mesmo wheel Core executam ciclo completo com catálogo, intenção, evento, ACK, decisão e recuperação. |
| G3 — escopo completo | TN/J preservados e novos aceites passam nas combinações declaradas; outros providers/attach/SOs ficam explicitamente indisponíveis até suas próprias provas. |

Não conceder G2 por UI estática, callback mock, catálogo importável ou testes do Core isolados. Sem infraestrutura autorizada, conservar `NOT_RUN` e `BLOCKED_EXTERNAL`, entregando o que é independente. Nenhum gate autoriza push, release ou uso de contas de produção por si.

## 11. Entrega exigida ao executor

Código e migrações; crosswalk atualizado; contratos do Core fixados por versão/hash; arquivos novos e removidos; testes com node/camada/comando/exit code; wheels e hashes; runbooks; restrições operacionais; snapshot de decisões públicas e privadas redigidas separadamente. Estados antigos `PASS` não migram automaticamente para código novo.

Nenhum teste de produto foi executado durante a criação deste plano. A validação incluída em `evidencias/VALIDACAO_DO_PACOTE.json` cobre apenas consistência documental, schemas de planejamento, fixtures e grafo de dependências.
