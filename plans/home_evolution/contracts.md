# HOME-R1 — contrato de projeção v1

Estado: congelado para PR-01/02; alterações incompatíveis exigem registro neste
documento e no ledger. DTOs Python/TypeScript devem refletir o mesmo contrato;
não usar `any` para preencher referências ou estados não definidos.

## Leitura e autorização

`HomeOverviewService` recebe o RequestContext canônico e abre um UoW
`write=False`. Autentica o operador pelo acesso existente, fixa `now` uma vez e
compõe queries batch no mesmo SQLite. Não há HTTP interno, filesystem de
artefatos, journal integral, host remoto ou provedor durante o GET.

Rotas sob o envelope atual `/api/v1`, `Cache-Control: no-store`:

- `GET /home/overview?workspace_id=&agent_id=&state=&limit_work=10&limit_attention=3&limit_results=6&limit_agents=6`.
- `GET /home/work?...&cursor=&limit=` e `GET /home/results?...&cursor=&limit=`.
- `GET /home/activity?...&cursor=&limit=` para o feed de eventos de negócio.
- Resolver GET de alvo tipado/serializado, sem comando, para revalidar referência
  exata e workspace antes de compor os componentes canônicos de detalhe.

`workspace_id` omitido significa Todos; o frontend não envia o sentinela `all`.
Filtros são validados e aplicados antes de contar/agrupar/paginar. Não aceitar
parâmetros duplicados, cursores de outro escopo ou referências incompatíveis.
O mesmo operador autorizado pode ler Todos, sem duplicação por join.

401/403 removem dados protegidos do cliente. Falha transitória pode manter só o
último snapshot da mesma origem/identidade/workspace, rotulado stale. Um bloco
indisponível usa status/reason_code e total null; não vira sucesso vazio.

## DTOs compartilhados

`HomeOverview`: `version:1`, `scope:{workspace_id:string|null,agent_id?:string,
state?:string}`, `server_id`, `generated_at`, `snapshot_id`, `event_cursor`,
`event_low_watermark`, `summary`, `work`, `attention`, `results`, `agents`,
`external_activity`. Feed pode ser paginado separadamente.

`HomeSection<T>`: `status:ready|partial|unavailable|disabled|forbidden`,
`as_of:string|null`, `next_refresh_at:string|null`, `items:T[]`, `total:number|null`,
`total_is_exact:boolean`, `has_more:boolean`, `next_cursor:string|null`,
`reason_code?:string`, `revision?:string`. O cursor e snapshot_id são diagnóstico,
não autorização. Cursores são opacos, versionados e vinculados a todos os filtros,
ordem e revisão estrutural, com desempate imutável; mudança incompatível retorna
conflito explícito para reiniciar paginação. Nenhuma transação fica aberta entre
cliques e não existe banco de snapshots Home.

`HomeActivity`: `id`, `kind:handoff|conversation_turn|direct_operation`,
`source_ref:{type,id,revision}`, `workspace_id`, `title`,
`title_origin:canonical_title|message_subject|fallback`, `agent_ids:string[]`,
`display_state`, `state_since:string|null`, `last_activity_at:string|null`,
`evidence_status:confirmed|unknown`, `attention_refs:string[]`,
`runtime_refs:Array<{executor_id,session_id,operation_id?}>`, `detail_target`.
Podem ser acrescentados `reason`, `parent_target`, `attempt_count` e rótulos de
projeto/host/harness quando provenientes de metadados autorizados.

`HomeTarget` é uma união discriminada para handoff, execution, message, approval,
result e external_observation. Sempre contém `server_id`, workspace canônico
quando houver e os IDs exatos necessários ao handler. Execution/result inclui
executor, sessão e operação; externo inclui fonte, instância e geração. O resolver
usa uma allowlist de handlers, nunca uma URL de ação arbitrária. A serialização
é JSON canônico/estrutura opaca sem concatenação ambígua; URL não inclui conteúdo,
paths, tokens ou rascunhos. Falta de alvo vira indisponível, nunca “mais recente”.

`HomeResult`: identidade estável, source_ref, workspace/autor, título e preview
limitados, timestamps, outcome canônico, estado de verificação/cleanup separado,
refs de artefato autorizadas, `view_state:unseen|seen|not_tracked`, atenção/revisão
quando rastreável e detail_target exato. Resposta/artefatos só são agrupados por
vínculo durável; preview indica truncamento e não inclui transcript/ferramentas.

Campos v1 de resultado: `id`, `source_ref`, `workspace_id`, `agent_id:string|null`,
`title`, `preview:string|null`, `truncated:boolean`, `outcome:string`,
`verification_state:string|null`, `cleanup_state:string|null`,
`created_at:string|null`, `detail_target`,
`artifacts:Array<{artifact_id:string,filename?:string,media_type?:string}>`,
`view_state` e `attention:AttentionOccurrence|null`. O último campo fornece a
ocorrência rastreável/CAS para ação explícita sem buscar uma página oculta.

`HomeAgent`: identidade/rótulo, workspaces conhecidos, presença/conectividade e
capacidades informadas como dimensões distintas. Sem evidência de atividade:
“atividade não informada”, não ready/idle/autorizado. Workspace filtrado inclui
somente vínculo ou atividade autorizada comprovados, não todo nó global.

`attention.items` reutiliza `AttentionOccurrence` sem perder IDs, revisões,
destinatário, allowed_actions, freshness ou seen_state. Incidentes globais do
Server ficam identificados separadamente dos números do projeto.

`external_activity.items` reutiliza `ExternalObservation` ou projeção limitada
equivalente, com fonte/instância/geração/validade. Nenhum sinal externo conta como
execução ou conclusão canônica; fonte sem workspace não entra por inferência.

## Identidade, agrupamento e apresentação

1. Handoff é pai quando houver binding persistido, por claim_epoch atual.
2. Sem handoff, entrega lógica produtiva é pai de suas operações/tentativas.
3. Sem ambos, operação produtiva direta tem identidade Server/executor/operação.
4. runtime.start isolado, warm pool, controles e manutenção não são trabalho novo.
5. Handoff filho delegado continua separado; mensagem informativa/broadcast não
   vira trabalho por estar unread. Não colapsar DAG por agente/título/PID.
6. Mesmo agente com várias sessões mantém atividades distintas. Externo nunca
   se funde a nativo por semelhança de identificador.

| Fato atual comprovado | display_state | Contador de execução |
|---|---|---|
| OPEN sem dependência | awaiting_owner | Não |
| CLAIMED sem execução confirmada | claimed | Não |
| Fila/entrega aceita, ainda sem início | queued | Não |
| Recibo native accepted/SUBMITTED | native_accepted | Não |
| Evidência corrente confirma execução iniciada, sem terminal da mesma tentativa | running | Sim, uma atividade lógica |
| Dependência pendente | awaiting_dependency | Não |
| Pergunta ao operador | awaiting_operator | Fato produtivo separado da pendência |
| Pergunta a outro agente | awaiting_agent | Não personificar destinatário |
| VERIFYING | awaiting_verification | Não concluir entrega |
| Resultado/recibo inconclusivo | outcome_unknown | Não presumir falha sem efeitos |
| COMPLETED do handoff atual | completed | Não |
| Turno SUCCEEDED, handoff ainda aberto | turn_completed | Não concluir handoff |
| Resultado SUCCEEDED com cleanup pendente | result_available_cleanup_pending | Não repetir resultado |

`state_since` só usa transição conhecida; não renomear created_at como tempo no
estado. Quando a fonte não confirma início, preservar recebido/desconhecido.
Estados simultâneos têm contagens/refs internas, não overwrite por badge único.

## Contadores

- `running`: número distinto de atividades com execução corrente confirmada.
- `waiting_start`: fila, responsável ou despacho; dependência e resposta são
  filtros próprios. Não somar inbox unread/sessões abertas.
- `needs_you`: ocorrências Attention acionáveis pelo operador, com adiamento e
  prioridade atuais; várias ocorrências podem pertencer à mesma atividade.
- Resultados rastreados usam `result_unseen`/revisão. Onde o conjunto não sustenta
  número exato de novos, usar null/not_tracked e rótulo Recent results.

O DTO de cada contador inclui valor nullable, exatidão e motivo/unidade. As quatro
unidades não se somam como total de tarefas. Contagem externa é separada.

`HomeSummary` tem chaves `running`, `waiting_start`, `needs_you`, `results` e
`external`, cada uma `HomeCounter:{value:number|null,total_is_exact:boolean,
label:string,unit:activities|occurrences|results|external_instances,
reason_code?:string}`. O label de results distingue New results de Recent results;
sem rastreamento integral, `value=null` para novos, não um zero inferido.

## Ações, atualização e fallback

Detalhes reutilizam inspeções existentes. Aprovar/responder/verificar/interromper
usam os endpoints atuais, revisão fresca e intenção idempotente persistida antes
do envio; erro de resposta não libera retry. Novo pedido distingue handoff e
mensagem. Continuação resolve a sessão exata pelo runtime canônico; sessão
encerrada/revogada exige novo contexto explícito.

Preferências seguem o ADR compartilhado; nenhuma nova fila, ACK ou watermark.
Cache/requests têm geração por origem/identidade/escopo. A apresentação mantém
rascunho, foco, scroll e item editado; troca/logout revalidam/descartam conforme
guard canônico. Pausa visual não muda autoridade nem para agentes.

Reutilizar os streams existentes no shell, com invalidação por bloco, debounce
300–500ms e teto de uma releitura consolidada/s, uma requisição em voo e uma
invalidação pendente. Reconnect/gap/retomada provocam snapshot fresco; polling de
15s e next_refresh_at cobrem fatos sem evento. Background reduz trabalho.
Cada bloco conserva sua atualidade; stream live não torna fonte stale current.

Um controle independente de apresentação preserva a Home anterior como fallback.
Desabilitá-lo não altera runtime, Attention, observação, grants ou daemon. O
contrato permite equivalente tipado de nomenclatura, com registro de desvio;
não permite diminuir os 36 itens ou 73 cenários por conveniência.
