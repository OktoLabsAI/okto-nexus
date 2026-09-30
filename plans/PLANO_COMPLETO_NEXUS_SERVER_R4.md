# Plano completo e unificado — Nexus Server R4

**29/09/2026 · Base: feature/v0.2.0 / 7ed52c2 · Especificação de implementação, não release.**

Este arquivo reúne os oito documentos normativos de leitura. A fonte editável é cada documento numerado; os JSONs de backlog, cenários e contratos estão no mesmo pacote. Não manter esta concatenação como plano divergente.

**17 fases · 85 tarefas · 164 cenários de produto NOT_RUN.** Os 70 requisitos de tarefa, 45 testes TN e 34 cenários conjuntos J do plano R3 estão mapeados. Schema/fixtures deste pacote são exemplos de planejamento; o bundle executável R4 deverá ser produzido no Core.

## Índice

1. [Arquitetura E Plano Mestre](#documento-01)
2. [Contratos Http Nxl E Estados](#documento-02)
3. [Dados Migracao E Recuperacao](#documento-03)
4. [Backlog Execucao](#documento-04)
5. [Testes E Aceite](#documento-05)
6. [Handoff Core Connector](#documento-06)
7. [Rastreabilidade R3](#documento-07)
8. [Fontes Baseline E Decisoes](#documento-08)


---

<a id="documento-01"></a>

**Documento-fonte: `01_ARQUITETURA_E_PLANO_MESTRE.md`**

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


---

<a id="documento-02"></a>

**Documento-fonte: `02_CONTRATOS_HTTP_NXL_E_ESTADOS.md`**

# Contratos de integração — alvo explícito R4

**Status: ESPECIFICAÇÃO A IMPLEMENTAR, não descrição de endpoints já existentes.** As APIs Core citadas como existentes pertencem a `0.2.10.dev0`. Rotas, DTOs e frames R4 deste documento requerem implementação coordenada. Não tornar um mock do Connector a autoridade do protocolo.

## 1. Versões, prefixos e representação

Fixar os identificadores abaixo no pacote de contratos compartilhado:

```text
plan_revision        = nexus-server-unified-r4-2026-09-29
management_revision  = nexus-connections-2026-09-29-r4
protocol_major       = 1
nxl_revision         = nxl-1-agent-centric-http-only-2026-09-29-r4
catalog_format       = 1 (atual)
availability_format  = 2 (atual; candidate_ref identifica instalação)
executor_snapshot    = 1 (novo envelope do aplicativo)
```

A revisão r3 atual permanece imutável, com seus vetores e manifest. O Core publica R4 em diretório/revisão separado ou mecanismo de bundle explicitamente versionado, mantendo a leitura dos receipts históricos. O Server não baixa schemas de `main` e não copia enums autorais. Durante a integração inicial, exigir mesma revisão e wheel/hash compatível fixado nos dois hosts. Um Connector r3 recebe `VERSION_INCOMPATIBLE` antes de novo efeito, com instrução de atualização; MCP HTTP e dados legados não dependem dessa negociação.

A alteração é necessária: r3 admite payload genérico, não possui confirmação explícita de attach/reconcile, torna owner generation opcional e não especifica payload completo de abertura remota. Além disso, o alvo de steer não pode obrigar ID de turno nativo para um adapter cujo Core usa run sem ID. Essas são lacunas de contrato, não autorização para modificar os codecs no Server.

**Prefixo:** `/v1` nas rotas novas. Sucesso é objeto JSON direto. Falha: `{ "error": { "code", "stage", "message", "possible_effect", "retry_safe", "operation_id", "action" } }`; campos nulos admitidos conforme schema. `/api/v1` legado preserva `{ok,data/error}`. Não ter dois handlers canônicos que executam a mesma operação. APIs legadas adaptam entrada/saída e chamam o mesmo caso de uso.

Responder `X-Nexus-Connections-Revision` em toda resposta `/v1`; cliente envia a revisão depois de consultar protocolo. Em `/v1`, usar somente bearer em header para credenciais. Query string com chave é rejeitada nessas rotas. Compatibilidade de extração antiga no `/mcp` é preservada, com geração de novas configurações por header e redaction dos acessos existentes; não é uma migração silenciosa de credenciais.

IDs de fio novos: strings 1–160 caracteres, não truncadas. Native request ID é JSON original string ou inteiro limitado, guardado dentro da proposta; não convertê-lo na chave canônica global. Refs `nexus-install-v1:` e hashes `sha256:` conservam seu prefixo/versionamento. JSON rejeita chaves duplicadas, NaN/infinito e excesso de profundidade/bytes antes do JCS. `operation_id` externo legado de tamanho diferente permanece consultável pela rota de compatibilidade, não admitido como novo ID R4.

## 2. Autoridade e credenciais

### 2.1. Principais separados

`AuthenticatedPrincipal` é criado na fronteira autenticada e contém `server_id`, `actor_agent_id`, `authentication_source`, epoch e permissões verificadas. Operação que representa outro agente registra também `subject_agent_id` e exige permissão existente de operador. Não aceitar `operator=true` do payload.

`LinkPrincipal` deriva do ticket: servidor, executor, binding, agente, credential epoch, audiences/scopes, expiry e conexão autorizada. `ChannelContext` acrescenta `connection_id` opaco, `connection_generation` e serial de socket local. Todo frame herda essa origem interna. Campos do frame são assertions a comparar, inclusive ACK, reconcile, approval e detach.

### 2.2. Tickets operacionais

Manter chave canônica do agente apenas em hash no Server. Ticket operacional usa bytes criptograficamente aleatórios, hash persistido, TTL inicial 600 s e escopo de binding/executor. Permitir emissão automática a 70% da validade, com jitter/single-flight, enquanto chave e binding continuam válidos. Expiração de ticket não é renovação da lease de trabalho.

Audiência de ticket: `nexus-executor-control`. Escopos possíveis, explicitamente emitidos: `link:connect`, `lane:attach`, `inventory:publish`, `realization:publish`, `receipt:publish`, `history:read`, `lease:request`. Emitir só os necessários ao papel. Ticket inicial de executor sem binding concede apenas inventory/realization bootstrap para o agente que registrou o executor; não admite runtime/lane. Não existe chave mestra de máquina.

Consumo de attach é vinculado ao request/connection: mesma tentativa pode consultar a confirmação; ticket já vinculado a outra conexão não autoriza takeover. Reconexão obtém ticket novo. Uma lane de outro agente precisa de ticket obtido pela chave daquele agente. Receber catálogo não prova direito sobre todas as lanes.

### 2.3. Capability MCP HTTP

Audiência separada `nexus-mcp-session`, token opaco diferente do ticket. Escopo contém agente, workspace, binding, sessão, configuração, owner e ações de domínio permitidas. `tools/call` é teto de protocolo, não autorização para qualquer tool. O guard de cada caso de uso aplica suas próprias permissões e claim.

Capability de sessão reservada pode ser emitida antes do spawn para compor o cliente, mas efeitos produtivos só são permitidos quando a sessão e sua lease estão ativas. Guardar o segredo em armazenamento local adequado do executor, não no prompt/argv/Server plaintext. Na resposta de emissão, `Cache-Control: no-store`.

O token pode permanecer estável durante a sessão; o Server renova/restringe validade canônica enquanto a lease é renovada legitimamente. Não pressupor hot reload do harness. Revogação impede novas chamadas imediatamente no Server; partição é limitada pelo prazo do executor. Não aceitar ticket NXL, EPT ou chave administrativa como capability de sessão.

### 2.4. Resposta perdida na emissão de segredo

Nunca recuperar plaintext a partir de hash. GET de ticket/capability já emitido devolve metadados, não o segredo. Se a resposta inicial se perdeu, o cliente solicita substituição identificada por novo `credential_request_id`, citando o ID anterior; o Server invalida o derivado anterior e emite outro somente dentro da mesma autorização e enquanto ainda não foi instalado/ativado em uma sessão. Isso é emissão de um derivado, não rotação da chave canônica, e não gera processo ou turno.

Para capability já instalada, não invalidar automaticamente por um timeout do cliente: conservar sua validade e seguir a política de renovação servidor-side. Se o segredo realmente foi perdido pelo executor, bloquear nova realização e exigir recuperação de configuração compatível; nunca reiniciar trabalho incerto para obter outro token. Respostas de replay sem material retornam `CREDENTIAL_MATERIAL_UNAVAILABLE`, com identificação do derivado e recuperação permitida. Ticket novo pode ser solicitado automaticamente sob chave canônica vigente, mas o ticket anterior não volta a ser validado para nova conexão.

Precisão do DTO de erro de capability: `CREDENTIAL_MATERIAL_UNAVAILABLE` inclui `capability_id` e `recovery_allowed` no objeto `error`, sem segredo. Esses campos opcionais estão declarados em `ErrorBody`. `recovery_allowed=true` informa que uma nova requisição de substituição pode ser avaliada; não reserva autorização nem dispensa revalidação transacional. Se o envio da abertura já puder ter instalado configuração, ou existir histórico de lease, a substituição automática é recusada. Renovação de validade de capability estável acompanha o commit de aplicação legítima da lease, não o simples envio do grant.

## 3. DTOs canônicos novos

Os nomes abaixo são fixados para a implementação; transportar por dataclass/Pydantic equivalente sem mudar sua semântica. Modelos do Core continuam sendo consumidos, não redefinidos localmente com o mesmo nome.

### 3.1. `ExecutionScope`

```text
server_id, executor_id, binding_id, agent_id, workspace_id,
workspace_binding_id, session_id: ID
session_owner_generation, authorization_revision,
configuration_revision, binding_revision, credential_epoch: inteiro >= 1
```

`AuthorizedExecution` agrega scope, operação imutável, `grant_id`, `lease_id/lease_serial` instalados, canal esperado e token da reserva. Ao construir `ExecutionContext` para o Core, usar o deadline monotônico já instalado no executor, nunca recalculá-lo de “agora + duração” a cada mensagem. Ações vêm do grant aprovado; vazio permanece vazio.

### 3.2. `ExecutorInventorySnapshot`

```text
snapshot_format_version = 1
server_id, executor_id, producer_instance_id: ID
publication_sequence: inteiro >= 1, crescente e persistido por executor
inventory_revision: sha256 JCS(evidence) completo, não truncado
core_version: string
catalog: RuntimeCatalog serializado publicamente (format_version = 1)
availability: AvailabilityReport.to_dict() (format_version = 2)
evidence: lista ordenada de CandidateEvidence
observation_age_ms: inteiro 0..300000
```

`CandidateEvidence`: `adapter_id`, `candidate_ref`, `content_fingerprint`, `build_identity` ou null, versão/arquitetura ou null, trust/source, suporte/plataforma, estado técnico/razões e capability report **somente quando observado**. Não transmitir executável, launch_script, HOME, nome de variável de segredo, token ou classe Python.

Para o digest, incluir versões de formato/Core e todos os campos técnicos que possam alterar seleção/realização; excluir sequence, producer_instance_id, observation_age, nomes apenas cosméticos e horário de publicação. Ordenar por `(adapter_id,candidate_ref)` e ordenar listas que representem conjuntos. Não retirar conteúdo do hash porque a versão textual não mudou.

TTL operacional inicial: 120 s após recebimento, reduzido por `observation_age_ms`; o Server usa seu monotônico para frescor do processo. Após restart, nenhum deadline monotônico persistido é restaurado: exigir nova publicação/validação. `publication_sequence` impede que snapshot antigo com digest válido substitua o atual. Mudança de instância produtora exige reconciliação do canal, não aceitar sequence 1 cegamente.

`candidate_ref` é local ao inventário do executor. Duas máquinas podem derivar refs iguais para paths iguais; validar executor no envelope. O Server não deduz os paths do hash e não os resolve.

### 3.3. `BindingProposal`

Campos exigidos: `proposal_id`, `proposal_revision`, `expires_at`, `server_id`, `executor_id`, `agent_id`, `binding_id`, `endpoint_id`, `profile_id`, `workspace_id`, `workspace_binding_id`, `adapter_id`, `candidate_ref`, `inventory_revision`, `realization_ref`, `realization_revision`, `authorization_revision`, `configuration_revision`, `required_approvals`, `diff`, `can_apply`.

`local_realization_ref` é emitida pelo executor depois de validar pasta/candidato/configuração e consentimento local. A publicação autenticada registra essa prova e recebe do Server a `realization_ref` canônica; o executor conserva o mapeamento entre ambas. O Server guarda somente refs, revisões e escopo, não o alvo físico como autoridade. Uma repetição idempotente retorna o mesmo mapeamento. Não criar um workspace remoto resolvendo path em A.

### 3.4. `IntentResolution`

Campos exigidos: `client_intent_id`, `intent_id`, `operation_id`, `session_id`, `reuse`, `scope`, `semantic_intent`, `intent_hash`, `resolution_revision`, `expires_at`, `can_submit`, `blockers`, `dispatch_owner="server"`.

Resolver pode reservar IDs e proposta durável, mas **não cria processo, turno ou outbox de efeito**. Repetir client_intent_id com mesmo conteúdo retorna a resolução; mudar conteúdo retorna `OPERATION_CONFLICT`. Resolution expirada exige nova resolução vinculada explicitamente, nunca executar dados aprovados sob outra revisão.

### 3.5. `OperationView`

Campos: `operation_id`, `client_intent_id`, `scope`, `action`, `intent_hash`, `admission_state`, `executor_stage`, `possible_effect`, `retry_safe`, `receipt_revision`, `last_observed_at`, `error`, `follow_up_operation_ids`.

`admission_state`: `RESOLVED`, `ACCEPTED`, `DISPATCH_PENDING`, `DISPATCHED`, `RECONCILING`, `RESOLVED_TERMINAL`. `executor_stage` é o estágio real do receipt Core, ou null antes de haver receipt. Não usar `SUCCEEDED` no estágio do executor só porque o POST teve 202.

### 3.6. `DecisionView`

Campos: `decision_id`, `client_intent_id`, `ApprovalKey`, `request_hash`, `request_revision`, `proposal_decision`, `native_decision`, `actor_agent_id`, `subject_agent_id`, `canonical_state`, `native_operation_id`, `native_stage`, `possible_effect`, `retry_safe`, `response_digest`, `expires_at`.

Estados canônicos: `PENDING`, `CONFIRMED`, `DENIED`, `EXPIRED`, `CANCELLED`. Aplicação nativa é outro fato: `NOT_DISPATCHED`, `DISPATCH_PENDING`, `SUBMITTED`, `APPLIED_OBSERVED`, `REFUSED_BEFORE_EFFECT`, `OUTCOME_UNKNOWN`. Somente observação explícita permite `APPLIED_OBSERVED`. Não devolver apenas `applied=true` como autorização suficiente.

## 4. Rotas HTTP — contrato fechado

Todas são novas ou adaptações a implementar; o Nexus inspecionado não implementa este conjunto `/v1`. A tabela fixa a responsabilidade; os exemplos/schemas de planejamento no pacote não são um SDK de produto publicado.

| Método e rota | Principal | Entrada principal | Saída e efeitos |
|---|---|---|---|
| GET `/v1/connections/protocol` | Público, sem dados privados | Nenhuma | 200 com management_revision, NXL aceito, formatos e limites; não enumera agentes/executores. |
| GET `/v1/connections/me` | Chave canônica | Header bearer | 200 identidade autenticada, permissões e revisões; lookup indexado. |
| POST `/v1/connections/executors:register` | Chave canônica | client_intent_id, connector_id, label aprovado, capabilities de controle declaradas | 200/201 executor_id canônico, bootstrap ticket limitado e estado; não cria agente ou binding privilegiado. |
| PUT `/v1/runtime/executors/{id}/inventory` | Ticket `inventory:publish` | ExecutorInventorySnapshot | 200 revision/sequence/validade aceitas; transação idempotente; 409 stale/conflict; nenhum spawn. |
| GET `/v1/runtime/executors/{id}/inventory` | Operador ou agente com vínculo autorizado | Cursor/revisão opcional | Snapshot filtrado e freshness; nada de paths; acesso de outro agente recusado. |
| POST `/v1/runtime/executors/{id}/inventory:refresh` | Operador ou agente autorizado | client_intent_id | 202 pedido de refresh ao executor; não faz scan remoto por conta própria. |
| POST `/v1/runtime/executors/{id}/realizations` | Ticket `realization:publish` | Prova de root local e candidato/revisão, refs de perfil sem secrets | 200/201 realization_ref canônica associada ao handle local; processo não inicia. |
| POST `/v1/connections/bindings:prepare` | Chave do agente ou operador autorizado | client_intent_id, executor_id, adapter_id, candidate_ref, inventory_revision, realization_ref, workspace_id/hint lógico, alias | 200 BindingProposal; 409 stale/ambiguidade; nenhuma concessão implícita. |
| POST `/v1/connections/bindings:apply` | Mesmo principal + prova de approval quando exigida | client_intent_id, proposal_id/revision, approved_diff_hash | 200 BindingView aplicado + revisões; CAS em endpoint/binding/profile; sem spawn. |
| GET `/v1/connections/bindings/{id}` | Sujeito ou operador | Escopo resolvido no Server | 200 estado e refs; não revela chaves/tokens. |
| POST `/v1/connections/bindings/{id}/ticket` | Chave do mesmo agente | client_intent_id, credential_request_id, audience e scopes pedidos | 200 ticket, ticket_id, expires_in, epochs e executor_id; intersectar política. |
| GET `/v1/agents/{agent_id}/runtime-options` | Próprio agente ou operador | executor_id obrigatório, workspace_id opcional | 200 catálogo/availability e can_prepare/can_bind/can_start + razões; não tem enum frontend. |
| POST `/v1/runtime/intents:resolve` | Agente/operador | client_intent_id, intenção, binding, workspace_binding, session quando existente, new_session, payload | 200 IntentResolution sem execução; 409 conflito/ambiguidade; guardar intenção antes de responder. |
| GET `/v1/runtime/intents/{client_intent_id}` | Mesmo ator+escopo | Consulta | 200 resolução e OperationView associado ou 404 consistente; não resolve nova intenção. |
| POST `/v1/runtime/operations` | Mesmo sujeito/operador | client_intent_id, operation_id, resolution_revision, intent_hash | 202 após commit de operação+outbox; 200 replay idêntico conhecido; 409 hash/revisão conflitante. Só este comando admite efeito. |
| GET `/v1/runtime/operations/{id}` | Próprio sujeito, ticket history escopado ou operador | Consulta | 200 OperationView/receipt; não exige runtime ou binário local. |
| POST `/v1/runtime/operations/{id}/receipts` | Ticket receipt:publish escopado | Receipt Core íntegro + source revision | 200 aceite durável ou 409 conflito; **não despacha** operação. Via WSS operation.receipt tem o mesmo caso de uso. |
| GET `/v1/runtime/sessions/{id}` | Sujeito/operador | executor_id se necessário | Estado composto; ausência de handle != STOPPED. |
| POST `/v1/runtime/sessions/{id}/capability` | Próprio agente com sessão/resolução válida ou operador representando | binding_id, audience MCP/nativa, actions pedidas, capability_request_id idempotente | 200 capability_ref, segredo uma vez/no-store, expires_in e audiência específica. `nexus-mcp-session` serve MCP HTTP; `nexus-native-session` serve somente as ações nativas não MCP. Nunca intercambiar tokens. |
| POST `/v1/runtime/approval-decisions` | Operador ou proof de operador escopado; chave do agente sozinha não basta em escalada | client_intent_id, ApprovalKey, expected_revision, request_hash, decision approve/deny, cas_token, response opcional | 202 DecisionView CONFIRMED e operação nativa na outbox; 200 replay da mesma decisão; 403/409 recusas. Não aplicar nativo na CLI. |
| GET `/v1/runtime/approval-decisions/{id}` | Ator autorizado/sujeito com leitura limitada | Consulta | 200 DecisionView; sem resposta sensível bruta. |
| POST `/v1/runtime/native-actions` | Capability `native-actions` limitada à sessão | action_id, scope, action context/claim/complete, payload tipado | Caso de uso canônico idempotente; sem MCP envelope, sem texto livre interpretado. |
| GET `/v1/runtime/executors/{id}/link` | Ticket link:connect | Upgrade WebSocket, subprotocolo nxl.v1 | Negociação R4 e registro de conexão; autenticação de WebSocket própria, sem fallback operador do middleware HTTP. |

**Resolução da diferença com o Connector atual:** `IntentResolution` do cliente passa a ler `scope` completo; `/approval-decisions` deixa de retornar bool como informação suficiente; `BindingProposal` incorpora executor, instalação e realização; CLI start/submit não chama Core diretamente; receipt usa a rota própria. Essas mudanças pertencem ao agente Connector e constam de `06_HANDOFF_CORE_CONNECTOR.md`. O Server não deve preservar o fluxo defeituoso duplicando efeitos.

### 4.1. Exemplo de fluxo remoto sem ambiguidade

```text
Connector CLI: grava client_intent_id=ci_A no seu journal de comandos
POST intents:resolve(ci_A, runtime.start, binding_B)
Server: reserva session_S/op_OPEN; devolve resolução R1; nenhum processo
POST operations(ci_A, op_OPEN, R1, hash_H)
Server: commit canônico + outbox; 202
Server dispatcher → Connector: operation.submit(op_OPEN, runtime.open)
Connector: resolve instalação/realização local → solicita lease inicial
Server: lease.granted correlacionada
Connector/Core: prepare → open(op_OPEN, SessionKey S, contexto completo)
Connector → Server: receipt(op_OPEN) + eventos duráveis
Server: ingresso/ACK → OperationView
CLI: consulta ci_A/op_OPEN; não inicia outro runtime
```

Prompt fornecido no start produz `op_TURN` separado, com parent `op_OPEN`; o Server somente libera sua outbox após prontidão comprovada. Reuso devolve sessão compatível existente e não cria open adicional; `new_session=true` cria intenção distinta autorizada.

## 5. NXL R4 — delta obrigatório sobre r3

A fonte executável continua no Core. O arquivo `contratos/nxl-r4-delta.json` lista mudanças normativas para seu agente; não é permissão para manter uma segunda implementação no Server. O manifesto atual r3 tem status `development-partial`; preservar esse fato no baseline, sem confundir o campo histórico `core_version` do manifest com a versão atual da biblioteca.

### 5.1. Envelope e hash

Para efeitos, exigir todos os IDs/revisões de `ExecutionScope`, `connection_generation`, `operation_id`, `intent_hash`, `action`, `payload` e `grant_id`. `session_owner_generation` deixa de ser opcional. `grant_id` referencia uma autorização instalada via lease correlacionada; não é um bearer independente ou fonte de permissões autodeclaradas.

Usar o canonicalizador/hash público do Core para semântica. O intent inclui configuração e alvo; exclui ticket, número de envio, instante de lease e geração de conexão. Não alterar hashes históricos de R3. Se o delta mudar representação semântica, seu domínio/versão de hash deve ser distinguível; receipts R3 continuam interpretados pelo decoder R3 para história.

Cada verbo possui payload fechado, `additionalProperties=false` e limite 64 KiB:

| action | Payload exigido / restrições |
|---|---|
| runtime.open | adapter_id, candidate_ref, inventory_revision, realization_ref/revision, profile_revision, mode=managed, model opcional. Proibir executable/argv/env/path/target_pid remoto. |
| turn.submit | text, delivery_id opcional e referências autorizadas. Não incluir scripts de execução. |
| turn.steer | text; expected_turn_id quando o Core declara alvo nativo. Targeting sem ID somente se capability efetiva do Core permitir current-run; ausência não é licença para escolher qualquer turno. |
| turn.interrupt | Motivo limitado; target correlacionado conforme capacidade. Não fabricá-lo a partir do primeiro turno. |
| runtime.close | razão e política dentro dos limites aprovados; não PID nem sinal livre do cliente. |
| approval.decide | canonical_request_id, decisão accept/decline/cancel confirmada, proposta operacional íntegra, decision_id/revision, response_digest. |
| input.provide | Os campos correlacionados acima + resposta tipada ou ref autorizada entregue de forma protegida. Core valida pedido original e tipo; não usar prefixo da decisão para inferir input. |

Metadata de targeting deve ser publicada pelo Core; Server/UI não mantêm regra `if adapter == codex/pi` para autorizar. R4 permite representar explicitamente ausência de turno nativo, e os reducers recusam combinações incompatíveis antes da escrita.

### 5.2. Frames novos e alterados

| Frame | Alteração normativa |
|---|---|
| hello/welcome | Adicionar link_attempt_id/connection_id, revisão HTTP, formatos de snapshot aceitos e capacidades de controle efetivas; welcome não significa lanes/sessões READY. |
| binding.attach | Incluir attach_request_id, expected_connection_generation, configuração e token de tentativa. Ticket continua sensível. |
| **binding.attached** | Novo ACK do Server após validar ticket/escopo e registrar lane; devolve attach_request_id, connection_id/generation, agent/binding/epochs/revisions, expires_in. Só este ACK conclui attach; write no socket não conclui. |
| binding.detach | Exigir scope/canal e razão; fechar concessão em memória antes de I/O; não concede controle de outro agente. |
| reconcile.request/report | Incluir reconcile_id, connection_id/generation e páginas/cursosres. Reporta receipts, claims, stream watermarks e fatos de ownership separados. |
| **reconcile.accepted** | Novo ACK canônico do Server com reconcile_id, próxima recuperação pendente e readiness autorizada por sessão/lane. Falha de storage não é report vazio. |
| lease.renew | Adicionar request_id não reutilizável, grant_id, expected lease_serial, configuração/owner/conexão e finalidade initial/renew/reconnect; captura monotônico t0 no executor antes do envio. |
| lease.granted | Correlacionar request_id; devolver lease_serial crescente, grant_id, scope/revisões completos, allowed_actions, valid_for_ms <=120000. Emissor é o Server. |
| **lease.applied** | Novo recibo do executor de aplicação no Core, com request_id, serial e scope; para abertura inicial, indica contexto instalado antes do open. Não confundir com processo pronto. |
| operation.submit/receipt/query | Scope completo e schemas por verbo; query não autoriza reexecução. Receipt pode ser histórico e mantém hash original. |
| event.batch/event.ack | Acrescentar connection_id/generation ao envelope R4; evento mantém identidade independente de reconexão e sequence/epoch estáveis. ACK pós-commit contíguo. |
| approval.request | Notificação de pedido; separar proposta operacional íntegra de representação para UI. Scope completo, expiry, request_hash/revision e tipo administrativo/nativo. |
| approval.decision | **Somente notificação da decisão canônica. Não gera aplicação adicional.** Efeito nativo usa exatamente a operação approval.decide/input.provide já admitida. |
| inventory.snapshot/delta | Snapshot técnico completo utiliza HTTP versionado nesta revisão; frames NXL antigos servem apenas projeção reduzida/hints quando negociados. Não alojar campos extras de availability neles. |
| heartbeat | Atividade de canal apenas; não renova lease de trabalho. |
| error/goaway | códigos de incompatibilidade, capacidade, escopo, estado/erro tipado; nunca incluir ticket/hash de chave ou raw response de operador. |

### 5.3. Máquina de estados do canal

```text
DISCONNECTED → AUTHENTICATING → NEGOTIATING → RECONCILING
             → CONTROL_READY → DRAINING / DISCONNECTED
```

`CONTROL_READY` exige contrato válido, geração obtida por CAS, ingress journal disponível e reconcile aceito. Lane pode continuar `ATTACHING`; sessão pode continuar `LEASE_PENDING`. Server não despacha trabalho produtivo para lane/sessão não pronta. Exceção de bootstrap explicitamente delimitada: `runtime.open` pode ser entregue a uma lane ADMITTED com sessão `OPEN_AUTHORIZED_PENDING_LEASE`; esse comando permite apenas resolver a realização e solicitar a lease inicial. O Connector não chama prepare/open do Core nem produz spawn antes de instalar a concessão correlacionada e emitir lease.applied. turn.submit/steer e decisões permissivas continuam aguardando lease aplicada e readiness real. Essa exceção não concede prazo ou ações por default. No início de reconnect, invalidar serial de socket anterior antes de aceitar tráfego novo. Operação já admitida permanece consultável; não é automaticamente reenviada como efeito.

Lane: `PENDING → ATTACHING(token/epoch) → ADMITTED → FENCED/EXPIRED/DETACHED`. Rotação fecha a prova antiga em memória; task antiga tem token próprio; seu término agenda o estado desejado atual, mas não marca nova epoch como pronta. O Server aceita ticket atual e emite ACK da mesma tentativa. Expiração de ticket limita admissão/renovação; não matar todos os agentes por revogar um.

### 5.4. Lease sem relógios compartilhados

No executor, antes do request, capturar `t0 = monotonic()`. Server concede duração <=120000 ms baseada no tempo de emissão e em sua própria política/expiração. Executor aplica `deadline = t0 + valid_for_ms/1000`. Atraso de ida/volta consome orçamento; se resposta chegar tarde, recusar/renovar sem executar. Não transmitir timestamp monotônico entre máquinas. Server guarda sua própria validade; não compara diretamente clocks monotônicos de hosts diferentes.

Mapear request_id para t0 uma única vez; replay do mesmo grant reutiliza esse t0 e não estende deadline. Reboot perde o t0 e exige nova autorização. A serial da lease aumenta por concessão confirmada; mensagem antiga, owner diferente ou configuração divergente não altera contexto. Renovação/reconnect chama `Core.renew_lease(SessionKey, ExecutionContext, expected_connection_generation=...)` e aguarda sua evidência antes de tornar a sessão produtiva. Uma linha durável SUPERSEDED impede o contexto anterior; ela não contém permissões para importar automaticamente.

Contenção autorizada — interrupt, close e resposta estritamente negativa — preserva semântica do Core após lease produtiva vencer, mas não amplia `allowed_actions`. Shutdown interno proprietário é outra trilha, não `containment=true` enviado pelo peer.

## 6. Idempotência e resultados possíveis

### 6.1. Intenção HTTP

A chave de idempotência do comando é `(server_id, authenticated_actor, client_intent_id)`. Guardar digest do corpo semântico completo e escopo. Uma nova tentativa de transporte envia a mesma chave. Se ID existia com corpo diferente, 409 antes de operação/outbox. Cliente grava essa chave antes do POST; sem isso, a consulta após resposta perdida é impossível.

`GET intents/{client_intent_id}` resolve operation_id quando a resposta inicial se perdeu. Não retornar zero efeitos de um ReadTimeout/5xx genérico. O Server só marca `retry_safe=true` quando sua transição comprova que nada foi admitido/executado e explica qual ação pode ser repetida; autorização para novo ID é separada.

### 6.2. Outbox e execução

Uma linha outbox corresponde à operação, não à tentativa de socket. Reservar tentativa por CAS com deadline, sem I/O dentro da transação. Antes do efeito, revalidar contexto, revisão, lane e resolução. `POST receipts`/WSS receipt ingressa fatos sobre uma operação existente e hash igual; receipt estrangeiro ou sem admissão canônica vai para quarentena/erro, não cria trabalho retroativamente.

Quando send falha após possível entrega, marcar despacho para **consulta**, não retransmissão cega. Resposta Core idempotente permite obter receipt da operação; não requer novo turno. Novo efeito só se a semântica do Core comprovar não envio e houver nova intenção explicitamente autorizada conforme o contrato.

### 6.3. Eventos e ACKs

Chave: `(server_id, executor_id, session_id, stream_epoch, sequence)`. Server valida scope/canal, tamanho, continuidade e hash. Duplicata com mesmo conteúdo é idempotente; mesmo sequence com hash diferente é conflito. Gap não recebe watermark além da última sequência contígua persistida. Eventos posteriores podem ser guardados sob limite para recuperação, sem fabricar o trecho ausente.

ACK é produzido após COMMIT do ingresso. Quando o COMMIT falha, nenhum ACK. Quando COMMIT sucede e ACK se perde, retransmissão do evento é aceita sem repetir efeito ou projeção. UI offline não bloqueia ACK. Receiver, persistência e controle usam quotas/budgets diferentes; saturação de texto não ocupa toda capacidade de interrupt/revoke/ACK.

No Connector/Embedded bridge: `remote_acked_through` e `core_ack_applied_through` são distintos. A espera do lote fixa `target=batch[-1].sequence`; ACK1 satisfaz replay1 e não lote2. Erro ao aplicar ACK no Core conserva obrigação e retry coalescido; reconexão assegura task viva mesmo sem novo evento. Server não compacta dados críticos só porque foram enfileirados no frontend.

## 7. Aprovação — fluxo único, sem aplicação dupla

### 7.1. Ingresso

Evento nativo autenticado contém a proposta que o Core já correlacionou. O Server guarda uma cópia operacional imutável, valida campos e seu request_hash, e produz uma cópia de apresentação redigida. Hash/digests de correlação não são credenciais; redaction de secrets não pode substituir o hash operacional por `[redacted]`.

Scope completo: Server/executor/binding/agente/workspace/sessão/owner/turno/request nativo + canonical_request_id. Receber mesmo pedido de outra execução não sobrescreve o original. Native IDs de dois Servers/sessões podem coincidir sem colisão.

### 7.2. Decisão e aplicação

1. UI ou CLI envia proposta `approve`/`deny`, client_intent_id, CAS/revision e proof do operador existente.
2. Server valida autoridade humana exigida, pedido vigente, scope/hash/turno e capacidade. Chave do agente que transporta a proposta não concede autoridade de aprovador.
3. Em UMA transação, confirmar decisão canônica, criar operation_id de aplicação e outbox, com vínculo ao pedido.
4. Responder 202/DecisionView. A aplicação nativa ainda pode estar pendente.
5. Dispatcher envia somente a operação canônica `approval.decide` ou `input.provide`. Traduzir approve→accept, deny→decline/cancel conforme tipo validado; não inferir ação por `startswith`.
6. Connector valida namespace, obtém SessionKey exata e chama Core com argumentos nomeados. Proposta operacional não passa pelo redactor de UI.
7. Receipt entra no mesmo ingresso de operação. Core SUBMITTED não comprova que provider agiu. UI mostra fatos distintos.

`approval.decision` de notificação não aplica novamente. A rota HTTP não devolve um bool para instruir a CLI a chamar o Core por fora. Esse é o ajuste coordenado que elimina a ordem/ownership híbridos das revisões anteriores.

### 7.3. Cancelamento, segredo de input e recuperação

Cancelar o request HTTP não cancela transação/producer já admitido. Repetir client_intent_id consulta DecisionView. Duas interfaces com decisões diferentes disputam CAS; só uma confirma. Uma decisão confirmada não volta a PENDING por erro da aplicação nativa.

Não persistir resposta sensível de input em logs ou no journal técnico; guardar digest e referência no domínio. Para este escopo, a resposta bruta é mantida somente em memória protegida do produtor, com TTL do pedido. Se houver crash antes de entrega e nenhum store sensível persistente qualificado estiver configurado, reportar `AUTHORIZED_INPUT_UNAVAILABLE`: exigir fornecimento explícito do mesmo conteúdo/novo fluxo autorizado, sem inventar input nem declarar recuperação automática pós-crash. Isso é um limite explícito; não criar um serviço de segredos novo como dependência implícita. Resultado de possível escrita continua consultado pelo receipt Core, não reenviado.

Um pedido administrativo sem sessão gerenciada termina no CAS do domínio. Marcar esse tipo explicitamente no registro; sessão nativa ausente não é motivo para convertê-lo em administrativo silenciosamente.

## 8. Erros e códigos de status

401: identidade/ticket/capability inválida. 403: scope/ação/autoridade negada. 404: recurso inexistente após autorização de leitura. 409: ID/hash conflitante, CAS obsoleto, inventário stale, ambiguidade. 422: corpo/tipo/forma inválida antes da admissão. 429: capacidade não disponível antes de aceitar, com retry policy. 503: dependência indisponível; não afirmar ausência de efeito se a operação já foi admitida. 202: operação durável consultável, não sucesso nativo.

Erros novos de aplicativo: `INVENTORY_STALE`, `INSTALLATION_REF_NOT_FOUND`, `INSTALLATION_REF_AMBIGUOUS`, `LANE_NOT_READY`, `EXECUTOR_NOT_READY`, `RECONCILIATION_REQUIRED`, `APPROVAL_AUTHORITY_REQUIRED`, `AUTHORIZED_INPUT_UNAVAILABLE`, `DISPATCH_OWNER_MISMATCH`. Acrescentar ao bundle quando atravessarem NXL; não converter todos em UNKNOWN. Preservar CoreError `possible_effect/retry_safe/stage/operation_id` e manter mensagem de diagnóstico separada do código.

## 9. Interfaces existentes versus alvo

| Ponto | Existente observado | Alvo decidido |
|---|---|---|
| HTTP Server | `/api/v1`, envelope `ok/data` | Preservado; novo `/v1` direto tem handler separado e caso de uso comum. |
| HTTP Connector | `/v1`, DTOs parciais e bool para approval | Atualizar para DTOs R4 completos e consulta idempotente. |
| Native runtime local | Server contém classes próprias | Core público no EmbeddedExecutor. |
| Remote runtime.open | Enumerado no schema r3, ainda indisponível no Connector | Payload/lease/realização fechados e dispatcher Server único. |
| Catálogo | Core API publicada | Consumir exatamente; UI sem lista paralela. |
| Snapshot | Availability v2 existe; publicação ainda não qualificada | HTTP snapshot R4 com scope, revisão completa e TTL. |
| Lane ready | Write de attach tratado como prontidão em partes do Connector | ACK binding.attached explícito e token/revisão corrente. |
| Reconcile | r3 report limitado | Páginas/ACK/correlation e histórico sem provider. |
| MCP | HTTP existente + stdio ainda no código do Nexus | HTTP preservado; stdio removido sem shim. |

Tudo nessa coluna “Alvo” é trabalho especificado, não capacidade já testada entre os produtos.


---

<a id="documento-03"></a>

**Documento-fonte: `03_DADOS_MIGRACAO_E_RECUPERACAO.md`**

# Dados, migração, lifecycle e recuperação

**Status: desenho R4 a implementar.** Manter o SQLite e os repositórios do Nexus. Este documento não autoriza executar SQL em base do usuário, apagar estado incerto ou reiniciar processos reais durante o planejamento.

## 1. Duas persistências, fatos diferentes

O **banco canônico do Server** guarda agentes, permissões, workspaces, endpoints, handoffs, decisão de execução, outbox e ingresso durável dos fatos remotos/locais. O **journal técnico do Core** guarda admissão do executor, possíveis efeitos nativos, receipts, eventos, claims de sessão, fences e slots.

No executor local, ambos podem estar na mesma máquina, mas não devem ser confundidos. Decisão de domínio não é atomicamente transacional com spawn/write; uma transação SQL não pode envolver espera de subprocesso ou socket. O ledger do Core impõe limite físico compartilhado às instâncias daquela instalação, inclusive quando o Server compõe um Core por sessão.

Escolha desta revisão: banco canônico existente + um journal Core compartilhado do executor local + um ledger Core de instalação. Usar implementações públicas Core; não copiar SQL do journal nem reimplementá-lo no Nexus nesta rodada. O adapter `core_history.py` consulta esse journal sem candidatos/factory para recuperar recibos depois de restart.

## 2. Entidades existentes preservadas

Foi confirmada a existência de `agent_endpoints`, `runtime_profiles`, `runtime_boot_bindings`, `runtime_execution_grants`, `runtime_open_requests`, `runtime_access_audit` e `delivery_outbox` nos arquivos examinados. O executor deve registrar o schema completo real antes das migrações, inclusive tabelas de sessões/handoff/claims não integralmente lidas nesta elaboração.

Regras fechadas:

* `agents`, chaves hash-only, permissões, IDs e mensagens não são recriados.
* `agent_endpoints` permanece autoridade de política do endpoint: enabled, activation_state, consumption, response_policy, priority e seleção aprovada. Não duplicar flags contraditórias em uma tabela nova.
* `runtime_profiles` permanece autoridade da configuração aprovada; dados nativos de lançamento passam a ser produzidos pelo Core, não campos livres de command/argv.
* `delivery_outbox` continua a fila canônica da entrega lógica e sua causalidade. A nova outbox de despacho abaixo transporta a operação referenciada; não cria segunda entrega/inbox.
* `runtime_open_requests` legado continua consultável. Novas operações têm contrato R4; a migração registra vínculo com a requisição anterior, sem recalcular seu hash.
* Binding remoto não recebe `root_realpath` calculado no Server. Dados históricos locais continuam mantidos para compatibilidade.

## 3. Extensões canônicas

Nomes-alvo abaixo fixados para a implementação. Se já existir tabela equivalente no HEAD posterior, reutilizá-la por migração de colunas e registrar o crosswalk; não criar duplicata. Ausência/diferença deve ser diagnosticada antes de aplicar, não resolvida com `DROP TABLE`.

| Tabela/conceito | Campos mínimos e chave | Invariante / índices |
|---|---|---|
| `execution_installation` | singleton com server_id, embedded_executor_id, schema_revision | Identidade da instalação persistida, não derivada do host a cada boot. |
| `execution_executors` | PK `(server_id,executor_id)`; connector_id, kind embedded/remote, label, control_state, generation, owner_instance_id, last_seen, revoked_at | UNIQUE `(server_id,kind,connector_id)` para remoto; índice por state/last_seen; sem user_id ou master key. |
| `execution_bindings` | PK `(server_id,binding_id)`; executor_id, endpoint_id UNIQUE no Server, workspace_binding_id, candidate_ref, inventory_revision, realization_ref/revision, binding_revision | FK endpoint existente; agente/adaptador/workspace são resolvidos e comparados com endpoint, não valores autônomos que podem divergir. |
| `execution_workspace_bindings` | PK `(server_id,workspace_binding_id)`; executor_id, workspace_id, realization_handle, revision, local_label aprovado, status | Handle opaco no remoto; root físico em registro local apenas. Índice executor/workspace. |
| `execution_realizations` | PK `(server_id,executor_id,realization_ref)`; local_realization_ref, subject_agent_id, workspace_binding_id, candidate_ref, inventory_revision, configuration_digest, local_root_proof_digest, revision/status | UNIQUE executor/local_realization_ref/revision; mapeamento canônico→handle opaco do executor, sem path remoto resolvido. |
| `execution_inventory_snapshots` | PK `(server_id,executor_id,publication_sequence)`; revision, formatos, core_version, canonical_projection, received_at, age, producer_instance_id | UNIQUE executor/sequence; digest igual não autoriza retroceder sequence; projeção sem paths/secrets. |
| `execution_inventory_current` | PK `(server_id,executor_id)`; sequence/revision atuais | Ponteiro atualizado por CAS após validar snapshot completo; guardar últimas duas revisões para diagnóstico, não histórico ilimitado. |
| `execution_proposals` | proposal_id PK no Server; client_intent_id, actor, subject, escopo, revisões esperadas, diff_hash, expires_at, status | Proposta não autoriza spawn; idempotência por ator/client_intent_id. |
| `execution_client_intents` | PK `(server_id,actor_agent_id,client_intent_id)`; body_hash, intent_id, operation_id, resolution_revision, resolved_json, created_at | Mesmo ID/corpo devolve resultado; corpo diferente conflita. Não depender do primeiro HTTP response para saber o ID. |
| `execution_operations` | PK `(server_id,executor_id,operation_id)`; subject_agent_id, actor_agent_id, binding/workspace/session, action, intent_hash, semantic_payload, expected revisions, decision/delivery parent, admission_state | Imutável quanto à semântica após admissão; índice subject/workspace/status. Payload sensível é ref/digest, não texto de input em logs. |
| `execution_dispatch_outbox` | PK FK da operação; dispatch_state, attempt_token, attempt_no, connection_generation, lease_id/serial, next_attempt_at, last_error, last_receipt_revision | Um item por operação; query/reconcile para unknown, não resend cego. Índices pendente/executor e next_attempt. |
| `execution_receipts` | PK operação + receipt_revision; intent_hash, stage, possible_effect, retry_safe, native_id, error_code, received_at | Receipt de hash/scope diferente não é anexado à operação. Projeção reduzida mantém última revisão. |
| `execution_sessions` | PK `(server_id,executor_id,session_id)`; binding/workspace, open_operation_id UNIQUE por scope, core_owner_ref, owner_generation, estado/prova, stream_epoch, lease state, legacy_session_id quando houver | É a projeção de execução governada. Sessão lógica preexistente conserva seu ID e ligação; não criar novo Agent nem substituir histórico. |
| `execution_leases` | PK sessão + lease_serial; grant_id, allowed_actions_json, auth/config/owner/connection/credential epochs, valid_until_server, request_id, status | Prazo do Server independente do monotônico do executor; revogada não volta a ativa por replay. Índices expiração/subject. |
| `execution_link_tickets` | ticket_id PK; hash único, scope, audiences/scopes, epochs, expires_at, bound_connection_id, revoked_at | Nunca plaintext. Binding ticket não concede todas as lanes. |
| `execution_session_capabilities` | capability_id PK; hash, audiência MCP ou native-actions, sessão/subject/actions/validity/revocation | Segredo retornado uma vez/no-store; token não vai em URL/argv. |
| `execution_event_ingress` | PK `(server_id,executor_id,session_id,stream_epoch,sequence)`; event_hash, tipo, payload operacional íntegro validado, received_at | Duplicata mesmo hash idempotente; hash divergente conflito; limites de tamanho e retenção. |
| `execution_event_watermarks` | PK StreamKey; committed_contiguous, projected_through, gap state | ACK deriva exclusivamente de committed_contiguous. UI/SSE não altera esse campo. |
| `execution_decisions` | decision_id PK; ApprovalKey único + revision; proposta íntegra/digest, ator/sujeito, decisão, canonical state, native_operation_id, response_digest/ref, expiry | CAS para decisão única; resultado nativo é receipt separado. Raw hash operacional não passa por redaction. |
| `execution_migration_map` | PK fonte/tipo/legacy_id; canonical_ref, row_digest_before, migration_batch_id, state | Retomada/backfill auditável; preservar IDs e hashes antigos. |

Campos de revisão são inteiros >=1, exceto serial esperado zero na primeira concessão. Guardar datas canônicas de auditoria UTC; timers ativos são monotônicos de processo e não sobrevivem ao boot por restauração numérica. Schema de JSON é validado na escrita e na fronteira; não confiar em payload porque veio do próprio banco legado.

**Escolha de reaproveitamento:** endpoint e binding são relação 1:1 por `endpoint_id`, não duas políticas. `execution_sessions` é projeção do executor e liga a sessão lógica/harness legada pelo campo de referência. O executor registra a tabela de sessão legada efetiva no manifesto da migração; os campos novos não podem substituir silenciosamente `session_secret` da identidade existente.

## 4. Transações exatas

### T1 — Apply de binding

Validar principal, proposta, hashes/revisões, snapshot ainda vigente e realização aprovada. Abrir UoW; confirmar revisões atuais; criar/atualizar endpoint/profile e binding extension; registrar auditoria e mapa legado; commit. Somente depois responder. Se a confirmação se perde, reusar client_intent_id e consultar a mesma proposta aplicada. Nada de enviar ticket ou criar processo dentro da transação.

### T2 — Admissão de operação

Verificar resolução e hash; UoW adquire idempotência; confirma políticas/subject/realização/configuração; cria operation e dispatch_outbox na mesma transação e reserva o claim lógico quando aplicável; commit; responder 202. O dispatcher adquire attempt_token por CAS em outra transação curta e faz I/O depois. Worker revalida o token e a autorização depois de fila/espera.

### T3 — Evento/ACK

Validar namespace contra canal e semântica do frame; UoW insere eventos inéditos, compara hashes dos duplicados e avança somente watermark contíguo; commit; ACK. Reducer/projeção é idempotente e pode ocorrer nessa transação para fatos pequenos ou depois via offset persistido; nenhum ACK espera o frontend. Gap/lote não contíguo preserva último limite comprovado.

### T4 — Decisão

Validar operador e pedido íntegro; UoW CAS de revision e estado PENDING; grava decisão, client intent, operation de aplicação e outbox; commit. Request HTTP interrompido não desfaz o commit nem cancela o produtor. A confirmação perdida é consultada por client_intent_id. Input bruto sem armazenamento sensível persistente tem a limitação declarada no contrato.

### T5 — Revogação/rotação

Após autorização, bloquear concessões em memória na seção curta pertencente ao agente/binding. UoW altera epoch/revision e derivados; commit; invalida cache, lanes, capabilities e concessões do Server; envia controles/revokes fora do UoW. Se commit ficar incerto, manter bloqueio conservador e reconciliar; não reabrir com um bool. Na partição, validade local do executor é limite real, não promessa de revogação instantânea remota.

## 5. Migração em etapas, sem reset

### M0 — Pré-condições e backup

Registrar schema/user_version/migration log reais, conteagens de agentes/keys/workspaces/mensagens/claims/handoffs/endpoints/sessões/outbox, índices e negações. Gerar backup consistente pelo mecanismo SQLite de backup ou aplicativo parado; nunca copiar somente o arquivo principal com WAL ativo. O número da migration SQL é o próximo número livre encontrado no runner, registrado no manifesto; não fixar um número que possa colidir com trabalho posterior.

### M1 — Expansão aditiva

Criar extensões e índices, mantendo leitores legados. Preservar checks e FKs. Não alterar as permissões por default: endpoint desabilitado continua desabilitado, método negado continua negado. Criar embedded_executor canônico para a instalação, mas não abrir processos por fazer backfill.

### M2 — Tradução do catálogo legado

Somente para dados históricos e migração, manter tabela fechada:

| ID do Server legado | ID Core |
|---|---|
| `codex` | `codex_app_server` |
| `pi` | `pi_rpc` |
| `claude_code.stream` | `claude_stream` |
| `claude_code.attach` | `claude_attach` |
| `mcp` | tools-only/MCP HTTP; não é adapter de processo |

Essa tabela não é um catálogo novo. IDs não conhecidos não recebem fallback; marcar `MIGRATION_REVIEW_REQUIRED`. Remover a tabela do hot path após migração concluída, conservando tradução read-only de histórico. Não substituir nomes dentro de hashes/receipts antigos.

### M3 — Endpoints e workspaces

Associar endpoints locais antigos ao embedded_executor e criar linkage de binding. Paths antigos são validados localmente pelo Core para uma nova realização; não transformar command strings livres em argv autorizados. Campo legacy ID permanece. Novo candidato não observado vira `REDISCOVERY_REQUIRED`, não arquitetura/versão inventada. Profile amplo/hook/home herdado exige consentimento definido, sem ligar bypass de permissions.

Workspaces baseados em path mantêm IDs. Novo workspace remoto recebe ID opaco Server + handle do executor, com associação explícita ao lógico existente quando o agente/operador tem permissão. Git remote, nome do diretório ou igualdade textual de path não mesclam workspaces.

### M4 — Sessões em curso e cutover

Não migrar processo vivo de supervisor antigo para Core por copiar PID. Antes do cutover, colocar admissões antigas em drain, preservar readers/queries, aguardar ou encerrar pelo owner antigo com evidência. Unknown continua identificado; não lançar substituto para “completar migração”. Bindings migrados só são ativados no novo caminho depois de resolução. Arquivos HOME/config ativos não são movidos.

Migrar o mapa de operações e histórico sem alterar IDs/hashes. Quando um receipt histórico não pode ser representado integralmente no R4, manter a consulta legada e uma referência de origem, sem inventar estágio novo. Replay mutável de operação legada não acontece automaticamente.

### M5 — Remoção de MCP stdio e duplicação

Extrair antes o bootstrap/Deps e o registro compartilhado de ferramentas. Remover só a implementação do transporte stdio, o ramo de execução, exemplos command/args e testes que exigem esse transporte. A CLI principal passa a módulo neutro; sem argumentos mostra help e código de saída definido, não inicia stdio. `serve` continua HTTP.

Migrar somente configurações MCP Nexus explicitamente escolhidas, com backup/diff/CAS, preservando agent key e entradas alheias. Não inserir comando shim stdio→HTTP. Remover adapters nativos do Server depois de seus consumidores dependerem do Core e de paridade delimitada; até lá wrappers finos não contêm parsing/spawn próprio.

### M6 — Verificação e rollback

Comparar conteagens e digests dos dados preservados; repetir migrations; injetar falha entre batches e retomar. Antes de novo efeito R4, rollback de aplicação pode usar expansão compatível. Depois de efeitos remotos/R4, requer drain/reconcile e versão capaz de ler dados novos. Não apagar journal/outbox nem reativar stdio como fallback. Restore é operação explícita do operador, não corretor automático.

## 6. Startup e recuperação sem binários

Ordem do owner `serve`:

1. Lock de instalação/owner existente; configuração válida; migrações canônicas concluídas.
2. Inicializar auth, registro técnico e readers públicos. Servir health com readiness ainda RECOVERING.
3. Abrir journal/ledger Core do executor local fora do loop bloqueante; leitura de claims/receipts/leases/slots paginada.
4. Reconstituir projeções e obrigações, **não handles vivos**. Birth record é histórico e não direito de sinalizar PID.
5. Retomar ingresso/outbox em modo consulta para resultados incertos. Nenhum prompt é reenviado por haver linha pendente.
6. Negociar executores remotos por ticket, geração e reconcile; snapshots devem ser refrescados.
7. Habilitar novas admissões somente para bindings/sessões reconciliados e autorizados. Falha em um provider local não derruba APIs nem executores remotos independentes.

`GET operation/intents/decisions` e scans de reconciliação funcionam sem `candidate_for`, sem provider instalado e sem chamar `prepare`. Usar `Journal.get_receipt`, `claimed_sessions`, `get_session_lease`, `get_process_birth` e APIs públicas correspondentes. Para batch, respeitar limite real do Core: até 256 IDs por reconcile e páginas de claims/slots até 4096; default 128. Não usar scan ilimitado nem SQL paralelo no handler.

## 7. Ownership dos producers

Cada operação em voo possui registro com owner token, task/Future produtor, waiter(s), resultado conhecido e obrigação durável. O socket/HTTP/CLI não possui o producer. `asyncio.wait_for(gather(...))` sobre producers possuídos é proibido quando o cancelamento do waiter abandonaria uma thread/commit; separar observers descartáveis de operações que ainda podem produzir efeito.

Casos obrigatórios:

| Caso | O que conservar | O que não concluir |
|---|---|---|
| Open iniciado, chamador cancelado | Tentativa, guard, Future e slot | Cancelamento não prova que não houve spawn. |
| Handle retorna depois do shutdown | Owner forte antes de qualquer await; coordenador Core | Não descartar porque cliente já saiu. |
| Close/observe bloqueado | Força com capacidade independente | Não esperar cancelamento de close para despachar força. |
| Force em thread ainda ativa | Future físico e coalescência | Coroutine cancelada não autoriza outra força simultânea. |
| STOPPED observado, release falhou | Prova de parada + obrigação leve de release | Não omitir a obrigação nem exigir nova força. |
| Decisão Server confirmada, Core incerto | Pedido, decision_id, operação e receipt | Não restaurar pending para outro approve. |
| ACK Server recebido, ACK Core falhou | Watermark remoto e pendência de aplicar | Não repetir trabalho do agente. |

Essas garantias são consumidas do Core, não reimplementadas no Server. O host deve preservar sua vida útil e o acesso aos stores necessários.

## 8. Shutdown do Server

`serve` possui o executor embutido. Ao iniciar shutdown, marcar draining e fechar novos starts/submits em memória; permitir consultas, controle autorizado e ingresso final de eventos. Agendar controles de todos os recursos locais em paralelo sob quotas. Política inicial: 30 s drain + 15 s de interrupção + 5 s de espera/relatório; orçamento de resposta total 50 s, configurável e medido uma vez por shutdown, não multiplicado por sessão.

Chamar Core.shutdown por instância sem serializar tudo atrás do POST/release de outra. Não excluir instância com unknown nem fechar journal/ledger enquanto houver producer que possa usá-los. Resultado por SessionKey deve separar processo desconhecido e somente liberação durável pendente.

**Decisão de produto nesta revisão:** se restarem recursos locais sem prova de parada/transferência, permanecer em `DRAINING_PENDING`, conservar o supervisor e disponibilizar health/consulta administrativa de recuperação. O comando retorna relatório pendente; não fazer `sys.exit(1)` como se isso conservasse o loop. Saída forçada do processo é operação administrativa explícita, com limite de contenção do SO documentado e qualificado. SIGKILL não passa pelo caminho gracioso; não prometer guarantees sem guardian/back-end qualificado.

Parar Server não mata imediatamente processos remotos: fecha novas concessões e deixa o Connector aplicar o prazo já autorizado. Se for desejado parar remotamente antes de sair, usar operações canônicas de close e relatar confirmação/unknown; não confundir desconexão WSS com morte física.

## 9. Quotas, controle e observabilidade

Defaults de planejamento, sujeitos aos testes de carga antes de anúncio de capacidade:

| Recurso | Limite inicial |
|---|---|
| Frame NXL | 1 MiB; texto por chunk até 64 KiB |
| Operação inline | 64 KiB; pedido/input nativo até o limite Core de 16 KiB |
| Pendentes produtivos por executor | 32; admissão antes de criar task |
| Controle reservado por executor | 8 itens + orçamento próprio de bytes |
| Runtimes por instalação | Ledger Core: 8 por default, compartilhado |
| Journal Core | 256 MiB lógico, reserva crítica 16 MiB |
| Snapshot técnico | 128 instalações por publicação inicial; coleção maior exige paginação/manifest acordado antes de habilitar |
| Heartbeat / ausência de canal | 15 s / 45 s; não lease de execução |
| Lease / renovação | Até 120 s / 30 s; duração consome RTT |
| Ticket | Até 600 s, renovar a 70% com jitter |
| Cache positivo de chaves | Até 4096 entradas; TTL máximo 60 s + invalidação de epoch |
| Backoff recuperável | 0,5–30 s com jitter e uma task por obrigação/stream |

Quota em itens e bytes é reservada em token que guarda custo exato. Liberação é idempotente pelo token, sem recalcular outro JSON. Reader valida/encaminha em fila limitada e continua recebendo controles; não cria milhares de tasks que esperam semáforo. Nenhum retorno de enqueue=false é tratado como sucesso.

Cenário de 100 mil agentes mede lookup por chave, paginação, memória e latência sem providers. Não significa 100 mil runtimes simultâneos. Não alocar lane/thread por agente offline. Métricas não usam session_id/agent_id como labels ilimitados. Logs escopados preservam IDs/digests operacionais e redigem secrets; UI recebe só o necessário ao principal.

## 10. UI e CLI — critérios concretos

**Tela do agente:** manter identidade e permissions; separar aba “Ferramentas MCP HTTP” de “Runtimes gerenciados”. Retirar TTL técnico/connection-key manual do caminho normal. Host remoto oferece comando protegido; host local não oferece instalação de Connector como pré-condição.

**Seletor:** executor primeiro, instalação depois. Renderizar `label/display_name/state/reasons` do snapshot; estado OFFLINE/STALE aplica overlay, sem modificar o fato técnico histórico. Duas cópias iguais continuam duas escolhas. Atualização do inventário invalida o formulário pendente e exige refresh; não escolher a primeira após reorder.

**Aprovação:** mostrar ator requerido, agente-alvo, host, projeto, tipo de operação, escopo/diff, validade e estados canônico/nativo separados. Depois de confirmar, acompanhar decision_id; timeout não apresenta outro botão que envia nova intenção automaticamente. Pedido de outra sessão/Server não é resolvido pelo rótulo.

**Runtime:** estados distintos para binding aprovado, transporte pronto, instalação pronta, starting, ready, running, waiting input, draining, unknown e stopped/release pending. Botões derivam capacidades efetivas, não enum TypeScript. Interromper turno não é parar processo. O fim do turno não mostra handoff concluído automaticamente.

**CLI:** `runtime discover/start/status/interrupt/stop/logs/doctor/bindings`, com `--json` e `--non-interactive`. Sem parâmetros mostra ajuda; stdin não inicia MCP. Headless exige escolha inequívoca ou erro com alternativas; não autoaprova nem pergunta secret no argv. ID de intenção fica disponível mesmo no timeout. Follower de logs pode encerrar sem parar runtime.

Testar UI com API real de laboratório, não apenas JSON copiado: duas instalações byte-idênticas, executor remoto de outra plataforma, atualização com mesma versão, snapshot stale, revogação entre seleção e apply, timeout de operation, duplicate approval e ausência de provider local no Server.


---

<a id="documento-04"></a>

**Documento-fonte: `04_BACKLOG_EXECUCAO.md`**

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


---

<a id="documento-05"></a>

**Documento-fonte: `05_TESTES_E_ACEITE.md`**

# Matriz unificada de testes e gates R4


**Todos os cenários de produto começam NOT_RUN.** Os cenários TR4 abaixo são especificações a implementar. TN/J mantêm o texto de preparação/resultado do plano original; execução sintética não fecha um requisito explicitamente de provider ou multi-host.


Contagem documental: **164 cenários** = 85 TR4 novos/específicos + 79 TN/J preservados. Não são 164 testes executados.


## Campos mínimos de evidência


test_id, test_node, layer, source_commit, Core/Connector commits, hashes dos wheels/bundle, SO/Python/provider, comando, exit_code, XML/log redigido, resultado observado e blockers. Não somar rerun/subconjunto ao total da suíte.


## TR4 — condições novas ou explicitadas


### TR4-00-01 — Registrar branch, HEAD, fonte e capacidade realmente instalada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.01.

**Preparação:** Clone de laboratório na branch e diretório com alteração não commitada.

**Ação:** Gerar baseline e executar novamente sem editar código.

**Resultado obrigatório:** Mesmo HEAD e alteração local preservados; manifest distingue fonte, wheel e qualificação; nenhuma alteração destrutiva.


### TR4-00-02 — Encerrar planos concorrentes sem perder requisito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.02.

**Preparação:** Planos R3, CN1–CN5 e arquivos de planejamento presentes.

**Ação:** Validar crosswalk e procurar tarefas sem sucessor.

**Resultado obrigatório:** 70 tarefas originais e 79 cenários TN/J possuem destino; nenhuma tarefa está DONE só por estar descrita.


### TR4-00-03 — Fixar responsabilidades e interfaces R4 entre repositórios

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.03.

**Preparação:** Peer de contrato sem provider; payloads válidos e respostas com envelope legado.

**Ação:** Exercitar fixtures de protocolo e comparar representação.

**Resultado obrigatório:** Objetos /v1 diretos são aceitos; ok/data legado não é confundido; divergências produzem VERSION_INCOMPATIBLE antes de efeito.


### TR4-00-04 — Solicitar bundle Core R4 e preservar histórico r3

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.04.

**Preparação:** Bundle r3 fixado e fixtures-alvo R4.

**Ação:** Validar rejeição cruzada e leitura histórica explícita.

**Resultado obrigatório:** R3 não executa efeitos R4; receipts históricos continuam interpretáveis; gate remoto permanece BLOCKED_EXTERNAL até artefato compartilhado.


### TR4-00-05 — Construir harness de testes e limites de evidência

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.05.

**Preparação:** Ambiente sem credenciais de providers.

**Ação:** Rodar um controle de fixture e validar o manifesto de evidência.

**Resultado obrigatório:** Campanha pode passar em contrato sem marcar provider/multihost como PASS; segredos de laboratório identificados e isolados.


### TR4-01-01 — Extrair Deps e composição antes de remover transporte

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.01.

**Preparação:** Server atual com /mcp e REST saudável em fixture.

**Ação:** Importar nova composição e comparar catálogo HTTP antes/depois.

**Resultado obrigatório:** HTTP mantém tools/resources e identidade; import não abre listener ou subprocesso; não há dependência do Connector.


### TR4-01-02 — Remover o ramo MCP stdio sem shim

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.02.

**Preparação:** Configuração legada selecionada e captura de stdin/stdout/processos.

**Ação:** Invocar comandos antigos e novas opções HTTP.

**Resultado obrigatório:** Nenhuma sessão MCP stdio nasce; serve continua HTTP; nenhum adaptador nativo é removido por usar stdin/stdout.


### TR4-01-03 — Definir CLI principal e extras de instalação

**Estado:** NOT_RUN. **Camada:** `packaging`. **Tarefa:** NS01.03.

**Preparação:** Wheel em ambiente limpo sem clone irmão.

**Ação:** Executar help, serve-lite e import dos adaptadores.

**Resultado obrigatório:** CLI não inicia stdio sem argumentos; extras contêm o Core necessário e não exigem a aplicação Connector.


### TR4-01-04 — Montar routers /v1 com autenticação específica

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.04.

**Preparação:** Requests HTTP e upgrade local/remoto com chaves/tickets inválidos.

**Ação:** Consultar protocolo público, /me e fazer upgrades positivos/negativos.

**Resultado obrigatório:** Só protocolo público expõe dados não privados; endpoints escopados rejeitam credenciais de audiência errada antes do handler.


### TR4-01-05 — Migrar configuração MCP apenas selecionada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.05.

**Preparação:** Arquivo com duas entradas de terceiros e uma Nexus selecionada.

**Ação:** Aplicar migração, repetir e simular edição concorrente.

**Resultado obrigatório:** Somente entrada selecionada muda; key/id intactos; concorrência recusa sem sobrescrever terceiros; stdio não retorna como rollback.


### TR4-02-01 — Definir chaves de escopo imutáveis

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.01.

**Preparação:** Dois Servers/executores com mesmos binding/session/request IDs.

**Ação:** Inserir, consultar e remover um namespace.

**Resultado obrigatório:** Nenhuma colisão ou remoção cruzada; UI pede escopo quando alias curto é ambíguo.


### TR4-02-02 — Criar extensões aditivas e índices

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS02.02.

**Preparação:** Banco vazio e cópia legada consistente.

**Ação:** Migrar, repetir e conferir constraints/índices.

**Resultado obrigatório:** Migrações idempotentes; dados legados e negações preservados; consulta indexada encontra escopo exato.


### TR4-02-03 — Persistir identidade técnica local e remota

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.03.

**Preparação:** Duas inicializações locais e dois pedidos idempotentes de registro remoto.

**Ação:** Reabrir a base e repetir registro com mesma intenção.

**Resultado obrigatório:** IDs estáveis, nenhum Agent novo e nenhum takeover automático por clone de diretório.


### TR4-02-04 — Separar workspace lógico da realização física

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.04.

**Preparação:** Server Linux, fixture de realização Windows e duas pastas do mesmo repo.

**Ação:** Preparar vínculos lógicos e tentar falsa equivalência.

**Resultado obrigatório:** Nenhuma resolução de filesystem remoto em A; associação depende de permissão e aprovação explícita; histórico não é re-hasheado.


### TR4-02-05 — Implementar writers transacionais e readers de histórico

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.05.

**Preparação:** Instrumentação da connection factory e peer que bloqueia I/O.

**Ação:** Admitir operação e bloquear o dispatcher externo.

**Resultado obrigatório:** Commit termina antes do I/O; consultas continuam responsivas e reproduzem os registros por IDs exatos.


### TR4-03-01 — Implementar /me pela autoridade já existente

**Estado:** NOT_RUN. **Camada:** `contract_scale`. **Tarefa:** NS03.01.

**Preparação:** 100 mil registros sintéticos com índice por key hash.

**Ação:** Autenticar uma key e enviar hint de outro agente.

**Resultado obrigatório:** Lookup escopado/indexado; spoof recusado; nenhum cadastro ou rotação ocorre.


### TR4-03-02 — Implementar proposta/aplicação com política herdada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.02.

**Preparação:** Agente com negação explícita e operador de fixture.

**Ação:** Tentar self-escalation e depois aprovação autorizada.

**Resultado obrigatório:** Agente não autoaprova; operador aplica uma revisão; repetição retorna a mesma proposta aplicada sem gerar outra identidade.


### TR4-03-03 — Emitir tickets escopados e revogáveis

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.03.

**Preparação:** Dois bindings/agentes, dois executores e relógio controlado.

**Ação:** Reusar ticket em outro alvo, expirar e rotacionar key.

**Resultado obrigatório:** Alvo/audiência/epoch incorretos recusados; outro agente permanece operacional; novo ticket não revive key revogada.


### TR4-03-04 — Implementar capability MCP de sessão com audiência própria

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.04.

**Preparação:** Harness HTTP de laboratório com token de sessão e ticket NXL.

**Ação:** Chamar tool permitida, proibida e depois revogar sessão.

**Resultado obrigatório:** Só ações permitidas têm efeito; ticket errado falha; revogação bloqueia MCP sem depender de proxy Connector.


### TR4-03-05 — Gerar comando protegido e não recuperar hash como segredo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.05.

**Preparação:** Agente hash-only e captura de issue_key/argv.

**Ação:** Gerar comando em Bash e PowerShell e usar key existente.

**Resultado obrigatório:** Comando sem segredo de longa duração; nenhuma chamada de emissão; MCP anterior continua autenticando o mesmo agente.


### TR4-04-01 — Consumir catálogo sem compor runtime falso

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.01.

**Preparação:** Ambiente sem harnesses e Core instalado.

**Ação:** Consultar catálogo antes de iniciar journal/runtime.

**Resultado obrigatório:** Catálogo vem do Core sem spawn/porta/credencial; attach continua registrado não qualificado.


### TR4-04-02 — Preservar candidatos e avaliar no host correto

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.02.

**Preparação:** Par Node/CLI de laboratório e duas versões da mesma família.

**Ação:** Discovery → avaliação → serialização.

**Resultado obrigatório:** Refs/build/version/architecture preservados; avaliação remota utiliza host remoto; nenhum provider é iniciado para listar.


### TR4-04-03 — Gerar e ingressar revisão completa do inventário

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.03.

**Preparação:** Mesmos paths/versão com bytes alterados e inventário reordenado.

**Ação:** Publicar snapshots repetidos, adulterados e antigos.

**Resultado obrigatório:** Bytes/qualificação alterados mudam revisão; reorder/timestamp isolado não muda; stale/adulterado recusados antes de binding.


### TR4-04-04 — Expor opções com estados técnicos e canônicos separados

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.04.

**Preparação:** Executor offline, candidato unqualified e agente sem autorização.

**Ação:** Consultar opções e comparar estados.

**Resultado obrigatório:** UI recebe razões verdadeiras; nenhuma combinação bloqueante habilita start; dados de outro executor não são apresentados ao principal errado.


### TR4-04-05 — Resolver instalação da revisão exibida

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.05.

**Preparação:** Duas cópias byte-idênticas A/B e revisão inicial.

**Ação:** Selecionar B, reordenar e depois alterar B antes do apply.

**Resultado obrigatório:** B continua B após reorder; drift/stale recusa antes de efeito; ref legada ambígua exige reseleção.


### TR4-05-01 — Registrar realização no executor proprietário

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.01.

**Preparação:** Realização Windows remota e Server sem esse path.

**Ação:** Registrar e tentar usar ref em outro executor/agente.

**Resultado obrigatório:** Somente escopo correto resolve; Server não testa filesystem remoto; nenhum spawn ao preparar.


### TR4-05-02 — Compor proposta agregada de vínculo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.02.

**Preparação:** Primeiro uso local/remoto com opções inequívocas.

**Ação:** Preparar proposta pela mesma API usada pela UI.

**Resultado obrigatório:** Uma confirmação mostra agente, host, instalação, projeto e escopo; backend já resolveu detalhes técnicos.


### TR4-05-03 — Aplicar proposta com CAS e recibo recuperável

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.03.

**Preparação:** Falha de resposta depois de commit e alteração concorrente de perfil.

**Ação:** Repetir client_intent_id e depois tentar proposta obsoleta.

**Resultado obrigatório:** Sem duplicação; resposta recupera mesmo binding; mudança de escopo exige nova aprovação.


### TR4-05-04 — Implementar reuso e novo processo explícito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.04.

**Preparação:** Duas sessões/candidatos e uma operação de open incerta.

**Ação:** Pedir start repetido, novo explícito e caso ambíguo.

**Resultado obrigatório:** Reuso não cria processo; new_session autorizado é distinto; unknown/ambiguidade não escolhe substituto.


### TR4-05-05 — Tratar drift e login de provider como estados explícitos

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.05.

**Preparação:** Atualização de binário, root movido e provider sem login.

**Ação:** Iniciar pela API e rebind após consentimento.

**Resultado obrigatório:** Recusas anteriores ao efeito têm diagnóstico; rebind efetivo preserva agente/key e não desliga outra sessão.


### TR4-06-01 — Implementar resolve sem executar

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.01.

**Preparação:** Peer contador de chamadas nativas e resposta perdida de resolve.

**Ação:** Resolver duas vezes mesma intenção e consultar por client_intent_id.

**Resultado obrigatório:** Zero efeitos; mesmos IDs; body diferente conflita; consulta recupera resposta perdida.


### TR4-06-02 — Admitir operação e outbox atomicamente

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.02.

**Preparação:** Injeções antes/depois de commit.

**Ação:** Admitir, perder resposta e repetir chave.

**Resultado obrigatório:** Uma operação/outbox lógica e um claim; falha pré-commit não anuncia sucesso; pós-commit é consultável.


### TR4-06-03 — Implementar dispatcher com reserva e revalidação

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.03.

**Preparação:** Fila pequena saturada e rotação durante espera.

**Ação:** Enfileirar submits e um controle, alterar grant antes do despacho.

**Resultado obrigatório:** Controle progride; operação obsoleta produz zero efeito; quota volta exatamente a zero ao concluir.


### TR4-06-04 — Separar dispatch, receipt e consulta

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.04.

**Preparação:** Peer registra uma execução e perde ACK do receipt.

**Ação:** Reenviar receipt idêntico e consultar operação.

**Resultado obrigatório:** Receipt idempotente não cria trabalho; um efeito máximo por intenção demonstrada; unknown não é retry seguro por timeout.


### TR4-06-05 — Preservar consumo exclusivo e causalidade do domínio

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS06.05.

**Preparação:** Mesma delivery disputada por MCP e dois runtimes.

**Ação:** Concorrer claim e encerrar um turno sem handoff_complete.

**Resultado obrigatório:** Um executor lógico; observers não executam; handoff permanece pendente até caso de uso governado.


### TR4-07-01 — Compor stores e runtime por ownership explícito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.01.

**Preparação:** Dois starts concorrentes e cancelamento de um waiter.

**Ação:** Compor instâncias e contar stores/workers/reservas.

**Resultado obrigatório:** Uma inicialização possuída por store; nenhum worker órfão; quota física agregada respeitada.


### TR4-07-02 — Adaptar prepare/open/control preservando IDs

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS07.02.

**Preparação:** Core real + peer nativo e contextos válidos/invalidos.

**Ação:** Executar open/submit/steer/interrupt/close pelo Server.

**Resultado obrigatório:** IDs conservados e erros tipados; operação legítima funciona; scope/generation errados não alcançam peer.


### TR4-07-03 — Gerar ambiente e cliente MCP por abertura

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.03.

**Preparação:** Duas sessões e dois Servers com IDs longos semelhantes.

**Ação:** Preparar lançamento e inspecionar env/arquivos reais de laboratório.

**Resultado obrigatório:** Configurações distintas, URL correta, tokens por sessão; marker estrangeiro impede sobrescrita; nenhum MCP proxy.


### TR4-07-04 — Compor aprovação e bridge Pi por portas públicas

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.04.

**Preparação:** Core real e bridges de laboratório sem provider.

**Ação:** Invocar pedido nativo, ação Pi limitada e tentativa fora de escopo.

**Resultado obrigatório:** Ação canônica passa pelo guard; fora de escopo recusa; capability não implementada é explicitamente indisponível.


### TR4-07-05 — Ligar eventos e encerramento ao host persistente

**Estado:** NOT_RUN. **Camada:** `core_fault_injection`. **Tarefa:** NS07.05.

**Preparação:** Open tardio, close bloqueado e release pendente.

**Ação:** Cancelar waiter, iniciar shutdown e restaurar backend.

**Resultado obrigatório:** Mesma abertura/handle permanece alcançável; controles independentes; consultas relatam físico e durável separadamente.


### TR4-08-01 — Autenticar upgrade e negociar versão antes de efeitos

**Estado:** NOT_RUN. **Camada:** `transport_contract`. **Tarefa:** NS08.01.

**Preparação:** Peers válidos e ticket cruzado, expirado ou versão antiga.

**Ação:** Tentar upgrades e enviar operation antes do welcome.

**Resultado obrigatório:** Somente namespace/protocolo correto progride; zero efeito em negociação inválida; secrets ausentes do log.


### TR4-08-02 — Confirmar attach explicitamente e isolar agentes

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.02.

**Preparação:** Dois agentes e attach antigo bloqueado durante rotação.

**Ação:** Admitir A/B, rotacionar A e liberar resposta velha.

**Resultado obrigatório:** B permanece válido; A só abre sob ACK novo; ticket A não concede B; ausência de ACK mantém PENDING.


### TR4-08-03 — Implementar reconciliação e readiness por sessão

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.03.

**Preparação:** Journal indisponível e depois recuperado.

**Ação:** Concluir handshake, simular falha e restaurar.

**Resultado obrigatório:** Operação nova fica bloqueada até recuperação; controles/história permitidos conforme escopo; nenhuma falsificação de liveness.


### TR4-08-04 — Validar escopo de todos os frames

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.04.

**Preparação:** Canal B pede receipt/approval/session de A com IDs iguais.

**Ação:** Percorrer receiver→handler→repo/Core de laboratório.

**Resultado obrigatório:** Zero dados/efeitos estrangeiros; caso legítimo passa; consultas durante handshake não ganham scope adicional.


### TR4-08-05 — Controlar filas, watchdog e cancelamento do link

**Estado:** NOT_RUN. **Camada:** `transport_fault_injection`. **Tarefa:** NS08.05.

**Preparação:** Flood, peer silencioso e queda durante execução.

**Ação:** Saturar e mandar interrupt/revoke/ACK; reconectar.

**Resultado obrigatório:** Memória/pendências limitadas; controles progridem; receipt é recuperado por ID sem duplicar trabalho.


### TR4-09-01 — Despachar remote open por realização aprovada

**Estado:** NOT_RUN. **Camada:** `cross_repo_contract`. **Tarefa:** NS09.01.

**Preparação:** Server sem binários e Connector peer com Core/realização local.

**Ação:** Abrir remotamente sem CLI ter criado sessão antes.

**Resultado obrigatório:** Um open com mesmo ID em Core; Server não acessa filesystem B; modo não suportado recusa antes de spawn.


### TR4-09-02 — Instalar lease inicial e renovar com correlação

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.02.

**Preparação:** Relógios independentes, RTT alto e resposta duplicada.

**Ação:** Solicitar initial/renew/reconnect e atrasar resposta.

**Resultado obrigatório:** Replay não estende deadline; resposta tardia não permite efeito; gerações/revisões correspondem ao grant legítimo.


### TR4-09-03 — Completar matriz de verbos e targeting

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.03.

**Preparação:** Adapters de contrato com targeting distinto.

**Ação:** Exercitar cada verbo anunciado e verbos não suportados.

**Resultado obrigatório:** Somente capacidades reais passam; expected_turn preservado; operação desconhecida gera erro tipado antes do efeito.


### TR4-09-04 — Revogar sem troca silenciosa de ownership

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.04.

**Preparação:** Dois canais/executores concorrentes e um turno desconhecido.

**Ação:** Avançar generation, revogar A e tentar execução antiga em B.

**Resultado obrigatório:** Contexto obsoleto recusado; nenhum processo substituto; histórico continua consultável no scope autorizado.


### TR4-09-05 — Qualificar desconexão de controle e ferramentas separadamente

**Estado:** NOT_RUN. **Camada:** `cross_repo_integration`. **Tarefa:** NS09.05.

**Preparação:** Dois canais controlados e uma conversa tools-only.

**Ação:** Derrubar canais individualmente e expirar capability.

**Resultado obrigatório:** Sem bypass/replay de tool mutável; tools-only legítimo permanece independente; runtime gerenciado respeita sua autorização.


### TR4-10-01 — Ingressar evento com deduplicação e watermark contíguo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.01.

**Preparação:** Seq1/seq3, duplicata1 e duplicata com hash diferente.

**Ação:** Ingressar lote e perder conexão antes/depois de commit.

**Resultado obrigatório:** Watermark só chega a1 até seq2; duplicata legítima não duplica projeção; conflito de hash é explícito.


### TR4-10-02 — Separar leitura finita de follower contínuo

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS10.02.

**Preparação:** Um evento real persistido e nenhum posterior.

**Ação:** Pedir página e publicar sem produzir outro evento.

**Resultado obrigatório:** Página termina; seq1 é enviada prontamente; próximo snapshot vazio não prende o request.


### TR4-10-03 — Usar target correto e aplicar ACK local uma vez

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.03.

**Preparação:** ACK1 conhecido, lote2 sem ACK2 e replay1.

**Ação:** Aguardar dois alvos e injetar falha em Core acknowledge.

**Resultado obrigatório:** Replay1 conclui; batch2 aguarda; obrigação de aplicar ACK converge sem novo send_turn.


### TR4-10-04 — Recuperar publicador sem evento novo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.04.

**Preparação:** Primeira leitura falha e journal contém seq1.

**Ação:** Restaurar storage e sinalizar reconnect sem publish novo.

**Resultado obrigatório:** Task é retomada uma vez, seq1 publicada/confirmada, payloads offline não crescem ilimitadamente em RAM.


### TR4-10-05 — Preservar projeções canônicas e retenção

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS10.05.

**Preparação:** Eventos fora de ordem, terminal cedo e UI offline.

**Ação:** Ingressar e reconstruir projeções duas vezes.

**Resultado obrigatório:** Estado idempotente e auditável; ACK não depende UI; handoff/causalidade continuam íntegros.


### TR4-11-01 — Persistir proposta operacional separada de exibição

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS11.01.

**Preparação:** Pedido real observado no journal Core e pipeline de ingresso/UI.

**Ação:** Receber, redigir para tela e recuperar pedido operacional.

**Resultado obrigatório:** Hash/JSON operacional byte-semanticamente preservados; UI não vaza secrets; dois namespaces não se sobrescrevem.


### TR4-11-02 — Autorizar operador e aplicar CAS antes do efeito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.02.

**Preparação:** Operador válido, agente solicitante e duas decisões concorrentes.

**Ação:** Tentar approve sem autoridade e CAS concorrente approve/deny.

**Resultado obrigatório:** Sem autoridade zero operação nativa; uma decisão canônica vence; perdedora recebe conflito consultável.


### TR4-11-03 — Despachar aplicação única e traduzir pelo contrato

**Estado:** NOT_RUN. **Camada:** `cross_repo_contract`. **Tarefa:** NS11.03.

**Preparação:** Server→Connector→Core reais nas fronteiras de laboratório.

**Ação:** Decidir pedido e repetir resposta HTTP/notificação.

**Resultado obrigatório:** Uma aplicação por operation_id; request/turn/scope corretos; accept/decline legítimos passam e pedido velho não afeta turno novo.


### TR4-11-04 — Conservar producers, recibos e incerteza de decisão

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.04.

**Preparação:** POST recebido bloqueado, cancelamento IPC e write nativo incerto.

**Ação:** Cancelar waiter, consultar e restaurar backend.

**Resultado obrigatório:** Producer permanece ou resultado é classificado; mesma decisão converge; nenhuma execução duplicada ou estado pending fictício.


### TR4-11-05 — Tratar input sensível e administrativo explicitamente

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.05.

**Preparação:** Pedido input, administrative e native session inexistente.

**Ação:** Decidir, expirar e simular crash antes da aplicação.

**Resultado obrigatório:** Limite de recuperação declarado; nenhuma resposta inventada ou desvio de namespace; consultar decisão não revela conteúdo sensível.


### TR4-12-01 — Unificar acesso MCP e native-actions no domínio

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS12.01.

**Preparação:** Uma delivery concorrida por MCP, local e Pi remoto.

**Ação:** Solicitar claim/complete via caminhos distintos.

**Resultado obrigatório:** Um claimant lógico; repeat é idempotente; policy/delivery budget preservados.


### TR4-12-02 — Aplicar autorização da sessão ao MCP HTTP

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.02.

**Preparação:** Capability limitada e key tools-only do mesmo agente.

**Ação:** Testar tool permitida, negada, root outro e revoke.

**Resultado obrigatório:** Mesmo agente, scopes diferentes; managed não contorna lease; tools-only não depende do WSS.


### TR4-12-03 — Preservar causalidade e resultado governado

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.03.

**Preparação:** Turno final sem complete e cadeia de replies próxima do limite.

**Ação:** Reconectar e completar explicitamente.

**Resultado obrigatório:** Sem complete automático nem aumento do orçamento causal; destinatário e evidência preservados.


### TR4-12-04 — Publicar capacidades apenas demonstradas

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.04.

**Preparação:** Runtime conversacional sem tool path e outro com ponte válida.

**Ação:** Consultar opções/capacidades e despachar trabalho governado.

**Resultado obrigatório:** Primeiro não recebe execute_work; segundo segue grant/claim; nenhum false READY por metadado estático.


### TR4-12-05 — Manter superfície MCP compacta

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.05.

**Preparação:** Catálogo com poucos e muitos executores, mesma toolset.

**Ação:** Comparar nomes/schema e executar preflight HTTP.

**Resultado obrigatório:** Número de ferramentas não cresce por host; orientação compatível com identidade/workspace e sem stdio.


### TR4-13-01 — Implementar seleção executor→instalação→workspace

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.01.

**Preparação:** Duas cópias idênticas e Server Linux com executor Windows.

**Ação:** Selecionar B e alterar snapshot no peer API.

**Resultado obrigatório:** UI mantém alvo correto quando válido e recusa stale; fatos remotos não são reavaliados pelo OS do Server.


### TR4-13-02 — Substituir configuração técnica por consentimento agregado

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.02.

**Preparação:** Primeiro uso e uso recorrente local/remoto.

**Ação:** Concluir wizard duas vezes com mesmo binding.

**Resultado obrigatório:** Segundo uso reutiliza sem chave/JSON manual; local não exige Connector; remoto não pede provider secret ao Server.


### TR4-13-03 — Implementar acompanhamento por IDs e estados honestos

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.03.

**Preparação:** Resposta perdida após admissão e evento terminal posterior.

**Ação:** Operar UI e reconectar SSE.

**Resultado obrigatório:** Mesmo ID reaparece e estado converge sem segundo start; UI offline não altera ACK durável.


### TR4-13-04 — Concluir CLI humana/headless e logs observadores

**Estado:** NOT_RUN. **Camada:** `cli_integration`. **Tarefa:** NS13.04.

**Preparação:** Ambiguidade de aliases e prompt desabilitado.

**Ação:** Executar start/status/logs/stop com timeouts.

**Resultado obrigatório:** Erros estáveis e ação corretiva; identidade correta; follower termina sem matar runtime.


### TR4-13-05 — Expor diagnóstico e aprovações sem vazar dados

**Estado:** NOT_RUN. **Camada:** `ui_security`. **Tarefa:** NS13.05.

**Preparação:** Usuário de teste autorizado e agente com leitura restrita.

**Ação:** Consultar views/log/export e responder pedido por UI.

**Resultado obrigatório:** Scopes/reasons úteis sem secrets; canal de apresentação não torna agente seu próprio aprovador.


### TR4-14-01 — Recuperar histórico antes de admitir após restart

**Estado:** NOT_RUN. **Camada:** `restart_integration`. **Tarefa:** NS14.01.

**Preparação:** Receipt real em disco, processo aplicativo novo e binário removido.

**Ação:** Reiniciar host e consultar client intent/operation/session.

**Resultado obrigatório:** Histórico responde; ownership desconhecido permanece; nenhum novo spawn para recuperar dados.


### TR4-14-02 — Invalidar autoridade em todas as superfícies

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS14.02.

**Preparação:** CAS perdido para geração mais nova e ACK perdido após revoke.

**Ação:** Consultar, tentar submit antigo e recuperar storage.

**Resultado obrigatório:** Contexto antigo zero efeito; rollback comprovado recupera disponibilidade; verdadeiramente unknown continua restrito.


### TR4-14-03 — Implementar shutdown DRAINING_PENDING com orçamento único

**Estado:** NOT_RUN. **Camada:** `core_fault_injection`. **Tarefa:** NS14.03.

**Preparação:** Dois runtimes, open tardio, close travado e release pendente.

**Ação:** Parar Server e depois restaurar backend.

**Resultado obrigatório:** Prazo público limitado; ambos relatados; força não espera storage; segunda recuperação alcança mesmos owners sem duplicação.


### TR4-14-04 — Aplicar quotas e cache limitados com medições

**Estado:** NOT_RUN. **Camada:** `load`. **Tarefa:** NS14.04.

**Preparação:** Base sintética e flood de um executor com outro legítimo.

**Ação:** Medir lookup/memória/filas e enviar controle sob carga.

**Resultado obrigatório:** Sem full enumeration por onboarding; memória bounded; controles e outro agente progridem; resultados e hardware registrados.


### TR4-14-05 — Testar falhas de processo e limites de plataforma

**Estado:** NOT_RUN. **Camada:** `os_backend`. **Tarefa:** NS14.05.

**Preparação:** Backend real disponível ou bloqueio documentado.

**Ação:** Matar supervisor de laboratório e observar árvore própria.

**Resultado obrigatório:** Apenas ownership comprovado é controlado; backend ausente é BLOCKED/NOT_RUN, não PASS universal.


### TR4-15-01 — Executar M0–M3 com preservação e retomada

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS15.01.

**Preparação:** Snapshot legado com endpoints negados, jobs históricos e keys.

**Ação:** Interromper backfill e retomar duas vezes.

**Resultado obrigatório:** Mesmos IDs/negações/conteagens; batches convergem; nenhuma migração abre processo.


### TR4-15-02 — Drenar owner antigo antes de trocar execução

**Estado:** NOT_RUN. **Camada:** `migration_runtime`. **Tarefa:** NS15.02.

**Preparação:** Sessão antiga ativa e outra com resultado incerto.

**Ação:** Executar cutover controlado e tentar abrir substituto.

**Resultado obrigatório:** Ativa encerra pelo mecanismo correto; unknown não duplica; rollback não reativa stdio.


### TR4-15-03 — Remover loaders/codecs duplicados depois de paridade

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS15.03.

**Preparação:** Busca estática de imports/Popen e testes de comportamento local.

**Ação:** Executar verificação de fronteiras e paridade delimitada.

**Resultado obrigatório:** Runtime físico só existe no Core; domínio e HTTP MCP preservados; nenhum import da aplicação Connector.


### TR4-15-04 — Migrar configuração e documentar rollback seguro

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS15.04.

**Preparação:** Falha de apply e tree com marker de outro binding.

**Ação:** Aplicar/repetir/migrar configuração e ensaiar restore.

**Resultado obrigatório:** Config alheia intacta; rollback recusado quando inseguro; histórico e operações unknown preservados.


### TR4-15-05 — Atualizar documentação e instruções operacionais

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS15.05.

**Preparação:** README/help/resources/dashboard atualizados.

**Ação:** Comparar docs com APIs e matriz de capacidade.

**Resultado obrigatório:** Nenhum comando fictício apresentado como existente; docs não contradizem gate/qualificação e negações.


### TR4-16-01 — Construir artefatos imutáveis e contratos instalados

**Estado:** NOT_RUN. **Camada:** `packaging`. **Tarefa:** NS16.01.

**Preparação:** Ambiente isolado sem fonte no sys.path.

**Ação:** Instalar e executar smoke público.

**Resultado obrigatório:** Hashes/versões registrados; serve-lite funcional sem torch novo; nenhum schema é obtido remotamente em execução.


### TR4-16-02 — Executar conjunto completo de regressões sem inflar números

**Estado:** NOT_RUN. **Camada:** `regression_suite`. **Tarefa:** NS16.02.

**Preparação:** Ambiente atual e fixtures de fault injection.

**Ação:** Rodar duas vezes casos de corrida e uma suíte completa.

**Resultado obrigatório:** Resultados por camada/node/versão; nenhum PASS sem execução; falha externa distinguida de defeito funcional.


### TR4-16-03 — Qualificar ciclo local sem Connector instalado

**Estado:** NOT_RUN. **Camada:** `provider_local`. **Tarefa:** NS16.03.

**Preparação:** Um SO/provider autorizado e pacote Nexus/Core apenas.

**Ação:** Executar caminho local ponta a ponta.

**Resultado obrigatório:** Mesmo adapter Core; nenhum Connector/WSS local obrigatório; governança e shutdown demonstrados.


### TR4-16-04 — Qualificar ciclo remoto heterogêneo

**Estado:** NOT_RUN. **Camada:** `multi_host`. **Tarefa:** NS16.04.

**Preparação:** Topologia A/B/C autorizada com ao menos um Windows/Unix pertinente.

**Ação:** Executar J01–J34 e TR4 correspondentes com artefatos exatos.

**Resultado obrigatório:** Nenhum filesystem remoto resolvido em A, nenhuma execução duplicada, mesmos IDs; limitações de provider/SO explícitas.


### TR4-16-05 — Emitir decisão por escopo e handoff final

**Estado:** NOT_RUN. **Camada:** `release_review`. **Tarefa:** NS16.05.

**Preparação:** Todas as evidências anteriores e casos NOT_RUN remanescentes.

**Ação:** Revisar cada gate e requisito original preservado.

**Resultado obrigatório:** Decisão proporcional, sem ambiguidades; outro agente consegue instalar artefato e repetir campanha sem inferir campos/rotas.


### TN-01 — Baseline

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS00.05.

**Preparação:** Executar build/testes existentes no HEAD efetivo e comparar com referência.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Falhas anteriores separadas; novos testes de regressão rastreados.


### TN-02 — Crosswalk

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS00.05.

**Preparação:** Comparar dois planos antigos, PR34 e remote-executors com G01–G20.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Todo requisito preservado/substituído/descartado tem justificativa; sem dois backlogs concorrentes.


### TN-03 — Migração nova/legada

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Aplicar migrações em DB vazio e snapshot legado, repetir e interromper backfill.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Retomada idempotente; agent/workspace IDs e histórico preservados.


### TN-04 — Contrato único

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Alterar hash/schema de consumidor e tentar major incompatível.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CI/negociação detecta divergência antes de efeitos.


### TN-05 — Boundary

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Importar Server sem Connector/provider local; inspecionar árvore de imports.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Server funciona; física nativa só no Core e sem ciclos de dependência.


### TN-06 — Identidade chave

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Autenticar A e enviar hint/payload com agent_id B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Negação antes de bind/spawn; nenhum Agent criado ou identidade alterada.


### TN-07 — Importação sem rotação

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Configurar Connector com chave já usada por MCP; chamar MCP novamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma identidade e chave continuam válidas; issue_key não é acionado.


### TN-08 — Revogação e dois canais

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Rotacionar/revogar key e capability MCP HTTP com WSS/HTTP ativos ou particionados separadamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Invalidação/expiry bloqueiam efeitos da sessão em qualquer caminho; tickets NXL não ampliam escopo MCP.


### TN-09 — Self permission

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Agente autenticado tenta bind/grant de outro ou habilitar método negado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Políticas existentes preservadas; nenhum autoapprove de escalada.


### TN-10 — Local nativo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Instalar Nexus + Core, sem aplicação Connector, e abrir Codex qualificado local.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Serve hospeda executor e controla runtime sem WSS/pareamento local.


### TN-11 — Owner local

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Duas CLIs e cliente MCP HTTP pedem abertura com mesma chave idempotente; fechar clientes.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Owner único e execução idempotente; runtimes independentes continuam, sem processo MCP stdio.


### TN-12 — Shutdown Server

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Encerrar serve com runtime próprio e alvo externo anexado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core drena/encerra árvore própria e desanexa externo; relatório por sessão.


### TN-13 — Path remoto

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Server Linux recebe vínculo de diretório Windows validado pelo Connector.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Nenhum realpath/isdir local sobre path remoto; identidade lógica correta.


### TN-14 — Workspace equivalência

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Mesmo Git/path em hosts diferentes e manifesto falsificado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Não mescla/autoriza automaticamente; binding explícito e escopado.


### TN-15 — Setup sem argv

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Selecionar binários Codex/Pi com espaços via UI normal.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core adiciona argumentos obrigatórios; usuário não edita JSON.


### TN-16 — Reuso e drift

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Repetir start aprovado, depois trocar root/binário/permissão.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro reutiliza; mudança relevante exige reprepare/approval, não expansão silenciosa.


### TN-17 — Canal WSS

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Negociar TLS/protocolo com peer e depois Connector real.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Saída remota bidirecional, sem callback/porta entrante no host.


### TN-18 — Lanes

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Autenticar lane A; tentar operações B; anexar B com própria prova.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** B só disponível após ticket válido; revoke A não empresta sua autoridade a B.


### TN-19 — Instâncias concorrentes

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Abrir canais conflitantes da mesma instalação e reenviar geração antiga.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CAS/fencing impede dois owners ativos ou takeover silencioso.


### TN-20 — Controle sob carga

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Inundar texto enquanto chega interrupt/revoke.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Limites/priority preservam controle; métricas de fila em bytes disponíveis.


### TN-21 — Idempotência

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Repetir operation_id/hash e depois alterar payload.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro devolve recibo sem efeito novo; segundo OPERATION_CONFLICT.


### TN-22 — ACK durável

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Cair antes/depois do commit de evento e antes do ACK.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Replay deduplicado; watermark só confirma persistido.


### TN-23 — Unknown

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Perder confirmação depois de write possível no harness.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** OUTCOME_UNKNOWN consultável; nenhum novo turno/host automático.


### TN-24 — Consumo exclusivo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** MCP pull, runtime local e remoto competem pela mesma entrega.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um consumidor de execução; outbox não cria outra tarefa.


### TN-25 — Eventos fora de ordem

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Terminal chega antes de ACK, duplicatas/gaps/geração antiga.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Reducer conserva fatos; gaps explícitos; histórico não autoriza novo efeito.


### TN-26 — Ferramentas canônicas

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Executar via MCP HTTP direto local/remoto e bridge nativa não MCP com o mesmo agente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmos casos de uso/grants/claims e auth; nenhum proxy/fachada MCP no caminho.


### TN-27 — Handoff

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Finalizar turno sem complete governado e depois emitir complete válido.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro não completa handoff; segundo preserva evidência/correlação/budget.


### TN-28 — HITL

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Duas interfaces decidem, chega decisão tardia e agente tenta se autoaprovar.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CAS único, turno/request corretos e autoridade existente exigida.


### TN-29 — MCP HTTP e remoção stdio

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Upgrade com MCP HTTP e antiga entrada Nexus stdio selecionada; invocar entrypoint removido.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** HTTP preservado; migração orientada sem key nova; stdio ausente/erro prescritivo sem transporte ou shim; outras entradas intactas.


### TN-30 — Superfície compacta

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Comparar catálogo/schema/tokens com baseline e adicionar muitos hosts.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Catálogo não replica tools por conexão; diferença justificada/medida.


### TN-31 — CLI consistente

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Start/status/interrupt/stop/logs com JSON e timeout.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmo domínio/recibo da API; timeout de espera não reenfileira efeito.


### TN-32 — UI primeiro/segundo uso

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Completar fluxo local e remoto duas vezes.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem endpoint/profile/JSON/token manual recorrente; escopo compreensível.


### TN-33 — Modo explícito

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Escolher tools-only, managed e attach.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** UI informa sessão criada/reutilizada/anexada; não promete adotar conversa atual.


### TN-34 — Estados honestos

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Daemon online, provider ausente, approval pendente e resultado unknown.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Cada condição aparece distintamente; nenhuma marcada como runtime pronto.


### TN-35 — Input hostil

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Enviar paths/plugins/argv/env e identidade forjados pelo wire.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Validação/autoridade impede execução/configuração fora do binding.


### TN-36 — Partição/lease

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Desconectar runtime durante revoke; alterar relógio; restaurar canal.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem novas autorizações offline; limite de lease respeitado e reconciliação anterior à admissão.


### TN-37 — Secrets

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Inspecionar logs/UI/exports/headers de erro/métricas.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem chave/ticket/provider secret; cardinalidade de labels limitada.


### TN-38 — 100 mil identidades

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Sem provider, popular 100 mil agentes e conectar um por chave.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Lookup indexado e retorno escopado; nenhuma enumeração global ou thread por agente.


### TN-39 — Cache bounded

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Exercer muitas chaves e revogar em cache; simular churn.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Memória limitada e invalidação síncrona; epoch não permanece autorizado.


### TN-40 — Rollback dados

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Restaurar snapshot/versão suportada após backfill e execução controlada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Dados e políticas preservados; rollback inseguro recusado/explicado.


### TN-41 — Build limpo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Instalar wheel Nexus serve/serve-lite e Core fixado sem clones irmãos.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Assets/dependências corretos e modo local disponível.


### TN-42 — Server sem harnesses

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Subir A sem binários, provider keys ou diretórios de B/C.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** API/recepção remota funcionam; não solicita instalação local de provider.


### TN-43 — Multihost

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Executar campanha J com A/B/C e mesmo Core wheel.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Controles/eventos/HITL e identidade independem do host central.


### TN-44 — Fault conjunto

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Executar partições, crash e ACK perdido nos três artefatos reais.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Resultados correspondem a efeitos possíveis e sem execução duplicada.


### TN-45 — Release gate

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Revisar evidências com SHAs/versões e casos ainda NOT_RUN.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Somente capacidades demonstradas qualificadas; bloqueios externos explícitos.


### J01 — Identidade canônica

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Criar agente previamente no Nexus e configurar MCP com sua key; importar a mesma no Connector.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Nenhum segundo Agent/user; MCP continua válido, mesmo agent_id em mensagens e sessões.


### J02 — Não rotacionar para conectar

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Usar Server que guarda somente hash; gerar comando para identidade existente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Comando pede/importa key existente de forma protegida; não chama issue_key silenciosamente.


### J03 — Autenticação errada

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Key A com hint B; depois ticket A tenta abrir lane de B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Negação antes de configuração/spawn; nenhuma atribuição por payload.


### J04 — Nexus local puro

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Instalar Nexus/Core, sem app Connector, e abrir/gerir cada runtime gerenciado qualificado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core embutido em serve, sem daemon Connector, pareamento ou WSS local obrigatório.


### J05 — Servidor realmente remoto

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** A sem executáveis/providers/projetos; B/C com Connector/Core e harnesses.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Operações e streams funcionam; Server não faz realpath/spawn de B/C.


### J06 — Rede outbound

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Firewall de B/C nega conexões entrantes e permite WSS/HTTPS ao Server; testar também o processo/sandbox do harness.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Controle via Connector e MCP HTTP direto via harness funcionam com tráfego de saída; nenhuma porta MCP local exigida.


### J07 — Paths heterogêneos

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** A Linux, B Windows e C Unix; roots diferentes do mesmo e de outros repositórios.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Vínculos lógicos autorizados, validação física local e nenhuma fusão por path/Git.


### J08 — 100 mil agentes

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Sem providers, popular 100 mil identidades no Server e importar uma key em B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Queries indexadas e escopadas; não listar tudo nem criar recursos por agente offline.


### J09 — Um daemon, várias identidades

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** B importa agentes A1/A2 que usam o mesmo binário Codex e um agente Pi.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sessões/credentials/lanes isoladas, sem daemon por agente ou prompt broadcast indevido.


### J10 — Dois Servers

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** B conecta dois Servers distintos e remove/revoga binding em apenas um.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Namespaces, processos, cofre e tickets do outro preservados.


### J11 — First-use/second-use

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Configurar por comando da tela e executar runtime start repetidamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Setup agregado uma vez; depois sem JSON/argv/endpoint/profile/grant/chave manual recorrente.


### J12 — Daemon automático

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Connect e runtime start concorrentes com daemon parado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Uma instância; daemon ready não abre todos os harnesses descobertos.


### J13 — Terminal independente

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Fechar CLI de start, TUI/log follower e encerrar cliente MCP HTTP tools-only independente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Daemon e runtimes independentes continuam; fechar cliente HTTP não encerra supervisor nem outra sessão.


### J14 — Turno versus processo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Enviar trabalho, interrupt, novo turno e runtime stop.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Cancelamento preserva runtime quando suportado; stop encerra recursos próprios, não identidade/histórico.


### J15 — Shutdown/crash

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Stop daemon/serve; depois SIGKILL do supervisor em cenário controlado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Drain/containment e relatório real; sem kill alheio ou trabalho indefinido não declarado.


### J16 — MCP HTTP tools-only direto

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Usar conversa não gerenciada com MCP HTTP antes/depois de instalar e desligar Connector; também testar sem Connector instalado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Harness chama somente o Server; identidade preservada, nenhum proxy/subprocesso MCP e nenhuma adoção de conversa pelo runtime.


### J17 — Work bridge nativa não MCP

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Pi sem MCP HTTP recebe tarefa e chama contexto/claim/complete via extensão qualificada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmo domínio canônico; nenhum servidor/proxy/envelope MCP no Core/Connector; texto livre não completa handoff.


### J18 — Consumo exclusivo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Uma entrega com MCP pull e dois runtimes disponíveis ao mesmo agente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um consumidor lógico; sem duplo turno/grant/resposta por multiplicidade de conexão.


### J19 — HITL concorrente

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Provider pede aprovação; CLI/UI respondem, agente tenta autoaprovar e decisão chega tarde.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Autoridade existente, CAS, geração/turno corretos; timeout/deny não aprovam.


### J20 — Recebido não é concluído

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Observar ACK WSS, aceitação nativa, fim de turno e handoff em cada adapter.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Estados separados, nenhum marco antecipa outro sem evidência.


### J21 — Resposta perdida

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Perder ACK após submit nativo possível, reconectar e repetir consulta/ID.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem replay automático; recibo/unknown/reconciliação pelo mesmo intent.


### J22 — Partição e revogação

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Revogar key com WSS online e depois testar partição prolongada/relógio alterado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Online invalida derivados; offline limita por lease, sem prometer revogação instantânea.


### J23 — Gerações e takeover

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Canal antigo e novo/daemon clonado disputam mesma sessão.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um owner, fencing/reconciliação; sem failover silencioso ou processo duplicado.


### J24 — Eventos/retention

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Interromper ACK, enviar duplicatas/out-of-order e ultrapassar retenção.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Ingressão durável idempotente e watermark contíguo; gap explícito, terminais não ocultos.


### J25 — Saturação

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Flood texto, disco cheio e consumidor lento enquanto chega interrupt.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Memória/journal/queues finitos, faixa crítica preservada e novas admissões bloqueadas quando necessário.


### J26 — Drift/config segura

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Trocar binary/root/symlink/home/hook e editar MCP existente durante setup.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Reprepare/approval/CAS; sem execução ampliada, JSON destruído ou secrets centrais.


### J27 — Quatro adapters

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Qualificar Codex/Pi/Claude managed e attach existente por versão/SO delimitados.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma implementação Core local/remota e capabilities comprovadas, sem sucesso simulado.


### J28 — Upgrade/rollback

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Migrar Nexus legado, atualizar Connector/Core com journal pendente e instalar wheels limpos.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Histórico/IDs/negações preservados, drain/reconcile e dependências acíclicas.


### J29 — Segredos/ameaças

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Inspecionar argv/log/config/export/metric; tentar handle/agent/server spoof e shell injection.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem chave canônica/admin de terceiros/provider secrets vazados ou efeito fora do escopo.


### J30 — Release coordenado

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Conferir resultados/SHAs/wheel hashes e gates provider/SO/multi-host em três relatórios.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma evidência, bloqueios explícitos e nenhuma alegação de produto completo baseada só em fakes.


### J31 — Remoção MCP stdio

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Instalação limpa e upgrade do Nexus v0.2.0 com configuração MCP stdio; inspecionar entrypoints, módulos, exemplos e migração selecionada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** MCP stdio ausente, sem shim/fallback; MCP HTTP direto mantém agente/key/histórico e outras entradas não são alteradas.


### J32 — MCP HTTP local nativo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Somente Nexus/Core no host; abrir runtime gerenciado com MCP HTTP para o próprio Server.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem Connector ou fachada; cliente chama endpoint HTTP de serve com capability válida e o Core só configura o cliente.


### J33 — Fronteira protocolo/transporte

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Exercitar stdio nativo dos adapters e inspecionar artefatos/portas de Connector/Core; testar harness com MCP apenas stdio.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Protocolos nativos funcionam; nenhum serviço/extra/CLI MCP/proxy; cliente incompatível recebe diagnóstico sem fallback stdio.


### J34 — Dois canais e autorização

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Em runtime remoto com MCP HTTP direto, derrubar apenas WSS e depois apenas HTTP; expirar/revogar capability e manter outra conversa tools-only independente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sessão gerenciada respeita lease/grants/revogação sem bypass, replay ou túnel; canal HTTP tools-only legítimo mantém política própria sem exigir daemon.


## Gates que não podem ser abreviados


G0: documento/artefato de desenvolvimento. G1: Server local real com Core, sem Connector; G2: Server e Connector reais em hosts separados e mesmo wheel; G3: escopo original por provider/SO e J-matrix. Candidato no catálogo não equivale a build qualificado. Fixture de Windows em Linux não equivale a teste Windows.

## Campanhas negativas transversais


Os casos TR4 devem manter as barreiras enquanto a asserção é feita: autorização vencida antes da escrita, lock/worker de dados bloqueado durante interrupt, journal bloqueado durante força, ACK2 ausente durante espera de lote2, callback antigo de attach após rotação, resposta HTTP perdida após commit e boot sem binário para história. Liberar barreira só no teardown. Contar bytes/chamadas/receipts no componente exercitado, não a presença de um método chamado guarded.

---

<a id="documento-06"></a>

**Documento-fonte: `06_HANDOFF_CORE_CONNECTOR.md`**

# Handoff explícito — Server, Core e Connector

**Este documento fixa trabalho coordenado; não afirma que as interfaces R4 já foram implementadas.** O Server é o destinatário principal. O agente do Server não edita os outros repositórios sem atribuição/autorização; abre os pedidos abaixo com IDs e fixtures, e mantém gates externos visíveis.

## 1. Baselines e situação

| Produto | Fonte conferida | O que pode ser usado agora | O que não presumir |
|---|---|---|---|
| Nexus | feature/v0.2.0, 7ed52c22865a92c3768bc32508ed9e35dc5efdc3 | Domínio/HTTP/CLI/migrações existentes | Executor remoto R4, remoção stdio ou integração Core já feitos |
| Core | 0.2.10.dev0, 1560d314ed2b478515dcbbe533436d7d0b027b09 | create_runtime, catálogo, availability v2, installation_ref/resolve_installation, Journal/ledger/controles | NXL R4 publicado, attach qualificado, E2 multi-host ou mesmo hash de wheel sem verificá-lo |
| Connector | 0.4.0.dev0, 87b8fd2e3e403cb6a70a1ce265618e29c7a6b86c | CLI/daemon/HTTP/WSS e composição parcial em desenvolvimento | CN5 encerrado, remote open completo, decisões persistentes ou inventário/UI remoto qualificados |

O CN5 documenta Q01 proposta redigida/namespace, Q02 producer de decisão, Q03 rotação de attach e Q04 publicador interrompido. O plano Server incorpora essas invariantes. Não herdará flags de prontidão do Connector sem fatos de negociação e teste do caminho real.

## 2. Entregas obrigatórias do Core

### CORE-R4-01 — Bundle executável R4

**Entrada:** delta em `contratos/nxl-r4-delta.json`, documento 02, schemas/fixtures de planejamento. **Saída:** wheel com revisão R4, schema fechado por verbo, codecs/reducers e hash vetores; R3 preservado para histórico.

Passos: copiar para uma pasta de especificação do Core; implementar geração na fonte única; declarar novos ACKs de attach/reconcile e lease correlacionada; owner obrigatório; controlar targeting de adapter; executar casos positivos/negativos contra consumidores sintéticos dos dois aplicativos. Não instalar schemas do diretório de planejamento como runtime autoral do Server.

**Aceite:** payload extra ou permissão autodeclarada falha antes do efeito; r3 não é aceito como r4 pelo mesmo major; enum deriva do registry; todos os eventos/receipts históricos usados na migração continuam lidos pelo decoder apropriado. Não re-hashear registros persistidos.

### CORE-R4-02 — Estabilizar helpers públicos usados pelos hosts

**Entrada:** APIs existentes em discovery, harness_config, Journal e composition. **Saída:** documentação/exports/testes de consumidor instalado que fixem as assinaturas realmente suportadas.

Não acrescentar um daemon ao Core. O objetivo é garantir discovery sem dummy runtime, preservação de InstallationCandidate completo, renderização HTTP direta e leitura finita de histórico. Caso um helper continue provisório, publicar a fachada pública mínima no próprio Core e adaptar os hosts uma vez. Não permitir imports `native.*` nos aplicativos.

**Aceite:** catálogo/discovery/evaluation/resolver funcionam no wheel sem classe privada; a operação de listar não exige iniciar provider, obter credencial ou criar candidato falso.

### CORE-R4-03 — Projeções de targeting e fatos de capacidade

**Entrada:** capacidades já implementadas nos adaptadores e testes atuais. **Saída:** campos públicos que permitam ao Server saber se controle requer native turn ID ou usa run sem ID, sem array específico por harness no Server.

Não ampliar capacidades por descrição. Pi com steering de próxima fronteira não vira IMMEDIATE. Attach segue não qualificado. Alterar schema R4 e fixtures quando o campo cruza wire. `execute_work` depende de tool path e aprovação, não só protocol support.

**Aceite:** Server não importa provider nem codifica regras próprias para construir target; consumidor passa somente combinações demonstradas, Core revalida no efeito.

### CORE-R4-04 — Artefato e compatibilidade por hash

Gerar wheel/sdist com dependências fixadas e manifest R4; manter package version independente de wire revision. Publicar **localmente para os agentes**, sem PyPI/release automático. Registrar hash completo, não fragmento de README. Consumidores instalam o mesmo arquivo, não dois builds diferentes com o mesmo número.

**Aceite:** import -I, conformance, catálogo v1, availability v2, duas instalações iguais resolvidas inequivocamente, testes históricos e novas fixtures passam na camada declarada. Provider/SO/multi-host continuam gates separados.

## 3. Entregas obrigatórias do Connector

### CON-R4-01 — Concluir CN5 sem enfraquecer domínio

Executar o pacote CN5 inteiro. Proposta operacional íntegra e display redigido são separados; namespace chega até SessionKey; producers sobrevivem ao waiter; attach novo é agendado após término do antigo; reconexão recria publicador necessário. Cada Q fecha com reprodução na entrada efetiva, não populando estado privado para evitar o problema.

### CON-R4-02 — Um único dispatcher de efeitos

Atualizar `RuntimeManager.start/submit/stop` usados pela CLI: registrar client_intent_id localmente antes de POST, chamar Server resolve/admit e consultar resultado. **Não chamar Core diretamente nessa trilha depois de pedir operação canônica.** A chamada Core fica na entrada de executor do dispatcher WSS R4 ou no shutdown proprietário interno, que não é uma nova intenção de trabalho do usuário.

Implementar remote runtime.open com refs de realização e lease inicial; preservar operation_id/scope/hash. Não anunciar G2 enquanto o verbo permanecer UNSUPPORTED. Corpo raw executable/argv/env recebido da rede é recusado.

### CON-R4-03 — Consumir DTOs HTTP R4 completos

Atualizar MeInfo/BindingProposal/IntentResolution/DecisionView/receipts e revisão em headers. Resposta de approval não é bool para aplicar nativo localmente; application operation chega pelo dispatcher único. Receipts usam endpoint próprio ou NXL receipt, nunca POST de execução com payload diferente.

Migrar clientes com validação explícita de revisão. Não manter fallback de permissões para simulação no código produtivo. GET por client_intent_id recupera operação quando response se perde.

### CON-R4-04 — Lanes e lease com ACK efetivo

Adotar binding.attached/reconcile.accepted, request tokens e source connection generation. Lane só pronta após ACK da mesma epoch. Rotação usa provider novo e agenda substituto sem emprestar sua revision ao resultado anterior. Guardar expiração do ticket e renovar automaticamente dentro do escopo.

Lease request captura t0 antes de enviar; reply serial é aplicada uma vez; replay não reancora prazo. Core recebe renovação/revocation por API própria antes de tornar a sessão produtiva. Nenhum `allowed.update()` local amplia grant.

### CON-R4-05 — Snapshot e resolução no mesmo inventário

Produzir `ExecutorInventorySnapshot` com candidato completo, disponibilidade Core e hash de todas as evidências. Publicar por HTTP na origem aprovada sob ticket próprio; UI remota devolve ref/revisão/escopo. Resolver somente pelo Core no executor original; não reconstruir Pi por executable isolado ou validar revisão de `[candidate]` como se fosse a revisão do inventário inteiro.

Campos locais sensíveis e paths não são publicados. Emitir nova sequência/atualizar TTL sem mudar digest quando a evidência não mudou; update de conteúdo com mesma versão muda digest.

### CON-R4-06 — Evento/ACK/recibo recuperáveis

Preservar namespace e connection origin nos ACKs; esperar target do batch; remote ACK e aplicação Core são fatos separados. Ler journal em páginas finitas. Backpressure não apaga receipt já produzido; reconnect retoma streams mesmo sem nova mensagem do harness. Queries históricas abrem journal sem binário.

### CON-R4-07 — Aprovação pelo dispatcher e chave completa

A CLI apenas propõe/consulta decisão. Após Server confirmar, operação de aplicação é recebida no WSS R4 e chama Core com request operacional original e argumentos nomeados. Não executar novamente em `approval.decision` notification ou depois do retorno HTTP. Preservar registro/tombstone por escopo e idempotência; retorno perdido não gera novo ID.

Input sensível segue o contrato de retenção explicitamente escolhido; sem prova de persistência recuperável, não anunciar recovery pós-crash de conteúdo bruto. Não ampliar autoridade do agente para substituir operador.

### CON-R4-08 — Lifecycle e pacote integrado

Conservar host/Core/store enquanto houver producer/recurso/obrigação; decisões de stop usam recibo e prova, não `stage != UNKNOWN`. Shutdown com unknown mantém supervisor/IPC de recuperação ou transferência de SO qualificada; exit code não é mecanismo de ownership. Pin exato de Core R4 e fixtures de dois namespaces; sem servidor ou proxy MCP.

## 4. O que o agente Server deve entregar aos outros dois

Entregar `/v1` protocol/me, registro executor, snapshots/realizações, prepare/apply, tickets, resolve/admit/query/receipts, capability, decisions e native-actions com OpenAPI/fixtures geradas dos schemas acordados. Entregar endpoint WSS R4 e peer de laboratório capaz de controlar abertura remota, ACKs, rotações, lease e falhas de resposta.

A fila de operação do Server é a única autoridade de execução; os mocks dos aplicativos devem representar essa regra. O peer não retorna sempre applied=true, READY ou lease estendida. Deve conseguir recusar, expirar, perder ACK depois de commit e consultar o mesmo resultado.

## 5. Ordem coordenada sem bloqueio circular

**Marco A — contrato:** Server NS00–NS03 e Core CORE-R4-01/02/03; Connector conclui CN5 e prepara DTOs. Os três agentes podem começar agora. A primeira entrega compartilhada é o contrato, não o provider inteiro.

**Marco B — inventário:** Core existente já permite catálogo/availability/ref. Server NS04/05 + Connector CON-R4-05 integram snapshot e seleção. UI pode usar fixtures do contrato enquanto endpoint é implementado, sem declarar integração completa.

**Marco C — uma execução:** Server NS06–NS09 e Connector CON-R4-02/03/04 atravessam open/submit/control/receipt com um peer de Core. Não aguardar a campanha multi-host para escrever remote open: isso geraria dependência circular.

**Marco D — governança:** ingressos/ACK/decisions/native-actions completam o ciclo. Então testar provider real local e remoto no mesmo wheel e ampliar casos.

**Marco E — release delimitada:** somente depois dos gates de plataforma/provider/aplicativos. Testes locais do Core não encerram o aceite do Server; XML de um repo não é nova execução em outro.

## 6. Lista de bloqueios legítimos

Bloqueia novo efeito remoto: bundle R4 não publicado, Connector sem remote open, lane sem ACK, sessão sem lease aplicada, snapshot stale, contexto incompatível ou pending decision sem autoridade. Não bloqueia desenvolvimento de UI, migrações, auth, catálogo ou domínio com fixtures.

Não aceitar como “bloqueio externo”: erro de namespace, código que ignora uma revisão, enum local duplicado, método não ligado ao caller, producer cancelado por waiter ou retorno falso de prontidão. Esses são defeitos da aplicação responsável e devem ser corrigidos nela.


---

<a id="documento-07"></a>

**Documento-fonte: `07_RASTREABILIDADE_R3.md`**

# Rastreabilidade e substituição do plano Server R3

R4 substitui o backlog ativo do Server, não apaga requisitos. Cada linha original abaixo tem sucessores explícitos; os 45 TN e 34 J foram incorporados à matriz com estado NOT_RUN. Os planos do Core/Connector não são considerados implementados porque seus requisitos foram mapeados.

| Tarefa R3 | Requisito original | Tarefas R4 |
|---|---|---|
| N00.1 | Registrar HEAD/branch/working tree, versões Python/MCP/schema, comandos de build e testes; preservar arquivos modificados e falhas preexistentes separadas. | NS00.01, NS16.02 |
| N00.2 | Ler os dois planos anteriores, PR34 e remote-executors; criar crosswalk G01–G20 e marcar cada requisito como preservado, substituído, já implementado ou a investigar. | NS00.02 |
| N00.3 | Inspecionar fluxo de chave, cache, middleware, operador reservado, grants e self-open; demonstrar que chave resolve agente e que emitir nova chave invalida a anterior. | NS03.01, NS03.05 |
| N00.4 | Reproduzir setup local e bugs de argv/path/plataforma no HEAD; criar regressões para os confirmados, sem tratar comentários/planos como evidência de execução. | NS00.05, NS07.02 |
| N00.5 | Inventariar realpath, spawn, ownership, delivery, approvals, boot e todo MCP stdio (entrypoints/config/módulos/docs/testes); medir baseline MCP HTTP e instalar backlog/status/evidência da revisão 3. | NS01.01, NS01.02 |
| N01.1 | Consumir bundle imutável K01 com manifest/hash; integrar tipos via API pública sem manter cópia autoral de NXL no Server. | NS00.03, NS00.04 |
| N01.2 | Modelar executor/binding/workspace binding, credential epoch, auth/config revision, operações e eventos; preservar IDs e serviços existentes onde possível. | NS02.01, NS02.02 |
| N01.3 | Criar migrações aditivas idempotentes e índices por key hash, agente/binding/executor/workspace e operation/event IDs; definir backfill retomável. | NS02.02, NS15.01 |
| N01.4 | Definir porta de execução embutida/remota, contexto autenticado e rotas do Anexo A no OpenAPI do produto; fechar validação de entrada/erro antes de efeitos. | NS06.01, NS08.01 |
| N01.5 | Construir reader/writer fixtures legado-novo, testes de boundary e de conflito; registrar política de rollback e incompatibilidade de schema sem downgrade destrutivo. | NS15.01, NS15.04 |
| N02.1 | Implementar /connections/me utilizando o resolvedor de chave existente; comparar agent hint e negar spoofing sem enumerar agentes. | NS03.01 |
| N02.2 | Implementar prepare/apply de binding próprio com CAS, políticas existentes e aprovação agregada; agente não pode habilitar método negado ou se autoaprovar escalada. | NS03.02, NS05.03 |
| N02.3 | Emitir tickets opacos curtos escopados em agente/executor/binding/epoch e capacidades de sessão; não adicionar login de usuário nem chave raiz obrigatória de Connector. | NS03.03, NS03.04 |
| N02.4 | Propagar rotação/revogação para tickets NXL, capabilities MCP HTTP diretas, caches, lanes, leases e bridges não MCP; validar cada audiência sem permitir bypass quando apenas um canal estiver conectado. | NS14.02, NS09.04 |
| N02.5 | Gerar contrato de comando de conexão da tela do agente; importar chave existente por entrada protegida e nunca emitir outra para contornar hash-only; testar comando em shells suportados. | NS03.05 |
| N03.1 | Integrar wheel incremental do Core ao serve e serve-lite; montagem de API/dashboard sem provider/binário local continua válida. | NS01.03, NS07.01 |
| N03.2 | Criar EmbeddedExecutor adaptando journal/event sink/secret resolver e contexto autorizado; não usar WSS/Connector app para executar localmente. | NS07.01, NS07.02 |
| N03.3 | Substituir construção nativa em RuntimeOpen/Control pelo despacho da porta; preservar recibos, reserva idempotente e claims existentes. | NS06.02, NS07.02 |
| N03.4 | Separar supervisor canônico de processo físico; manter wrappers de compatibilidade temporários e eliminar duplicação de adapters após comparação rastreada. | NS15.03 |
| N03.5 | Integrar startup/shutdown do Core ao owner de serve, contenção, readiness e cleanup; CLI/cliente MCP HTTP não são donos de runtime e nenhum processo MCP stdio inicia o Server. | NS07.05, NS14.03 |
| N04.1 | Usar discovery/prepare do Core no executor certo; Server central consulta inventário remoto e nunca qualifica peer pelo próprio os.name. | NS04.01, NS04.02 |
| N04.2 | Implementar criação/resolução de workspace lógico e vínculo físico local com validação no executor; manter aliases de IDs legados e compatibilidade de APIs. | NS02.04, NS05.01 |
| N04.3 | Criar fluxo resolve–diff de confiança–approve/apply–start com etapas reexecutáveis; gerar endpoint/perfil/argv sem pedir ao usuário sua estrutura interna. | NS05.02, NS05.03 |
| N04.4 | Reutilizar binding e sessão compatível, com ambiguidade explícita e intenção nova para --new-session; mudança de root/perfil/harness não amplia escopo silenciosamente. | NS05.04 |
| N04.5 | Corrigir fluxo do campo Executável para consumir templates de Core; segredos/provider home são refs locais e login ausente retorna ação no host adequado. | NS05.05, NS07.03 |
| N05.1 | Implementar upgrade WSS com TLS no deployment, ticket em header, subprotocolo nxl.v1, negociação de limites e erro antes de efeitos para versão incompatível. | NS08.01 |
| N05.2 | Registrar connector/executor como entidades técnicas; autenticar lane inicial e binding.attach adicional com prova de agente independente por ticket. | NS03.03, NS08.02 |
| N05.3 | Gerir geração/ownership de canal por CAS, reconnect, heartbeat, lease autenticado e conflito entre instâncias; não converter WSS ativo em runtime pronto. | NS08.03, NS09.02 |
| N05.4 | Implementar inventory snapshot/delta, filtros por binding e estado de controle; não aceitar atualização global de identidade/permissões vinda do executor. | NS04.03, NS04.04 |
| N05.5 | Adicionar prioridades, limites de bytes/frames, redaction e backpressure; validar proxy reverso e fechamento/deauth por agente sem conceder outra lane. | NS08.04, NS08.05 |
| N06.1 | Reservar operação/outbox com ID/hash antes do envio; mesma intenção retorna recibo, payload conflitante é negado; rede/spawn nunca dentro da transação. | NS06.01, NS06.02, NS06.04 |
| N06.2 | Ingressar eventos com identidade/sequence/hash e ACK pós-commit; projetar fatos idempotentemente e lidar com terminal antes de ACK intermediário. | NS10.01, NS10.03 |
| N06.3 | Reconciliar cursores, operações, sessões e ownership após reconnect/restart; conservar unknown e evitar repetição automática ou realocação para outro executor. | NS14.01, NS09.04 |
| N06.4 | Aplicar mecanismo de consumo exclusivo comum a MCP/local/remoto; preservar quotas, leases, causalidade e budgets ao reconectar. | NS06.05, NS12.01 |
| N06.5 | Testar queda em cada fronteira de commit/envio/aceitação/evento/ACK, evento atrasado e geração antiga; diferenciar evidência histórica de autoridade ativa. | NS10.05, NS16.02 |
| N07.1 | MCP HTTP do Server e bridges nativas não MCP chamam os mesmos casos de uso; Core não importa MessageService nem concede grants. Não criar fachada MCP local/remota. | NS12.01, NS12.02 |
| N07.2 | Emitir capability de sessão aceita diretamente pelo MCP HTTP com agente/workspace/binding/sessão/ações/validade; qualificar renovação e expiração sem proxy/hot-reload presumido, nem chave administrativa no harness. | NS03.04, NS09.05 |
| N07.3 | Distinguir fim de turno de handoff complete; preservar claim, reply target, contexto, evidência, root/parent/correlation e orçamento de relay. | NS12.03 |
| N07.4 | Normalizar pedidos HITL com sessão/turno/request/geração/expiry; aplicar decisão uma vez por CAS e validar autoridade existente de aprovador. | NS11.01, NS11.02, NS11.03, NS11.04, NS11.05 |
| N07.5 | Classificar execute_work somente após caminho de ferramentas comprovado; MCP HTTP direto é padrão para cliente compatível. Pi sem esse cliente usa extensão nativa não MCP qualificada, nunca servidor/proxy MCP. | NS07.04, NS12.04 |
| N08.1 | Expor operações por intenção nas superfícies existentes, compartilhando validação/autorização; evitar tool por host/adapter/CRUD interno. | NS12.05, NS06.01 |
| N08.2 | Implementar namespace CLI runtime com discover/start/status/interrupt/stop/logs/doctor e recibos JSON; não sobrecarregar start como daemon e harness. | NS13.04 |
| N08.3 | Remover MCP stdio, entrypoints e shims legados do Nexus; migrar configuração selecionada para MCP HTTP direto sem rotação de key/novo agente. Preservar outras entradas e SDK major; roots/hints não autorizam filesystem/identidade. | NS01.02, NS01.05 |
| N08.4 | Gerar configuração do cliente MCP HTTP para a URL do Server e capability limitada de sessão, inclusive local nativo. Não exigir Connector ou publicar fachada/backend MCP adicional; validar alcance a partir do harness/sandbox. | NS07.03, NS12.02 |
| N08.5 | Medir catálogo/tokens antes/depois e corrigir crescimento desnecessário; erros de auth/projeto/unknown são prescritivos sem rotinas manuais de grants. | NS12.05 |
| N09.1 | Criar visão por agente com local/remoto/tools-only/managed/attach e host/projeto/status; não adicionar painel de conta de usuário Nexus. | NS13.01, NS13.02 |
| N09.2 | Implementar gerar comando protegido para Connector e fluxo local nativo; renderizar política/aprovação agregada em linguagem de intenção. | NS03.05, NS13.02 |
| N09.3 | Retirar JSON, nomes/IDs de endpoint/perfil, argumentos e token de uma hora do caminho normal; avançado apenas para diagnóstico e opções justificadas. | NS13.02 |
| N09.4 | Implementar start/reuse/interrupt/stop/inspeção/logs com recibos e estado de operação; timeout não dispara nova sessão automaticamente. | NS13.03, NS13.04 |
| N09.5 | Mostrar desconhecido/offline/auth_required/drift/approval por camada e capabilities reais; testar UI em locale/shell/path com espaços e preservação de config MCP. | NS13.05 |
| N10.1 | Executar testes de spoof de agente/Server/executor, replay de ticket, lane não autenticada, mutation de escopo e tentativa de plugin/shell remoto. | NS08.04, NS09.04 |
| N10.2 | Validar invalidation de chave em trânsito e revogação durante turno/approval; impedir renovação após revogação e mostrar limite real de partição/lease. | NS14.02, NS09.05 |
| N10.3 | Exercitar frame/journal flood, slow consumer, disco cheio e controle urgente; recursos finitos e isolamento por binding/Server são obrigatórios. | NS08.05, NS14.04 |
| N10.4 | Validar restart do owner, morte do executor local e reconnect remoto com operações desconhecidas; não converter heartbeat em prova de processo vivo/morto. | NS14.01, NS14.03, NS14.05 |
| N10.5 | Auditar logs/metrics/export/UI para secrets e roots indevidos; separar dados históricos de geração antiga de nova autoridade e registrar findings resolvidos. | NS13.05, NS16.02 |
| N11.1 | Executar cenário sintético de 100 mil agentes sem providers: onboarding por key index, paginação, sem full enumeration ou estruturas por identidade offline. | NS03.01, NS14.04 |
| N11.2 | Limitar cache positivo por tamanho/TTL com invalidação síncrona; medir touch/queries no hot path e evitar escrita por delta de streaming. | NS14.04 |
| N11.3 | Migrar instalação legada, permissões e endpoints para executor local; comparar dados/IDs/inbox/handoff antes/depois e retomar backfill interrompido. | NS15.01, NS15.02 |
| N11.4 | Remover código nativo duplicado após paridade, referências ao Core hospedado no Connector e onboarding user-centric; marcar planos antigos superseded preservando evidência. | NS15.03, NS00.02 |
| N11.5 | Entregar runbooks de backup/restore/rollback e upgrade com drain; não indicar downgrade de schema irreversível como seguro. | NS15.04, NS15.05 |
| N12.1 | Gerar wheel/sdist de Nexus com dependência Core versionada e assets corretos; instalação limpa sem clone do Connector. | NS16.01 |
| N12.2 | Rodar suíte unitária/contrato/migração e gate local com Core real; registrar versões dos harnesses e capacidades testadas por SO. | NS16.02, NS16.03 |
| N12.3 | Validar Server central sem binários/providers/dirs, preparando artefato para campanha remota; falhas locais do provider não impedem serving de modo remoto. | NS04.01, NS16.04 |
| N12.4 | Publicar documentação de API/CLI/UX e matriz de compatibilidade, sem comandos fictícios marcados como já existentes antes da implementação. | NS15.05, NS13.04 |
| N12.5 | Entregar build imutável de integração, SHA e hash para C11/N13; preparar release/rollback sem publicar automaticamente. | NS16.01, NS16.05 |
| N13.1 | Montar Nexus A sem runtimes e hosts B/C com Connector/Core, ao menos uma combinação heterogênea; incluir cenário Nexus local separado. | NS16.04 |
| N13.2 | Executar J01–J34 com SHAs e wheels reais; fakes não contam nos casos explicitamente multi-host/provider/SO. | NS16.04 |
| N13.3 | Validar first-use/second-use, chave MCP reutilizada, mesma identidade, múltiplos bindings e ausência de usuário Nexus em todas as superfícies. | NS13.02, NS16.04 |
| N13.4 | Injetar partições/restart/revogação/ACK perdido e provar não duplicação, cleanup e governança; registrar limitações por capacidade real. | NS14.05, NS16.04 |
| N13.5 | Consolidar matriz conjunta idêntica à do Connector/Core, blockers e release checklist; concluir somente gates demonstrados sem merge/publicação implícitos. | NS16.05 |

## Alterações normativas em relação ao texto R3

1. API pública real do Core substitui as assinaturas apenas ilustrativas de R3; instalação e availability v2 estão identificadas.
2. Novo /v1 direto é distinto do /api/v1 legado.
3. Server é o único admitter/dispatcher de efeitos; resolve não executa e receipt tem rota própria.
4. Catálogo/availability/snapshot são do executor escolhido; binding leva ref+revisão, não enum/local path central.
5. NXL R4 coordenado adiciona confirmações/correlação e payloads fechados; r3 histórico permanece imutável.
6. Decisão canônica gera a operação de aplicação; CLI não aplica nativo em paralelo.
7. DRAINING_PENDING conserva supervisor até prova ou transferência qualificada.
8. Core .10 e Connector .4 são baselines, não declaração de G2/E2.

## Correções acumuladas que viraram critérios permanentes

CN1/CN2: namespace completo, autenticação de todos os frames, idempotência HTTP, controle sob carga, scopes nos ACKs e história sem binário. CN3: gerações/revisões, quota exata, duplicate ACK e config por ownership. CN4: decisão Server antes de Core, candidato inteiro, revisão completa e rotação de lane. CN5: hash operacional não redigido, SessionKey até a aprovação, produtor separado do waiter, reattach após cancelamento e publicador retomado sem evento novo. Cada grupo aparece em NS08–NS14 e na matriz TR4. Não foram executados novamente nesta elaboração.

---

<a id="documento-08"></a>

**Documento-fonte: `08_FONTES_BASELINE_E_DECISOES.md`**

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
