# UI-R1 — mapa estático das fontes e destinos (UI-002)

Inspeção em 16/11/2026, Nexus `feature/v0.3.4`, HEAD
`856c7f459d16719aa7dfa54c3dc64c85199cf563` (também origin/feature/v0.3.4).
O snapshot do plano é `3d95aad8`; o HEAD contém os commits posteriores de
evidências HOME-R1. Antes destas edições, `git status --short` apontava somente
`?? NEXUS_UI_R1/`. Nenhum rollback ao snapshot foi feito.

Após a inspeção, o root registrou o bump na branch de entrega
`feature/v0.3.5`/`9de55d95` e Connector `feature/v0.0.13`/`414e3e7`; Core
permanece0.0.14. Este mapa preserva o SHA da leitura de produto e aponta para
`baseline.json` para os SHAs completos da reconciliação atual.

Leitura prévia: `CONTRIBUTING.md`, `.github/workflows/ci.yml`, plano UI-R1
§§2–7, tarefas UI-002/UI-003 e seus aceites no ledger entregue, e
`plans/home_evolution/source-map.md`. CI atual constrói frontend e wheel/sdist,
executa contratos frontend e regressão instalada em Linux/Windows, Python
3.11–3.13, quatro shards. Esta etapa documental não executa essa campanha nem
reconstrói os assets gerados.

## Destinos completos e dependências dos nomes

Os 19 IDs abaixo são os valores atuais de `VIEWS`/`View` em
`frontend/src/App.tsx:100`. Trocar o texto apresentado não troca esses IDs.
Hoje o shell usa estado React para a view, não uma rota pública por rótulo.

| ID interno preservado | Destino UI-R1 / rótulo público em inglês | Acesso básico preservado |
|---|---|---|
| Home | Principal / Home | Pedido, conexão e acompanhamento; mesma Home |
| Meta-harness | Principal / Conversations | Conversa e delegação; não confundir com Messages |
| Graph | Principal / Graph | Grafo e aberturas contextuais |
| Artifacts | Principal / Artifacts | Catálogo e referências de entregas |
| Attention | Painel global sob demanda / Needs attention | Sino em todas as views e filtro da Home, inclusive fallback clássico |
| Agents | Advanced → Agents and execution / Agent administration | Conectar agente permanece ação básica |
| Runtimes | Advanced → Agents and execution / Runtime administration | Sessão/trabalho no painel básico; diagnóstico aqui |
| Registry | Advanced → Agents and execution / Tags and capabilities | Não impor cadastro técnico no onboarding padrão |
| Communication | Advanced → Agents and execution / Communication styles | Não é Conversations nem Messages |
| Policies | Advanced → Policies and control / Policies | Decisões correntes no básico |
| Guardrails | Advanced → Policies and control / Guardrails | Motivo da recusa no trabalho |
| Approvals | Advanced → Policies and control / Approval history | Aprovar/negar corrente pelo controle canônico básico |
| Messages | Advanced → History and diagnostics / Message history | Abrir mensagem exata por contexto |
| Handoffs | Advanced → History and diagnostics / Work delegations | Criar/acompanhar no básico; Kanban existente preservado |
| Events | Advanced → History and diagnostics / Events | Timeline resumida no painel |
| Execution log | Advanced → History and diagnostics / Execution records | Motivo resumido no básico |
| Workspaces | Advanced → History and diagnostics / Project health | Seleção global de projeto permanece |
| Memory | Advanced → System and data / Shared memory | Preservar `memoryEnabled`, não ativar feature por exibição |
| Settings | Advanced → System and data / System settings | Preferências/ajuda/conta e logout globais; atalho ao formulário existente |

`Advanced` será um novo ID de índice de navegação, não um domínio novo ou uma
permissão. Seus quatro grupos não adicionam menus Harnesses/Sessions/Executions.
As capabilities existentes continuam nas páginas originais.

Dependências explícitas encontradas no shell:

- `setView` centraliza o guard de saída; `mayLeavePanel` protege troca de alvo,
  workspace e toggle da Home. Não contornar esses callbacks por links novos.
- `operatorUnread.ts` contém `OPERATOR_VIEWS = ["Messages", "Meta-harness"]`:
  comparadores de visibilidade, marker de mensagens, toast e notificação devem
  continuar usando IDs. Abrir Home não pode marcar mensagens globalmente.
- `view === 'Attention'` controla visibilidade do controller; `view === Graph`
  controla leituras do grafo; `Meta-harness` controla polling e notificações.
  `memoryEnabled` remove Memory e redireciona para Graph se necessário.
- Callbacks atuais: toast → Meta-harness; execução → Events; configuração de
  acesso → Settings; onboarding → Agents; Runtimes → Approvals; composer →
  Meta-harness. A nova organização preserva cada destino e guard.
- Preferências: `okto-nexus-sidebar`, `okto-nexus-workspace`,
  `okto-nexus-home-operational`, `okto-nexus-operator-seen` e
  `okto-nexus-operator-notify` não recebem renomeação por rótulo.
- `OperationalHome.tsx` preserva `home_target` no query string com
  `pushState`/`replaceState`, `popstate` e guard; IDs no JSON são opacos.
  Não inventar path baseado no nome público da view.

## Matriz origem → escopo → autorização → correlação → evento/fallback

Paths abreviados nesta tabela partem de `src/okto_nexus/`.

| Origem / arquivos atuais | Escopo e autorização efetivos | Correlação e cobertura | Atualidade / evento / fallback |
|---|---|---|---|
| `application/home.py`, `domain/home.py`, `adapters/inbound/http/home.py` | `HomeOverviewService._authorize`: operador autenticado via `access.authenticate(...require_feature=False)`; workspace deve existir; Server vem de `execution_installation`. HTTP rejeita parâmetro desconhecido/repetido, usa `no-store`. Operador autorizado não significa que agente pode usar a mesma rota. | Uma UoW read-only e relógio comum; target é revalidado contra Server/workspace real. Nenhum GET inicia sessão, probe, claim ou provedor. | `generated_at`, `as_of`, `next_refresh_at`, snapshot/revision e limites por seção; falha independente é unavailable/partial, não vazio confirmado. |
| Handoffs/tasks; `adapters/outbound/sqlite/home.py:FACTS`, `domain/home.py:activity`, `application/handoff_runtime_views.py` | Workspace é filtrado antes da projeção/página; agente vale para remetente OU destinatário/subject relacionado. Não restringir a pedidos do operador. | Handoff é pai; claim_epoch vincula tentativas ao dono correto. Handoff filho é outra atividade, com relação ao pai; fila sem executor é trabalho legítimo, sem sessão fabricada. | Eventos handoff/receipt invalidam; lease/deadline e receipts sem evento geral exigem fallback por tempo. |
| `delivery_outbox`, messages, `execution_domain_deliveries`, `execution_delivery_attempt_history`; mesma FACTS | Vínculo persistido e workspace da entrega; não inferir por assunto ou nome de harness. | Entrega lógica é pai sem handoff; abertura/submit/retry não multiplicam tarefas. A→B aparece mesmo sem operador autor. | Eventos mensagem/dispatch/receipt mais snapshot/reconnect/fallback. |
| `execution_operations`, receipts, sessions, event_ingress/watermarks, results; mesma FACTS e `application/execution_results.py` | Server/executor/operação/sessão/owner_generation; continuidade e eventos aplicam autoridade canônica, não PID. | Operação direta só sem pai persistido. RUNNING exige evidência corrente/contígua de started/progress; accepted, claim e warm não bastam. SUCCEEDED não conclui handoff aberto; cleanup pendente mantém resultado. | Epoch/contiguous watermark/gaps e retenção preservados; não chamar host por linha. |
| Sessões; `application/execution_session_views.py`, `execution_event_views.py`, HTTP `runtime_v1.py`, `dashboard_runtime.py` | Read verifica operador OU actor/subject autorizado; session_id ambíguo exige executor. Scope real inclui Server/executor/binding/agente/workspace/workspace_binding/session/owner_generation e revisões. Eventos reusam essa leitura. | Há leitura canônica sem turn produtivo: `runtime.open` é operação de abertura, não `turn.submit`. Inventário UI unificado ainda não existe. `list_execution_sessions` é por executor/binding/agente e cursor, não diretório global. | Lifecycle/lease/control_available são separados; process_state/ownership UNKNOWN não comprovam saída. Eventos usam stream_epoch/sequence/committed_contiguous e payload público redigido. |
| `application/meta_harness_sessions.py:conversation_sessions` | Operador; SQL contém `m.from_agent_id='operator'`, mais filtros workspace/agente. | Diretório de conversas do operador, NÃO inventário de todas as execuções. Exclui sessão sem interação do operador. Não reutilizar como fonte exclusiva da nova Home. `agent_session_summary` tem corte100+has_more, também não inventário completo. | Página20 de conversas e informações observadas; preservar consumidores atuais, ampliar projeção separadamente. |
| Bindings/executors/agent_endpoints; `execution_session_views.py`, `application/execution_runtime_options.py`, `connection_setup.py`, `execution_operator_authority.py` | Binding persistido, workspace_binding e revisões/grants; leitura não emite autorização de execução. | Grupo usa contexto de conexão+agente+workspace+executor/host/harness quando conhecido. Conexão configurada não comprova sessão pronta/login. Inventário de conexões sem sessão precisa nova query autorizada. | Config/revisões/credential_epoch/inventory têm atualidade própria; leitura não faz refresh remoto implícito. |
| Attention; `application/attention.py`, `adapters/outbound/sqlite/attention.py`, `attention_native.py`, `attention_results.py`, HTTP `attention.py`/`attention_stream.py` | Operador, feature e preferências canônicas. Pergunta humana exige destinatário/autoridade/revisão/prazo; não personificar outro agente. | `attention_id` + source_revision + preference_revision. Referências enriquecem o pai; órfã permanece ocorrência com proveniência. Seen/snooze via CAS; visto não é ACK, aprovação ou aceite de entrega. | Stream próprio já canônico com reset/low watermark; next_change_at e fallback para prazo/adiamento; revalidar antes do efeito. |
| Partições Home Attention; `application/home.py`, `sqlite/home.py`, source-map HOME-R1 emendaA08 | Hint só workspace para famílias `WORKSPACE_BOUND`; preserva evidência do destinatário mesmo em filtro do remetente. Server global independente de filtro projeto/agente/state. | `/home/attention` exclui globals; `/home/server-attention` só globals autorizados, fora de Needs you/contadores projeto. Seis famílias atuais não são produtor global real; prova global foi porta de domínio válida, não NULL DB inválido. | Cursores Home vinculam seção/escopo/Server/revisão; nunca enviar cursor Home à API Attention clássica. Sem incidente, UI-R1 propõe aviso ausente. |
| Resultados/artefatos; `sqlite/home.py:RESULTS`, `application/execution_results.py`, `attention_results.py`, APIs atuais | Mesma origem autorizada e revisão/claim/terminal_sequence. Preview limitado/redigido; conteúdo completo e download sob demanda. | Results/artefatos só enriquecem trabalho mediante referência comprovada. `result_unseen` é episódio canônico compartilhado; not_tracked não vira contador exato. | Novo episódio pode reaparecer. Retenção indisponível não reconstrói conteúdo por logs. |
| Observações externas; `application/observations.py`, `sqlite/observations_repo.py` | Fonte/instância/generation, associação persistida e workspace confiável. Agent_id/nome/PID/host isolado não autoriza união ao nativo. | Reported/inferred separado de confirmed nativo; sem vínculo confiável não entra no projeto por inferência. | observed_at/expiry; stale/off/disabled/parcial explícitos. Ausência não bloqueia restante da Home. |
| Shell e atualização; `App.tsx`, `hooks/useSSE.ts`, `hooks/useAttention.ts`, `hooks/useHomeOverview.ts`, `homeController.ts` | Cache por origin/identity/workspace/filter; geração/AbortController impedem resposta antiga cruzada;401/403/logout limpam protegido. | Home recebe invalidações do SSE do shell; não criar stream por grupo/linha. Attention conserva controller/stream canônicos. | Burst/coalescing,1inflight, pausa/aplicar, reconexão/gap/retorno da aba e fallback15s; reconectar não prova frescor de dados. |

## Reuso do painel, ações e fronteiras

`components/home/HomeInspection.tsx` revalida alvo e delega a
`CanonicalInspection` de `AttentionInspection.tsx`; novo pedido reusa
`MetaHarnessComposer`; continuidade usa `RuntimeOperations` e
`components/home/continuation.ts` com scope exato. `AgentActionModal` mantém
guard/foco; não substituir por handlers de comando novos.

`SessionTerminalModal.tsx` já compara scope de sessão em polling e oferece
`RuntimeSessionTail`/`RuntimeHistory`. `RuntimeTerminal.tsx` apresenta eventos e
possui maximização por dialog. Extrair corpo embutível preservando wrappers,
scrollback e cancelamento; na nova Home deve haver uma única camada/foco, sem
modal dentro de drawer. Transcript só do painel visível, leitura apenas.

Server é autoridade de identidade, política, despacho e persistência. Core é
executor; Connector é host remoto com armazenamento/checkpoints próprios e
daemon. O plano fixa Connector `a8bd48bd…` como referência, não como auditoria
deste checkout. UI-004 deve reconciliar seu HEAD e contratos de seleção antes
de alegar compatibilidade remota. Uma UI HTTP não pode instalar serviço ou
transportar chave administrativa ao host por conveniência. Connect/work e
setup transacional continuam caminhos canônicos, dashboard opcional.

## Lacunas e gates herdados

No HEAD não há `HomeEntryGroup`/`entries`, cursor de filhos ou alvo autônomo
`session`; `HomeTarget.execution/result` exige operation_id. Home ainda mostra
listas paralelas, sidebar tem19destinos e não há sino Attention global completo
independente do projeto. Estes são deltas UI-R1, não regressões já corrigidas.

HOME-R1 preserva31VERIFIED/2IMPLEMENTED/2IN_PROGRESS/1TODO e71PASS/2NOT_RUN no
seu próprio corte. H02 fala real de leitor de tela, I01 continuidade de coorte
real, HOME033 nova campanha consentida e avaliação humana10s permanecem
pendentes; HOME030/032/034/036 são condicionadas. Default ainda classic e M3
não aprovado. p95 HTTP local quatro datasets passou, mas service read grande
673.91ms permaneceu acima da meta; não é SLO de produção nem evidência de
desempenho da projeção nova. Mobile pr13 tem aceite literal de layout, probe
adicional de paginação incompleto; não converter em PASS novo.

## Estado proposto

UI-002: mapa documental implementado para revisão; T-BASE-03 pode ser avaliado
como contrato estático contra a tabela e callbacks acima. T-SCOPE-01 continua
NOT_RUN para a nova projeção: inspeção e evidência HOME-R1 não substituem seu
novo teste HTTP/SQLite. Não alterar status do ledger automaticamente. Nenhum
teste de produto/browser/campanha foi executado nesta tarefa.
