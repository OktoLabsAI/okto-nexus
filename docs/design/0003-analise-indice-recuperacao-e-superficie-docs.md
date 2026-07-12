---
title: "Análise 0003 — Índice de recuperação de mensagens & auditoria da superfície de instruções/resources"
status: "Parte 2 CORRIGIDA em 2026-07-12 (itens 1-4 do plano, SURFACE_REVISION 31; item 5 — redesign do aspecto 1 — aguarda spec)"
date: 2026-07-12
related: ADR 0001 (message inbox delivery), Frente 1 (token reduction), specs 80624c1a / 2948b2a2
---

> **Status das correções (2026-07-12).** Os itens 1-4 do plano de correção foram aplicados
> (SURFACE_REVISION 30→31; resources bumpados: preflight v3, communication v2, monitoring v5,
> target-grammar v5, tool-docs/{messages,inbox,events,artifacts} v2, tool-docs/identity v4,
> governance v2, hitl v2; gate de 40% sem desconto fantasma via `EXPERIMENTAL_GROWTH_KEYS`;
> lease default agora INTERPOLADO de config no resource). Superfície residente: cuttable
> 27.788→26.275 chars (−379 tokens proxy/turno); params 17.512→15.720 (voltou abaixo do
> baseline pré-Frente-1 de 16.406); redução honesta do gate: 44,27% (folga 1.777 chars).
> Suíte completa: 1577 passed. O item 5 (inbox_wait/ack-implícito/EPT cursor — Parte 1)
> permanece como recomendação aguardando spec.

# Análise 0003 — Índice de recuperação & superfície de docs

## Método

Análise multi-agente adversarial (workflow `wf_2f982d83-24a`, 37 agentes, ~2,59M tokens):

- **Aspecto 1**: 1 arquiteto mapeou o estado que o cliente é forçado a carregar e propôs 5 opções de
  redesign; 1 crítico independente montou o *steelman* do design atual e julgou cada opção
  (sobrevive / sobrevive-com-ajustes / morre) lendo ADR 0001 + código.
- **Aspecto 2**: 3 auditores paralelos (inline-vs-código, tool-docs-vs-código, orçamento de tokens),
  cada achado submetido a um verificador **cético** independente instruído a refutar abrindo os
  arquivos (em dúvida, refutar).

Resultado da verificação: **32 achados brutos, 0 refutados**. Vereditos: `CONFIRMADO` (claim exata),
`PARCIAL` (verdadeiro mas impreciso — a correção está registrada no achado), `NÃO-VERIFICADO`
(6 achados cujo verificador caiu por limite de sessão — plausíveis, mas sem segunda checagem;
tratar como hipótese até conferir a evidência citada).

Todas as referências `file:line` são relativas a `src/okto_nexus/` salvo indicação contrária, na
árvore de 2026-07-12.

---

# Parte 1 — "O agente é forçado a conhecer o índice de recuperação de mensagens"

## Tese avaliada

> "O agente é forçado a conhecer o índice de recuperação de mensagens. Ele deveria ter apenas uma
> lista de mensagens não vistas/não lidas e mensagens já consumidas."

## Veredito

**A tese é parcialmente correta — e a parte correta não está onde ela aponta.**

**Onde a tese NÃO se aplica — o inbox em si.** O ADR 0001 foi escrito exatamente para matar o
índice do V1 ("Index-based retrieval is fragile", `docs/design/0001-message-inbox-delivery.md:31-37`)
e o modelo entregue cumpre: `inbox_pull` não tem cursor ("Index-free: the server tracks per-recipient
read state", `application/inbox.py:123-124`), e as "duas listas" pedidas **já existem no servidor**
como projeções read-only: `inbox_count` retorna `{unread, in_flight, read}` (`inbox.py:293-310`),
`inbox_peek` lista as não-consumidas e `inbox_history` lista as consumidas. O servidor rastreia
lanes, attempts, lease e redelivery por destinatário (tabela `message_deliveries`, ADR 0001:129-146).

**Onde o fardo é REAL.** Não é um índice de *recuperação* de mensagens; é:

- **(a) o protocolo de transição entre as duas listas**: o cliente é forçado a carregar a lista de
  `message_ids` do lote puxado até o ack (`tools/inbox.py:59`) e a gerenciar um prazo de lease de
  300s dentro do turno (`config.py:24`), com `inbox_extend` all-or-nothing como ferramenta de
  correção (`inbox.py:197-235`). Para um LLM isso é contexto entre tool-calls e fonte de erro:
  ack esquecido → redelivery duplicada → após 5 tentativas, *parked* — que o `inbox_count` **nem
  mostra** (`inbox.py:72,299`);
- **(b) o plano de sinal**: o monitor canônico é o plano de eventos, que reintroduz exatamente o
  padrão cursor-por-leitor que o ADR 0001 condenou para mensagens — o pre-flight passo 4 manda
  ancorar com `event_cursor` e "Always advance the cursor" (`mcp/resources.py:149-155`), e o
  invariante I4 manda **persistir** o `next_cursor` entre restarts (`resources.py:281-284`).
  A defesa do design é o I2 ("a dropped event never loses a message… re-anchor at now and let
  inbox_count sweep the backlog"): o cursor de eventos é descartável PORQUE o inbox é durável.

Somando: o sistema já é index-free no plano de **entrega**, mas cobra do agente um cursor no plano
de **observação**, ids+prazo no plano de **consumo**, um segundo cursor+token com lifecycle no EPT,
e credenciais de sessão em tudo — **5 peças de estado inter-turnos** para o fluxo completo de
recepção. A tese acerta no diagnóstico do fardo, erra ao localizá-lo na "recuperação".

## Inventário do estado que o cliente é forçado a carregar

| # | Estado | Onde | Por que é forçado | Evidência |
|---|--------|------|-------------------|-----------|
| 1 | Lista de `message_ids` do lote puxado (retida do `inbox_pull` até o `inbox_ack`) | Consumo pull → processa → ack | O ack é endereçado por message_id escolhido pelo cliente; não existe "ack do último lote". Perdeu os ids no meio do turno → redelivery e reprocessamento | `tools/inbox.py:59,166-181`; `application/inbox.py:160-192` |
| 2 | Prazo do lease (`lease_expires_at`, default 300s) e a decisão de `inbox_extend` dentro do turno | Turnos longos entre pull e ack | Turno de LLM rotineiramente estoura 300s; lease vencido → extend falha all-or-nothing (INVALID_TRANSITION, "pull it again") — um deadline de relógio de parede vigiado enquanto raciocina | `config.py:24`; `application/inbox.py:65-72,197-235,590-611` |
| 3 | Semântica das lanes: lease expirado "conta como unread"; 5 claims → *parked* invisível no count | Triage com `inbox_count`/`inbox_peek` | Para não duplicar trabalho o agente precisa saber que unread inclui redeliveries suas, que attempts crescem a cada pull, e que parked só aparece com `peek(include_parked=true)` | `application/inbox.py:72,253-256,296-300`; ADR 0001:78-93 |
| 4 | Cursor do plano de eventos: âncora (`event_cursor`) + `next_cursor` avançado e **persistido entre restarts** (I4) | Monitor canônico (event_wait/event_get) | O servidor não guarda posição de leitura por agente no log — exatamente o padrão leitor-com-índice que o ADR 0001 aboliu para mensagens, mantido para o wake. Mitigado por I2 | `resources.py:149-155,281-284,267-272`; `application/events.py:519-589` |
| 5 | EPT: token bruto `nxsept_` (retornado UMA vez), base_url, um SEGUNDO cursor via REST, `expires_at` para renovar, revoke no teardown | Monitor remoto EPT | O processo faz sua própria gestão de cursor REST; o harness gerencia o lifecycle do token. O token já carrega `issue_cursor` server-side (clamp na emissão) — meio mecanismo de cursor server-side já existe | `resources.py:344-376`; `application/poll_tokens.py:77-165,223-248`; `http/routes.py:840-916` |
| 6 | Cursor opaco de paginação do `inbox_history` (`read_at~delivery_id`) | Navegação do histórico | Keyset padrão; fardo baixo e efêmero, mas é mais um cursor na superfície | `application/inbox.py:84,315-342,690-705` |
| 7 | `session_id` + `session_secret` (retornado SÓ no `session_open`) + disciplina de heartbeat (<60s stale; presença 1800s) | Verbos sensíveis + poll_token_* | O secret é retornado uma única vez e precisa sobreviver no contexto a sessão inteira; heartbeat é responsabilidade explícita (I3: leituras não avançam) | `application/identity.py:118-207,691,728,774`; `config.py:27,34,72-74` |

## Steelman do design atual (crítica adversarial)

O design atual não é acidente: cada peça cobre um modo de falha que o modelo "duas listas" não
consegue sequer **representar**.

1. **Todo estado do cliente é DESCARTÁVEL porque o inbox é durável.** Perdeu os message_ids? O
   lease expira e a mensagem volta (`claim_pending` cobre "unread + own lease-expired redeliveries").
   Perdeu o cursor? Re-ancora em now e `inbox_count` varre o backlog (I2). Perdeu o EPT? Reemite.
   A única peça de estado cliente que seria IRRECUPERÁVEL é "o que eu já processei" — e é
   exatamente essa que um auto-ack destrói.
2. **O lease é o detector de crash** de um consumidor (turno de LLM) que morre constantemente e sem
   aviso — sem supervisor, sem rebalance, sem shutdown hook. Sem lease, crash entre "peguei" e
   "terminei" força escolha binária: perda silenciosa ou re-entrega infinita de mensagem-veneno.
   O trio lease+attempts+parked dá recuperação, quarentena de veneno (parked após 5 claims,
   `messages_repo.py:442-446`) e um dead-letter nunca podado (`messages_repo.py:699`).
3. **delivered/read não é burocracia**: é o que torna `message_status` utilizável pelo sender para
   decidir entre reenviar e esperar ("pulled but died" ≠ "processou"), e os receipts são emitidos
   NA MESMA transação da transição de lane (`inbox.py:146-155`) — nunca mentem.
4. **O cursor de eventos ser client-side é coerente com SQLite-WAL-single-writer**: count/peek/
   history foram projetados para nunca tomarem o writer lock (`inbox.py:20-24`); posição server-side
   transformaria cada página servida em uma escrita por leitor.
5. O servidor **já oferece as duas listas** como projeções; o modelo atual é um superset: duas
   listas para olhar, mais o protocolo de transição para quem consome com garantias.

## Opções de design avaliadas

### A — Ack implícito no próximo pull (modo consumer) → **sobrevive-com-ajustes**

`inbox_pull` ganha um modo em que cada pull confirma automaticamente o lote in-flight anterior do
mesmo escopo — o padrão "commit no próximo poll". O agente nunca carrega message_ids; o loop vira
pull → processa → pull. Ack explícito continua disponível.

- **Prós**: elimina a peça de estado mais cara; preserva at-least-once (crash entre pulls →
  redelivery normal); o lease deixa de ser deadline vigiado e vira só timer de crash-recovery;
  padrão consolidado (Kafka auto-commit-on-poll).
- **Contras/ajustes obrigatórios (da crítica)**:
  - `message_deliveries` **não tem vínculo de sessão** (migração 005) — sem amarrar o lote ao
    `session_id`, duas sessões do mesmo agent_id se ackam mutuamente;
  - **o lote final nunca é ackado implicitamente**: todo fim de sessão deixa um batch in-flight que
    a próxima sessão reprocessa — duplicação SISTEMÁTICA por fronteira de sessão; e como attempts
    incrementa por claim, mensagem corretamente processada por 5 sessões consecutivas acaba
    **parked** (dead-letter de mensagem tratada). Exige **flush do in-flight no `session_close`**;
  - precisa de um verbo de devolução (nack/requeue) para mensagem deliberadamente não tratada;
  - `message.read` passa a significar "confirmado no pull seguinte" — o receipt atrasa um ciclo.
- **Custo de migração**: baixo-médio (1 parâmetro + coluna de sessão no repo de deliveries; ledger
  APPROVED_GROWTH + bump de SURFACE_REVISION; nada existente quebra).

### B — Pull com auto-ack (at-most-once opt-in) → **morre**

`inbox_pull(ack="auto")` flipa unread→read na mesma transação. É literalmente o modelo do dono,
zero estado — e morre por três razões independentes:

1. Reintroduz a classe de falha que o ADR 0001 existe para matar: **perda silenciosa**. O modo de
   morte mais comum do consumidor-LLM é "o tool call retornou mas o turno não completou"; com
   auto-ack a mensagem já está em read, nada sinaliza a perda, e a lane read é **podada após 14
   dias** (`config.py:87`) — janela de recuperação finita e invisível. O ADR usa "silently" duas
   vezes como motivação; B a reintroduz com flag.
2. Corrompe a observabilidade do sender: `read` deixa de implicar "processado"; `message_status`
   perde o significado e o sender não tem como saber em que modo o recipient puxou.
3. Seu caso de uso legítimo (receipts/FYI) é **totalmente absorvido pela opção A** com
   at-least-once. Sobra só o custo de um segundo modo de consumo na doc.

### C — Cursor de eventos rastreado no servidor por agente → **sobrevive-com-ajustes (forma reduzida)**

Proposta plena: `event_wait/event_get` sem cursor = "desde a última vez que você olhou", posição
persistida por (agent_id, stream). A crítica derrubou a forma plena:

- posição por agent_id quebra multi-leitor (a doc oficialmente suporta listener em background E
  snapshot simultâneos do mesmo agente — leitores roubariam eventos entre si);
- avançar posição server-side transforma cada página servida em ESCRITA, contra o design de
  leituras que nunca tomam o WAL writer lock (`inbox.py:20-24`);
- mudar o significado de "omitir cursor" (hoje = ler do início) é a classe de mudança que gerou os
  shims MIGRATED — o custo que o repo já demonstrou ser o mais caro;
- "metade do mecanismo já existe" é meia-verdade: o `issue_cursor` clampa só em `/events/cursor`;
  `GET /events` REJEITA cursor antigo com VALIDATION_ERROR (`poll_tokens.py:371-382`) — é cerca,
  não rastreador.

**Forma que sobrevive**: (a) persistir `last_served` **no row do token EPT apenas** — ali a escrita
por request JÁ existe (`touch_used`, `poll_tokens.py:204-219`), o escopo por token resolve
multi-leitor de graça, e o poller vira token+base_url; (b) no plano MCP, no máximo um
`since="last"` opt-in escopado por session_id — **nunca** mudança do default de cursor omitido.
Aceitar explicitamente na doc a semântica at-most-once do sinal (tolerável só porque I2 faz o
inbox ser a verdade).

### D — Monitor por inbox apenas: `inbox_wait` sem cursor → **sobrevive-com-ajustes (a opção mais forte)**

Novo verbo bloqueante `inbox_wait(agent_id, timeout_seconds)` (+ `GET /api/v1/inbox/wait` no EPT)
que parka até os counts mudarem, reusando o Waiter por `PRAGMA data_version` que o `event_wait` já
usa (`events.py:11-19`). O monitor canônico deixa de tocar o log de eventos: sem âncora, sem
cursor, sem I4. `event_*` permanece como observabilidade.

- **Prós**: monitor 100% stateless (o loop inteiro é agent_id+timeout); alinha o design com o
  próprio I2 do sistema ("the inbox DECIDES" — hoje o monitor observa o plano errado e confirma no
  certo); infra pronta (count read-only barato; precedente `handoffs_pending` no EPT); reduz o
  REFERENCE MONITOR de ~40 linhas para ~8.
- **Bug de design achado pela crítica — AUTO-DESPERTAR POR LEASE PRÓPRIO**: `inbox_count` conta
  in-flight com lease vencido como unread (`inbox.py:296-300`); um `inbox_wait` armado enquanto o
  agente processa um batch puxado ACORDA aos 300s com o unread do PRÓPRIO batch — wake espúrio
  sistemático em todo turno longo, indistinguível de mensagem nova num predicado level-triggered
  "unread>0". **Ajuste obrigatório**: semântica de **DELTA** (o wait retorna um change-token e
  desperta em MUDANÇA de counts desde o token, reportando as lanes).
- Demais ajustes: declarar a dependência do wake-do-sender no knob `inbox_read_receipts` (default
  ON mas opt-out — com o knob OFF, "espere lerem minha mensagem" via inbox morre e volta a exigir
  event_wait); `handoffs_pending` NÃO é um COUNT barato (lista handoffs abertos e avalia
  elegibilidade por scan, `poll_tokens.py:315-353`) — precisa de projeção mais barata antes de
  entrar num long-poll re-escaneado por data_version; honestidade no claim: event_wait com cursor
  continua existindo para filtros finos — o fardo vira opcional, não eliminado.

### E — Unificação peek/pull em `inbox_list` + `inbox_consume` → **morre**

O próprio repositório fornece a prova do custo: os shims MIGRATED de message_get/list/wait
(`tools/messages.py:297-357`) ocupam superfície residente PARA SEMPRE só para dar erro prescritivo
a clientes pinados — quebrar 6 tools consolidadas criaria seis novos desses. Tecnicamente:
"o lease continua existindo, invisível" é a pior combinação — a redelivery REAPARECE mas o agente
perde o vocabulário (lease_expires_at, extend, attempts) para entender ("mensagem duplicada
misteriosa"); um consume auto-ack colapsa delivered/read e herda toda a crítica de B; parked fica
sem casa. O ganho de simplicidade é obtível por A+D aditivamente — peek/count/history **já são**
as duas listas do dono.

## Recomendação final (pós-crítica)

Manter o modelo at-least-once com lanes+lease+parked como **default inegociável**, e atacar o
fardo de estado em três movimentos **aditivos**, nesta ordem:

1. **D ajustado** — `inbox_wait(agent_id, timeout)` como monitor canônico, com semântica de DELTA
   (change-token + lanes no retorno) em vez de "unread>0"; documentar a dependência do
   wake-do-sender no knob `inbox_read_receipts`; dar a `handoffs_pending` uma projeção barata.
   Deleta o I4 do caminho canônico e o grosso da prosa de monitoring.
2. **A ajustado** — ack-no-próximo-pull **opt-in por chamada**, com lote amarrado ao `session_id`
   (coluna nova em `message_deliveries`) E flush do in-flight no `session_close`; adicionar
   nack/requeue; documentar que `message.read` atrasa um ciclo.
3. **C reduzido ao plano EPT** — `last_served` no row do token; cursor opcional só nos endpoints
   EPT; no MCP, no máximo `since="last"` opt-in por sessão, jamais mudando o default.

**Rejeitar** B (at-most-once reintroduz a perda silenciosa; caso de uso absorvido por A) e E
(quebra 6 tools, colapsa delivered/read, esconde sem eliminar o lease).

**Complemento barato e ortogonal**: expor `parked` no retorno de `inbox_count` (hoje invisível,
`inbox.py:299`) — remove um fardo conceitual real por +1 campo, sem redesign.

Cada item novo entra no ledger APPROVED_GROWTH com bump de SURFACE_REVISION; o saldo de tokens é
positivo porque D deleta mais prosa da resource monitoring (I4, reference monitor, loop EPT com
cursor) do que os três adicionam.

---

# Parte 2 — Auditoria de instruções e resources

Legenda de veredito: **CONFIRMADO** = o verificador cético reproduziu a evidência; **PARCIAL** = verdadeiro na essência, impreciso em detalhe (a versão corrigida está no achado); **NÃO-VERIFICADO** = sem segunda checagem. Achados encontrados independentemente por mais de um auditor estão mesclados (a redundância independente é sinal forte).

## Sumário

| # | Achado | Sev. | Veredito | Auditor(es) |
|---|--------|------|----------|-------------|
| 1 | Pre-flight inline (e resource) prescreve event_cursor(stream="workspace") mas a tool exige project_root e agent_id | alta | CONFIRMADO | inline-vs-code, token-budget |
| 2 | "Pass session_id + session_secret on every authenticated verb - each advances your heartbeat" é falso para a maioria dos verbos e usa nome de parâmetro errado | alta | PARCIAL | inline-vs-code |
| 3 | Inline se contradiz: "never spawn helper processes" vs recomendar o EPT remote poller (um processo helper) | media | CONFIRMADO | inline-vs-code |
| 4 | Communication resource manda 'aguardar' com event_wait sem timeout_seconds — a chamada como escrita é um snapshot imediato | media | PARCIAL | inline-vs-code |
| 5 | Passo 3 diverge entre inline ("if unread > 0") e resource ("if anything is pending") | baixa | CONFIRMADO | inline-vs-code |
| 6 | Resource governance v1 descreve um modelo flag-gated que não existe mais (enforcement é always-on/binding-driven) | alta | CONFIRMADO | tooldocs-vs-code |
| 7 | Resource governance aponta o CRUD REST legado cujas escritas NÃO alimentam mais o enforcement | alta | NAO-VERIFICADO | tooldocs-vs-code |
| 8 | Resource hitl v1 condiciona a interceptação a feature_governance, flag que não existe | media | NAO-VERIFICADO | tooldocs-vs-code |
| 9 | tool-docs/inbox documenta lease default 120s; o código e a superfície inline dizem 300s | media | CONFIRMADO | tooldocs-vs-code, inline-vs-code, token-budget |
| 10 | tool-docs/events omite trace_id das filter keys (rev 18) e nunca foi bumpado | media | CONFIRMADO | tooldocs-vs-code, inline-vs-code, token-budget |
| 11 | tool-docs/identity diz que agent_list retorna 'all registered agents (global)', mas discovery é escopada por reachability (rev 14) | media | CONFIRMADO | tooldocs-vs-code |
| 12 | tool-docs/artifacts não menciona a leitura audience-scoped do artifact_get (rev 25) — o resource sabe menos que o docstring inline | media | NAO-VERIFICADO | tooldocs-vs-code |
| 13 | tool-docs/identity omite effective_policies/governance/communication do retorno do agent_whoami | baixa | NAO-VERIFICADO | tooldocs-vs-code |
| 14 | target-grammar: bullet de edge cases restringe a rejeição de broadcast-em-mixed a message_create, mas ela é universal | baixa | NAO-VERIFICADO | tooldocs-vs-code |
| 15 | Changelog rev 25 declara +233 chars no ledger policies_b3; o ledger real registra 127 | baixa | CONFIRMADO | inline-vs-code |
| 16 | Gate de 40% desconta memory_i6 (2.388 chars) que não está na superfície default | alta | CONFIRMADO | token-budget |
| 17 | Componente params (17.512 chars) já excede o baseline pré-Frente-1 (16.406); top-10 consumidores concentrados em handoff/message | media | CONFIRMADO | token-budget |
| 18 | Cheat-sheet inline de target ainda carrega ~391 chars de regras do rich-selector, 2x, duplicando o target-grammar resource | media | PARCIAL | token-budget |
| 19 | Mecânica 'workspace_id = sha256(realpath)' repetida em 18 parâmetros project_root | media | PARCIAL | token-budget |
| 20 | handoff._P_SESSION_SECRET (197 chars x5) viola o invariante 'one credential story bus-wide' declarado no próprio código | media | CONFIRMADO | token-budget |
| 21 | _P_PROFILE (163 chars) idêntico em 5 tools = 815 chars; enum mínimo bastaria | media | CONFIRMADO | token-budget |
| 22 | Loop de recepção e receipts contados 3x entre resources: communication, tool-docs/inbox e tool-docs/messages | media | CONFIRMADO | token-budget |
| 23 | monitoring re-explica event_get/event_wait/event_cursor que tool-docs/events já cobre (~700 chars de overlap) | baixa | CONFIRMADO | token-budget |
| 24 | Regra 'verbo autenticado avança o heartbeat; session_heartbeat só quando idle' dita em 4 lugares | baixa | PARCIAL | token-budget |
| 25 | tool-docs/artifacts (601 chars) é órfão e ~100% redundante com os params inline de artifact_put | baixa | CONFIRMADO | token-budget |
| 26 | agent_register.capabilities (377 chars) embute mecânica de operador que já vive em tool-docs/identity | baixa | PARCIAL | token-budget |
| 27 | Ponteiros 'Full docs: okto-nexus://...' presentes em só 8 de 35 tools; tool-docs/events e tool-docs/artifacts não são referenciados por nenhum | media | NAO-VERIFICADO | token-budget |

## Instruções que falham ou enganam se seguidas literalmente (assertividade)

Afirmações da superfície inline (`SERVER_INSTRUCTIONS`) e dos resources de prosa que, seguidas ao pé da letra, produzem erro de validação, comportamento inesperado ou contradição — contra o lock do projeto (*o mínimo para chamar certo de primeira fica inline*).

### 1. Pre-flight inline (e resource) prescreve event_cursor(stream="workspace") mas a tool exige project_root e agent_id

**Severidade:** alta · **Veredito:** CONFIRMADO · **Auditor:** inline-vs-code · id `preflight-event-cursor-params`

**Problema.** Um agente que copiar literalmente o passo 4 do pre-flight — event_cursor(stream="workspace") — recebe erro de validação, porque event_cursor declara project_root e agent_id como parâmetros obrigatórios (str, sem default). Isso viola o lock do dono ('o mínimo para chamar uma tool certo de primeira FICA inline').

**Evidência.** server.py:110 "4. event_cursor(stream=\"workspace\") to anchor at NOW"; resources.py:149 "event_cursor(stream=\"workspace\") returns the log's current end"; tools/events.py:138-142 "def event_cursor(project_root: Annotated[str, ...], agent_id: Annotated[str, ...], stream: Annotated[str, ...])" — três obrigatórios. O monitor de referência (resources.py:306-308) passa os três corretamente, confirmando a forma completa.

**Recomendação.** No inline (server.py:110) e no preflight resource (resources.py:149), escrever a chamada completa: event_cursor(project_root=<cwd>, agent_id=<you>, stream="workspace"). Custa ~40 chars inline; assertividade > economia por lock.

**Δ tokens.** +~40 chars (~10 tokens) inline

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri os quatro pontos citados e todos batem. (1) src/okto_nexus/adapters/inbound/mcp/server.py:110 — passo 4 do pre-flight inline diz literalmente 'event_cursor(stream="workspace") to anchor at NOW'; os passos 1-3 do mesmo bloco escrevem formas completas, só o 4 elide parâmetros. (2) src/okto_nexus/adapters/inbound/mcp/resources.py:149 — o resource preflight (version="2") repete a forma abreviada. (3) src/okto_nexus/adapters/inbound/mcp/tools/events.py:138-142 — event_cursor(project_root, agent_id, stream), três Annotated[str] sem default → required no schema; conferi que tool_envelope (src/okto_nexus/envelope.py:95) não injeta argumentos e não há Context/derivação da conexão, logo a cópia literal produz erro de validação de argumentos. (4) resources.py:306-308 — o monitor de referência passa os três, confirmando a forma completa como canônica. O lock citado existe textualmente: tests/test_frente1_harness.py:3-7 ('owner's lock: assertividade de uso > economia de tokens ... call every tool correctly on the FIRST try') e o próprio server.py:102 promete 'act correctly on the first try' no bloco que contém o passo defeituoso. A recomendação não quebra nada: SERVER_INSTRUCTIONS é constante única usada por stdio (server.py:741) e HTTP (http/app.py:311), então a paridade se mantém; o gate S7 lê somente list_tools() (test_frente1_harness.py:10-14), nunca as instructions; o teste que pinna substrings das instructions (tests/test_tools_surface.py:124-171) não pinna o texto do passo 4. Ressalvas de completude para o executor (não refutam o achado): o fix deve bumpar a version do resource preflight ("2"→"3") e, por precedente de revisões doc-only (5, 6, 9, 11 em server.py:124-166), bumpar SURFACE_REVISION; e README.md:560 contém a mesma forma abreviada e merece o mesmo fix.

</details>

> **Duplicata independente** — `preflight-event-cursor-call-shape` (auditor token-budget, veredito CONFIRMADO): SERVER_INSTRUCTIONS e o preflight resource mostram 'event_cursor(stream="workspace")', mas o tool declara project_root, agent_id e stream todos required sem default; um agente que siga o texto literalmente erra a primeira chamada — contra o lock de assertividade (os passos 1-3 mostram shapes completos).

### 2. "Pass session_id + session_secret on every authenticated verb - each advances your heartbeat" é falso para a maioria dos verbos e usa nome de parâmetro errado

**Severidade:** alta · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** inline-vs-code · id `heartbeat-claim-overbroad`

**Problema.** O inline (passo 2) afirma que todo verbo autenticado aceita session_id+session_secret e avança o heartbeat ('working keeps you present'). Falso em três pontos: (a) só os verbos sensíveis M10 aceitam credenciais (message_create, handoff_claim/complete/reject, inbox_pull/ack/extend, poll_token_*) — event_get/event_wait/inbox_count/inbox_peek/agent_*/channel_* não têm esses parâmetros; (b) em message_create o parâmetro chama from_session_id, não session_id; (c) verbos read-only nunca avançam o heartbeat de sessão — o próprio resource monitoring (I3) afirma o oposto do inline. Um agente que só lê (event_get/inbox_count) acredita estar presente, fica stale em 60s e sai da audiência de broadcast em 1800s sem aviso.

**Correção do verificador.** O inline (server.py:108) afirma que TODO verbo autenticado aceita session_id+session_secret e avança o heartbeat — falso, mas a lista correta é maior que a do achado: aceitam credenciais e avançam o heartbeat forte quando validadas: message_create e memory_put (param chama-se from_session_id, não session_id), handoff_claim/complete/verify/reject/cancel e inbox_pull/ack/extend (param session_id; M10 trust.require), e poll_token_issue/renew/revoke (obrigatórios). handoff_create aceita apenas session_id de atribuição (sem secret, sem heartbeat). Os demais verbos (event_get/event_wait/event_cursor, inbox_count/inbox_peek/inbox_history, agent_*, channel_*, workspace_*) não têm esses parâmetros e nunca avançam o heartbeat FORTE — e em open mode até os verbos sensíveis só avançam se o secret for fornecido (identity.py:275-291). O dano real limita-se à audiência de broadcast e ao strict mode: a sessão fica stale em 60s e sai da audiência de broadcast em 1800s (resources.py I3, README); o indicador online do dashboard NÃO é igualmente afetado, pois também usa last_seen_at, bumpado por todo verbo autenticado inclusive read-only (README.md:789-797). A correção deve reescrever a frase em TRÊS lugares — server.py:108, resources.py:137-140 (com bump da version do resource preflight "2"→"3") e resources_docs.py:416-426 — usando a lista completa acima (não a lista sub-inclusiva da recomendação original) ou uma formulação não-enumerativa ("on every verb that accepts them; read-only verbs do not — call session_heartbeat on idle/read-only turns"). Paridade stdio/http se mantém automaticamente (SERVER_INSTRUCTIONS é constante única usada por ambos os transportes; test_tools_surface.py:138) e o gate S7 permanece atendido pois a orientação continua inline.

**Evidência.** server.py:108 "Pass your session_id + session_secret on every authenticated verb - each advances your heartbeat, so working keeps you present"; config.py:69-74 lista fechada dos verbos strict; tools/events.py:152-160 event_wait sem parâmetros de sessão; tools/messages.py:248-257 "from_session_id ... session_secret"; resources.py:273-275 "neither event_wait nor EPT reads advance your strong session heartbeat"; identity.py:275-278 (open mode sem secret: require retorna sem heartbeat).

**Recomendação.** Reescrever o inline: "Pass session_id + session_secret on every verb that accepts them (message_create names it from_session_id; handoff_claim/complete/reject; inbox_pull/ack/extend; poll_token_*) - each advances your heartbeat. Read-only verbs (event_*, inbox_count/peek) do NOT; call session_heartbeat on read-only/idle turns." Replicar no preflight resource (resources.py:138-141), que repete a frase.

**Δ tokens.** +~120 chars (~30 tokens) inline

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e conferi cada evidência citada. CONFIRMADO: (1) src/okto_nexus/adapters/inbound/mcp/server.py:108 contém a frase exata "Pass your session_id + session_secret on every authenticated verb - each advances your heartbeat"; (2) src/okto_nexus/config.py:68-74 define a lista fechada do strict mode (message_create, handoff_claim/complete/reject, inbox_pull/ack/extend); (3) tools/events.py:111-185 (event_get/event_cursor/event_wait), tools/inbox.py:207-238 (inbox_peek/inbox_count), tools/identity.py:306-325 (agent_list/agent_get) e channel_create/channel_list em tools/messages.py NÃO têm parâmetros de sessão — não podem avançar o heartbeat; (4) message_create usa from_session_id (tools/messages.py, param _P_FROM_SESSION) e avança presença só quando credenciais são validadas (application/messages.py:311-327); (5) resources.py:273-280 (I3) afirma que event_wait/EPT não avançam o heartbeat forte, com defaults 60s (stale) e 1800s (broadcast audience) — contradiz o inline; (6) application/identity.py:275-291 — em open mode sem secret o require retorna sem avançar heartbeat; (7) resources.py:137-140 repete a frase no resource preflight (version="2"). IMPRECISÕES que impedem CONFIRMADO: (a) a lista de verbos que aceitam credenciais no achado é SUB-INCLUSIVA — tools/handoff.py:396-458 mostra que handoff_verify e handoff_cancel também chamam trust.require (validam e avançam heartbeat via identity.py:291), e tools/memory.py:168-188 mostra memory_put com from_session_id+session_secret (avança via application/memory.py:275); handoff_create aceita session_id só de atribuição (_P_SESSION_OPT, handoff.py:112, sem secret, sem heartbeat); a RECOMENDAÇÃO reproduziria essa lista incompleta, violando o próprio lock de assertividade; (b) a recomendação ignora uma TERCEIRA repetição da frase em resources_docs.py:416-426 (docs de session_open/session_heartbeat: "any authenticated active verb ... advances your heartbeat"); (c) nuance no dano: README.md:776-797 documenta DUAS noções de presença — a audiência de broadcast é estritamente heartbeat de sessão (o dano descrito é real), mas o indicador online do dashboard usa o mais fresco entre heartbeat e last_seen_at, que TODO verbo autenticado (inclusive read-only) bumpa; logo a metade "show online" do inline não é falsa para o dashboard, só para a audiência de broadcast. Gates: editar SERVER_INSTRUCTIONS não quebra paridade stdio/http (constante única, server.py:741 + http/app.py:311, travada por tests/test_tools_surface.py:127-138, que não fixa o texto); o gate S7 (harness sem resources) permanece atendido pois a correção fica inline; tests/test_frente1_resources.py só exige frontmatter version não-vazio — editar o resource preflight exige bump da version ("2"→"3"), o que a recomendação não menciona.

</details>

### 3. Inline se contradiz: "never spawn helper processes" vs recomendar o EPT remote poller (um processo helper)

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** inline-vs-code · id `inline-helper-process-contradiction`

**Problema.** O parágrafo YOUR IDENTITY proíbe categoricamente spawnar helper processes, mas o passo 4 do mesmo bloco (e o parágrafo COMMUNICATE) recomendam o 'EPT remote poller', que é exatamente um processo background separado. A reconciliação ('a separate process is acceptable only as an EPT poller') existe apenas no resource monitoring — um agente que lê só o inline ou recusa a opção EPT ou viola a proibição como escrita.

**Evidência.** server.py:104 "never shell out to the okto-nexus CLI, spawn helper processes, or attach a stdio server" vs server.py:110 "monitor via event_wait ..., an EPT remote poller (poll_token_issue -> /api/v1/events)"; a exceção só em resources.py:384-386 "A separate process is acceptable only as an EPT poller whose output wakes the harness".

**Recomendação.** Qualificar o inline: "never shell out to the okto-nexus CLI, attach a stdio server, or spawn helper processes carrying your nxs_ key (the ONE sanctioned separate process is an EPT poller holding only a nxsept_ token)".

**Δ tokens.** +~60 chars (~15 tokens) inline

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri src/okto_nexus/adapters/inbound/mcp/server.py e resources.py. server.py:104 traz verbatim "never shell out to the okto-nexus CLI, spawn helper processes, or attach a stdio server" (categórico, sem exceção); server.py:110 (passo 4 do PRE-FLIGHT, mesmo SERVER_INSTRUCTIONS) recomenda "an EPT remote poller (poll_token_issue -> /api/v1/events)"; server.py:117 (COMMUNICATE/HOW YOU RECEIVE) também menciona "EPT remote pollers that do not carry the permanent key". O próprio produto define o EPT poller como "a separate background process" (resources.py:237-240 e 344-347), logo é um helper process. A reconciliação explícita "A separate process is acceptable only as an EPT poller whose output wakes the harness" existe apenas em resources.py:384-386, dentro do corpo do resource slug="monitoring" (resources.py:222; último add_resource, corpo até a linha 388) — o qualificador inline da linha 117 é descritor+ponteiro, não exceção à proibição. resources.py:387-388 ainda repete "NO spawning a helper process or a second server", confirmando a intenção "ban geral + exceção EPT" que o inline não carrega. A recomendação não quebra locks: nenhum teste trava a frase (test_tools_surface.py:124-171 só exige substrings: ordem inbox_count<pull<ack, "ERRORS & RETRIES", ponteiros aos resources); paridade stdio/http preservada pois SERVER_INSTRUCTIONS é constante única usada em server.py:741 e http/app.py:311; +~60 chars mantém assertividade; gate S7 melhora (reconciliação passa a existir inline). Ressalva de implementação (não refuta o achado): a reformulação "spawn helper processes carrying your nxs_ key" estreita o ban — em loopback um helper SEM chave vira operator keyless no REST (decisão D5, CLAUDE.md) — então a parentética "the ONE sanctioned separate process is an EPT poller holding only a nxsept_ token" é obrigatória, ou melhor ainda: manter o ban intacto e anexar a exceção ("spawn helper processes (sole exception: an EPT poller holding only a nxsept_ token, never your nxs_ key)").

</details>

### 4. Communication resource manda 'aguardar' com event_wait sem timeout_seconds — a chamada como escrita é um snapshot imediato

**Severidade:** media · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** inline-vs-code · id `event-wait-await-snapshot`

**Problema.** O resource communication prescreve "Await one with event_wait(filters={\"type\":\"message.read\"})". Como timeout_seconds tem default 0 (snapshot não-bloqueante, opt-in para long-poll só com >0), a chamada prescrita NÃO aguarda nada — retorna imediatamente vazio; e ainda omite project_root/agent_id/stream obrigatórios. O inline tem o mesmo germe ao chamar event_wait de "background long-poll" sem mencionar o opt-in.

**Correção do verificador.** O resource communication (resources.py:213-214) prescreve "Await one with event_wait(filters={\"type\":\"message.read\"})". Como timeout_seconds tem default 0 (snapshot não-bloqueante; >0 é opt-in para long-poll — tools/events.py:159 e 67-71; comportamento confirmado em application/events.py:313-318), a chamada prescrita NÃO aguarda nada: retorna imediatamente — e, como o exemplo também omite cursor (omitido = desde o início do log), pode retornar receipts message.read ANTIGOS em vez de vazio. A omissão de project_root/agent_id/stream é abreviação de doc sem impacto em runtime (o schema os marca required e força o preenchimento); o defeito real é o timeout 0 silencioso, apenas parcialmente mitigado pela descrição _P_TIMEOUT visível no schema. O inline (server.py:110) tem o mesmo germe ao chamar event_wait de "background long-poll" sem mencionar o opt-in. Correção deve usar a forma completa E ancorada: event_wait(project_root=..., agent_id=<you>, stream="workspace", cursor=<âncora do event_cursor>, filters={"type":"message.read"}, timeout_seconds=25).

**Evidência.** resources.py:213-214 "Await one with event_wait(filters={\"type\":\"message.read\"}) and match payload.message_id" vs tools/events.py:159 "timeout_seconds: ... = 0" e tools/events.py:67-70 (_P_TIMEOUT: "default 0 ... an immediate non-blocking snapshot; >0 OPTS IN to a BLOCKING long-poll").

**Recomendação.** Corrigir o exemplo para a forma completa e bloqueante: event_wait(project_root=..., agent_id=<you>, stream="workspace", filters={"type":"message.read"}, timeout_seconds=25). No inline, trocar "event_wait (background long-poll)" por "event_wait(timeout_seconds>0) (background long-poll)".

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e conferi: (1) src/okto_nexus/adapters/inbound/mcp/resources.py:213-214 — o resource 'communication' (slug linha 161) prescreve literalmente 'Await one with event_wait(filters={"type":"message.read"}) and match payload.message_id'. (2) tools/events.py:159 — timeout_seconds default 0; _P_TIMEOUT em events.py:67-71 (achado citou 67-70, trivial) diz '0/omitted/null = immediate non-blocking snapshot; >0 OPTS IN to a BLOCKING long-poll'. (3) Runtime real confirma: application/events.py:313-318 — timeout<=0 faz um único scan e retorna na hora; tools/events.py:180 mapeia None→0. (4) project_root/agent_id/stream são required sem default (tools/events.py:153-155). (5) Inline server.py:110: 'event_wait (background long-poll)' sem o opt-in — confirmado. IMPRECISÕES: 'retorna imediatamente vazio' é errado no caso geral — o exemplo também omite cursor, e cursor omitido = 'from the beginning' (tools/events.py:61), logo num workspace com histórico o snapshot retorna message.read ANTIGOS (página não-vazia, stale); só é vazio sem receipts prévios. E a omissão de project_root/agent_id/stream não causa falha em runtime: o schema os marca required e força o preenchimento (mitigação: _P_TIMEOUT também é visível no schema; o defeito real é o 0 silencioso do timeout). RECOMENDAÇÃO checada contra os travamentos: lock 'assertividade>tokens' (resources.py:5-6) — alinhada; gate S4 medido ao vivo com o instrumento real = 46,378% de redução (folga ~2.652 chars; acréscimo inline ~18 chars; corpo de resource não conta na superfície residente — tests/test_frente1_measurement.py:65); gate S7 (tests/test_frente1_harness.py:163-171) só exige tools/params descritos no tools/list — intocado; paridade stdio/http intocada (create_server único, server.py:741-744). timeout_seconds=25 < teto 30 (config.py:142). Ressalva na recomendação: o exemplo corrigido deveria também incluir cursor=<âncora do event_cursor>, senão a forma bloqueante ainda retorna na hora com receipts históricos.

</details>

### 5. Passo 3 diverge entre inline ("if unread > 0") e resource ("if anything is pending")

**Severidade:** baixa · **Veredito:** CONFIRMADO · **Auditor:** inline-vs-code · id `preflight-step3-wording`

**Problema.** O gate inline "if unread > 0" está correto e cobre in-flight expirado (o count dobra lease expirado em unread), mas o preflight resource diz "if anything is pending" — 'pending' na terminologia do bus é unread + in_flight (docstring do peek), e um in-flight com lease vigente não é pullável: um agente que pull-e por causa de in_flight fresco recebe página vazia e pode concluir erroneamente que perdeu mensagens.

**Evidência.** server.py:109 "if unread > 0, inbox_pull" vs resources.py:144-145 "if anything is pending, inbox_pull"; application/inbox.py:296-299 "an elapsed in-flight delivery is COUNTED as ``unread``"; application/inbox.py:248 peek = "pending deliveries (unread + in-flight)".

**Recomendação.** Alinhar o resource ao inline: "if unread > 0 (expired in-flight leases already count as unread), inbox_pull...".

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri todos os arquivos citados e desci até o SQL para não confiar só em docstrings. (1) Divergência textual confirmada: src/okto_nexus/adapters/inbound/mcp/server.py:109 diz "if unread > 0, inbox_pull" enquanto src/okto_nexus/adapters/inbound/mcp/resources.py:144-145 (resource preflight, version "2") diz "if anything is pending, inbox_pull"; o mesmo resources.py:196 (resource communication) usa a forma correta "if unread > 0, pull". (2) "Pending" = unread + in-flight na terminologia do bus: docstring do peek em src/okto_nexus/application/inbox.py:248 ("View pending deliveries (unread + in-flight)") e docstring do módulo linha 12. (3) O gate inline cobre in-flight expirado de verdade, não só em docstring: inbox.py:296-299 (count) e a implementação em src/okto_nexus/adapters/outbound/sqlite/messages_repo.py:590-602 — o CASE com _EXPIRED (linha 391: status='delivered' AND lease_expires_at < now) reclassifica lease expirado como lane 'unread' no COUNT. (4) In-flight com lease vigente não é pullável: o claim do pull (messages_repo.py:448-453) só pega "status = 'unread' OR _EXPIRED"; docstring do pull em inbox.py:121-129 confirma. Logo, com unread=0 e in_flight fresco > 0, "anything is pending" induz um inbox_pull que retorna página vazia — cenário real em bootstrap pós-crash com lease de até 3600s (inbox.py:68). (5) A recomendação não quebra nada: o lock "assertividade de uso > economia de tokens" está em resources.py:5-7 e favorece a precisão; o DESIGN LOCK (resources.py:10-16) só restringe o que fica inline, e o inline não muda; o gate S7 (tests/test_frente1_harness.py:109-192) lê APENAS list_tools() — nunca resources — e não é afetado; a paridade stdio/http (tests/test_http_parity.py:56-68) compara URIs de resources, que não mudam; nenhum teste fixa o texto do corpo (tests/test_frente1_resources.py só valida o conjunto fechado de 12 URIs e o frontmatter "version:"). ÚNICA RESSALVA operacional (não invalida o achado): ao editar o corpo do resource preflight é obrigatório bumpar sua version "2"→"3" (invariante documentada em resources.py:15-16 e 39: "bump on every change", consumida por nexus_info.resource_versions para detecção de cache obsoleto) — a recomendação não menciona isso.

</details>

## Drift entre resources e código

Resources de referência que ficaram para trás do código (nenhum teve a `version` bumpada quando o contrato mudou — o mecanismo `nexus_info.resource_versions` existe exatamente para isso e não está sendo exercitado).

### 6. Resource governance v1 descreve um modelo flag-gated que não existe mais (enforcement é always-on/binding-driven)

**Severidade:** alta · **Veredito:** CONFIRMADO · **Auditor:** tooldocs-vs-code · id `governance-resource-obsoleto`

**Problema.** O resource okto-nexus://reference/governance afirma que a governança é gated por feature_governance e que 'When the flag is OFF nothing is enforced and nothing changes for you', e que o bloco governance do agent_whoami aparece 'ONLY when the flag is ON and at least one active policy matches you'. Isso é falso: a flag feature_governance foi removida (rev 25), o enforcement é sempre ativo e dirigido por BINDINGS (não por subject-match global), e o bloco do whoami aparece quando o caller tem bindings com regras de governança — independente de qualquer flag.

**Evidência.** resources_docs.py:479 '# GOVERNANCE POLICIES (feature_governance, default OFF)' e :482 'When the flag is OFF nothing is enforced and nothing changes for you.' vs application/governance.py:7-8 'Enforcement is ALWAYS-ON and binding-driven - there is no feature flag (D-FLAG)' e :195-199; config.py:183-189 não contém feature_governance (só trace/hitl/verification/dag/memory/health/replay); tests/test_feature_flags.py:20-21 'feature_governance was removed (spec 80624c1a, D-FLAG)'. Condição do whoami: governance.py:416-418 'Empty when the caller has no bindings ... the tool then omits the block'.

**Recomendação.** Reescrever o resource governance como v2 alinhado à spec 80624c1a: (a) remover toda menção a feature_governance e à semântica 'flag OFF = nada enforçado'; (b) explicar o modelo de bindings ('sem binding = sem regra = pass; caller sem identidade nunca é governado' — governance.py:204-205); (c) corrigir a seção 'Discovering...' para 'o bloco governance aparece quando você tem bindings com regras' e documentar que policy_id ali é o label inline / <policy_id>@<version> (governance.py:414-415), não necessariamente 'pol_...'; (d) mencionar effective_policies. Bumpar version para "2" (nexus_info.resource_versions detecta o cache velho).

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei cada peça da evidência abrindo os arquivos (somente leitura):

1. Resource desatualizado — D:\Projetos\Techridy\okto_labs_okto_nexus\src\okto_nexus\adapters\inbound\mcp\resources_docs.py: linha 479 diz literalmente "# GOVERNANCE POLICIES (feature_governance, default OFF)"; linha 481-482 "When the flag is OFF nothing is enforced and nothing changes for you"; linhas 529-531 "``agent_whoami`` includes a ``governance`` block ... ONLY when the flag is ON and at least one active policy matches you"; linha 477 version="1"; linha 471 ainda referencia "spec ffef15bf, feature_governance - surface rev 19". Também descreve o modelo de subject global (agent/role/capability/star, linhas 487-491), que foi substituído.

2. Flag removida — src\okto_nexus\config.py:183-189 lista apenas feature_trace/hitl/verification/dag/memory/health/replay (sem feature_governance); tests\test_feature_flags.py:20-21 diz "feature_governance was removed (spec 80624c1a, D-FLAG): policy enforcement is always-on and binding-driven"; grep por feature_governance em src\ só encontra comentários históricos (errors.py:67, migration 022, server.py revs 19/20) e o próprio resource obsoleto.

3. Enforcement always-on/binding-driven — src\okto_nexus\application\governance.py:7-8 "Enforcement is ALWAYS-ON and binding-driven - there is no feature flag (D-FLAG)"; :195-205 (docstring de enforce) confirma "there is no feature flag", "actor with NO bindings resolves to no sources -> no rules -> pass" e "Callers WITHOUT an identity (cooperative stdio) can hold no bindings, so they pass"; :213-218 implementa exatamente isso. Migration 022_policies.sql:81-92 confirma que políticas legadas foram migradas DETACHED (sem binding) justamente para NÃO enforçar — binding é o sujeito.

4. Rev 25 — src\okto_nexus\adapters\inbound\mcp\server.py:349-359: "25 = attachable policies (spec 80624c1a, migration 022) ... Enforcement is always-on and binding-driven (``feature_governance`` removed)".

5. Condição real do bloco whoami — governance.py:410-420 (policies_for_agent): "Empty when the caller has no bindings (or none carry governance) - the tool then omits the block entirely"; :414-415 confirma que policy_id ali é o label "inline" / "<policy_id>@<version>", não "pol_...". O tool em adapters\inbound\mcp\tools\identity.py:232-237 inclui effective_policies + governance sem consultar flag alguma.

6. Recomendação não quebra locks — o DESIGN LOCK (resources_docs.py:10-14) exige apenas que a superfície inline compacta permaneça autossuficiente (gate S7 "harness sem resources"); reescrever o BODY do resource não toca docstrings inline nem adiciona/remove tools, então S7 e a paridade stdio/http (test_http_parity, que compara superfícies de TOOLS) ficam intactos. O mecanismo de bump existe: server.py:687,692 expõe resource_versions via nexus_info para detecção de cache velho, e o campo version="1" está em resources_docs.py:477. Ressalva menor (não invalida o achado): o resource hitl no mesmo arquivo (linhas 546-551) também menciona feature_governance ("BOTH feature_governance and feature_hitl are ON") e ficará inconsistente se só o resource governance for reescrito — a correção deveria cobrir os dois.

</details>

### 7. Resource governance aponta o CRUD REST legado cujas escritas NÃO alimentam mais o enforcement

**Severidade:** alta · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** tooldocs-vs-code · id `governance-rest-endpoint-morto`

**Problema.** O resource governance instrui 'Policies are managed by operators over REST (/api/v1/governance/policies)', mas uma policy criada hoje nesse endpoint só grava na tabela legada governance_policies, que o enforcement não lê mais (o enforce compõe apenas bindings + policy versions). Migration 022 espelhou as linhas UMA vez; escritas novas via esse endpoint não restringem ninguém — o operador que seguir o resource cria uma policy inerte.

**Evidência.** resources_docs.py:532 'Policies are managed by operators over REST (/api/v1/governance/policies)' vs routes.py:2002-2003 'this surface is kept until the /policies surface (B1) supersedes it. Enforcement itself no longer reads this table - it composes the actor's attached policies.'; governance.py:483 create_policy grava só em self._governance, enquanto enforce() (:213-216) lê _effective_sources -> _policy_bindings/_policies (:264-281).

**Recomendação.** No resource v2, apontar o fluxo operativo real: POST /api/v1/policies + POST /policies/{id}/versions + PUT /api/v1/agents/{agent_id}/policies (routes.py:2086/2170/2230), deixando /governance/policies marcado como legado/inerte para enforcement (ou omitido). Alternativa de código: fazer o CRUD legado também criar policy detached + versão, se a intenção é mantê-lo funcional até B1.

### 8. Resource hitl v1 condiciona a interceptação a feature_governance, flag que não existe

**Severidade:** media · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** tooldocs-vs-code · id `hitl-gate-flag-inexistente`

**Problema.** O resource hitl afirma 'Interception only happens when BOTH feature_governance and feature_hitl are ON; with either flag OFF nothing changes for you'. O gate real é: uma regra require_approval efetiva (via binding do caller) + feature_hitl ON, lida ao vivo. feature_governance não existe em NexusConfig; um agente que consulte nexus_info.features nunca encontrará essa flag e não conseguirá prever a interceptação pela doc.

**Evidência.** resources_docs.py:549-551 'Interception only happens when BOTH ``feature_governance`` and ``feature_hitl`` are ON' vs application/governance.py:207-210 'when the action would have passed and a ``require_approval`` rule matches AND ``feature_hitl`` is ON (read live)' e :244-250; config.py:183-189 (sem feature_governance). O restante do resource (envelope {status:'pending_approval', approval_id, action, policy_id, watch{stream:'workspace', types:[approval.granted, approval.denied], approval_id}, trace_id?}, CONFLICT na 2ª decisão, subject 'Approval <id>: <action> rejected') confere com approvals.py:209-222, :290, :406.

**Recomendação.** Bumpar hitl para v2 trocando a frase por: 'Interception happens when a require_approval rule bound to you matches AND feature_hitl is ON (check nexus_info.features.feature_hitl and your agent_whoami governance block)'. Também atualizar 'setting a governance policy' para 'binding a policy whose version carries a require_approval rule'.

### 9. tool-docs/inbox documenta lease default 120s; o código e a superfície inline dizem 300s

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** tooldocs-vs-code · id `inbox-lease-default-120-vs-300`

**Problema.** O resource tool-docs/inbox afirma que inbox_pull tem '``lease_seconds`` (default 120, clamped 10..3600)'. O default real é DEFAULT_INBOX_LEASE_TTL_SECONDS = 300 (configurável via inbox_lease_ttl_seconds), usado quando lease_seconds é omitido; a descrição inline do parâmetro interpola a constante e portanto exibe 300 — o resource 'profundo' contradiz a superfície residente que ele deveria aprofundar. Clamp 10..3600, preview de 200 chars e parked após 5 attempts conferem.

**Evidência.** resources_docs.py:168 'Size the lease with ``lease_seconds`` (default 120, clamped 10..3600)' vs config.py:24 'DEFAULT_INBOX_LEASE_TTL_SECONDS = 300', tools/inbox.py:61-65 (_P_LEASE_SECONDS interpola o default 300) e :115 'lease_ttl_seconds=deps.config.inbox_lease_ttl_seconds', application/inbox.py:679-680 (None -> self._lease_ttl).

**Recomendação.** Corrigir para 'default 300 — o knob inbox_lease_ttl_seconds do servidor; clamped 10..3600' e bumpar tool-docs/inbox para v2. Idealmente interpolar DEFAULT_INBOX_LEASE_TTL_SECONDS no corpo do resource (como o inline já faz) para impedir novo drift.

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri cada arquivo citado e conferi linha a linha. (1) D:\Projetos\Techridy\okto_labs_okto_nexus\src\okto_nexus\adapters\inbound\mcp\resources_docs.py:168 diz literalmente "``lease_seconds`` (default 120, clamped 10..3600)" dentro do resource slug="tool-docs/inbox" (linha 154), que está em version="1" (linha 157). (2) O default real é 300: config.py:24 "DEFAULT_INBOX_LEASE_TTL_SECONDS = 300" e config.py:145 "inbox_lease_ttl_seconds: int = DEFAULT_INBOX_LEASE_TTL_SECONDS". (3) A superfície inline exibe 300: tools/inbox.py:61-65 monta _P_LEASE_SECONDS via f-string interpolando DEFAULT_INBOX_LEASE_TTL_SECONDS (=300), MIN_LEASE_SECONDS (=10) e MAX_LEASE_SECONDS (=3600); tools/inbox.py:115 injeta lease_ttl_seconds=deps.config.inbox_lease_ttl_seconds no serviço. (4) Caminho do default quando lease_seconds é omitido: application/inbox.py:133 chama _clamp_lease_seconds, e em :679-680 "if seconds is None and not required: return self._lease_ttl", com self._lease_ttl = int(lease_ttl_seconds) em :111 — ou seja, 300 por default de config. (5) Os demais fatos do resource conferem com o código: clamp 10..3600 (application/inbox.py:67-68), preview de 200 chars (PEEK_BODY_PREVIEW_CHARS = 200, application/inbox.py:76, citado no resource em resources_docs.py:186), parked/dead-letter após exaustão de attempts (DEFAULT_MAX_DELIVERY_ATTEMPTS = 5, application/inbox.py:72; o resource não cita o número, apenas "redelivered too many times is parked" — sem contradição). Tentativas de refutar a RECOMENDAÇÃO falharam: o gate S7 (tests/test_frente1_harness.py:109-110) lê SOMENTE list_tools() e nunca resources/read, então editar o corpo do resource não o afeta; tests/test_frente1_resources.py:134-145 só exige frontmatter "version:" não-vazio (bump para "2" passa); o S8 (test_frente1_harness.py:198-222) só exige strings de versão não-vazias, e resource_versions() deriva automaticamente do registro add_resource (resources.py:70-72), então o bump propaga sozinho; não há teste de budget de tokens sobre corpos de resources (test_frente1_measurement.py não contém budget/threshold); test_http_parity.py cobre a superfície de TOOLS, e resources são registrados uma vez no mesmo FastMCP server usado por stdio e http — sem quebra de paridade. Única ressalva prática (não invalida o achado): se interpolar a constante no corpo do resource via f-string, os literais com chaves no corpo (ex.: "{acknowledged, read_message_ids}" em resources_docs.py:173, "{unread, in_flight, read}" em :191) precisarão de chaves duplicadas.

</details>

> **Duplicata independente** — `inbox-lease-default-120` (auditor inline-vs-code, veredito CONFIRMADO): O resource tool-docs/inbox documenta "lease_seconds (default 120, clamped 10..3600)", mas DEFAULT_INBOX_LEASE_TTL_SECONDS = 300 em config.py, e a descrição inline do parâmetro interpola essa constante (300). Um agente que planeje o ack pelo resource assume janela de redelivery 2,5x menor que a real (ou, pior, confia em 120s que não valem se o operador mudou o knob).

> **Duplicata independente** — `inbox-lease-default-drift` (auditor token-budget, veredito CONFIRMADO): O resource okto-nexus://reference/tool-docs/inbox (v1) diz 'Size the lease with lease_seconds (default 120, clamped 10..3600)', mas DEFAULT_INBOX_LEASE_TTL_SECONDS = 300. O inline _P_LEASE_SECONDS interpola a constante via f-string e está correto — o doc 'profundo' contradiz a superfície inline e o código.

### 10. tool-docs/events omite trace_id das filter keys (rev 18) e nunca foi bumpado

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** tooldocs-vs-code · id `events-filter-sem-trace-id`

**Problema.** O resource tool-docs/events (version 1) afirma que 'filters (equality, AND-combined) allow keys: type, agent_id, task_id, handoff_id', mas o domínio aceita também trace_id (FILTER_KEYS), a descrição inline do parâmetro já lista trace_id, e a revisão 18 do changelog registra a adição. Um agente que siga o resource deixará de usar um filtro válido para seguir traces; o resource ficou atrás da própria superfície compacta que deveria aprofundar.

**Evidência.** resources_docs.py:214-215 'filters (equality, AND-combined) allow keys: type, agent_id, task_id, handoff_id.' vs domain/events.py:61-63 'FILTER_KEYS ... {"type", "agent_id", "task_id", "handoff_id", "trace_id"}' e tools/events.py:63-66 'Keys: type, agent_id, task_id, handoff_id, trace_id'; server.py:230-231 (rev 18: 'filters gain the payload-level ``trace_id`` key').

**Recomendação.** Acrescentar trace_id à lista de keys (com a nota de que type/agent_id são colunas e task_id/handoff_id/trace_id são payload-level, cf. domain/events.py:59-60) e bumpar tool-docs/events para v2.

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Tentei refutar abrindo cada arquivo citado; tudo confere. (1) D:\Projetos\Techridy\okto_labs_okto_nexus\src\okto_nexus\adapters\inbound\mcp\resources_docs.py:205-216 — o resource slug="tool-docs/events" tem version="1" (linha 209) e o body diz "filters (equality, AND-combined) allow keys: type, agent_id, task_id, handoff_id." (linhas 215-216; o achado citou 214-215, off-by-one trivial) — trace_id ausente. (2) src\okto_nexus\domain\events.py:61-63 — FILTER_KEYS = frozenset({"type","agent_id","task_id","handoff_id","trace_id"}), aceito INCONDICIONALMENTE em normalize_filters (linha 145, sem gate de feature flag); o comentário nas linhas 58-60 confirma que task_id/handoff_id/trace_id são payload-level e type/agent_id colunas, exatamente como a recomendação propõe anotar. (3) src\okto_nexus\adapters\inbound\mcp\tools\events.py:63-66 — _P_FILTERS lista "type, agent_id, task_id, handoff_id, trace_id" e é usado incondicionalmente em event_get (linha 117) e event_wait (linha 158): o resource "full reference" está de fato atrás da superfície inline compacta. (4) src\okto_nexus\adapters\inbound\mcp\server.py:222-232 (o achado citou "server.py"; o path completo é o do adapter MCP) — rev 18 registra "event_get/event_wait filters gain the payload-level ``trace_id`` key" (linhas 230-231). A recomendação não quebra nada: (a) o gate S7 (tests\test_frente1_harness.py:108-110) lê SÓ list_tools(), nunca resources — e o inline já lista trace_id; (b) tests\test_frente1_resources.py asserta apenas o conjunto fechado de 12 URIs e a presença do frontmatter "version:", sem pinar valores de versão nem o texto do body (grep por "allow keys"/"task_id, handoff_id" nos testes só acha test_mcp_projection.py:144, não relacionado); (c) bump de versão é o protocolo documentado em resources.py:39-40 ("bump on content change"; nexus_info expõe {uri: version} para stale-cache); (d) paridade stdio/http (test_http_parity) cobre a superfície de TOOLS, e os resources vivem num registry único compartilhado — inalterada; (e) o lock "assertividade > tokens" favorece a correção: bodies de resources não entram em nenhum budget de tokens dos testes (grep budget/resource em test_frente1_measurement.py e test_surface_metrics.py: zero matches) e a adição corrige uma omissão factual. Única nuance (não invalida a claim): com feature_trace OFF os payloads não carregam trace_id, então o filtro é aceito mas casa vazio — a claim diz apenas que o domínio "aceita", o que é exato.

</details>

> **Duplicata independente** — `tool-docs-events-trace-id` (auditor inline-vs-code, veredito CONFIRMADO): O resource tool-docs/events (version "1", nunca bumpada) lista as filter keys como "type, agent_id, task_id, handoff_id", mas FILTER_KEYS do domínio e a descrição inline _P_FILTERS incluem trace_id (adicionado na SURFACE_REVISION 18). Um agente que confie no resource conclui que filtrar por trace não é possível via MCP.

> **Duplicata independente** — `events-filter-trace-id-drift` (auditor token-budget, veredito PARCIAL): O resource tool-docs/events (resources_docs.py:215-216) diz 'filters (equality, AND-combined) allow keys: type, agent_id, task_id, handoff_id' mas FILTER_KEYS em domain/events.py:61-63 inclui trace_id (introduzido pela migration 015_trace_id.sql, commit d7e3c78/v0.1.0 — não "rev 18"; a 018 é handoff_verification) e o inline _P_FILTERS (tools/events.py:63-66) já lista trace_id — o doc profundo diz MENOS que a superfície inline e que a própria mensagem de erro de normalize_filters (domain/events.py:139-140), negando ao leitor um filtro válido e funcional. O resource está em version="1" desde sua criação (commit 391d401), anterior à introdução de trace_id, sem bump quando o contrato mudou.

### 11. tool-docs/identity diz que agent_list retorna 'all registered agents (global)', mas discovery é escopada por reachability (rev 14)

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** tooldocs-vs-code · id `identity-discovery-sem-reachability`

**Problema.** O resource tool-docs/identity (v3) descreve agent_list/agent_get como 'List all registered agents (global) ... or read one agent's details' sem mencionar que, para caller autenticado, a lista é filtrada pela dupla interseção de comm_scope (visible = reachable) e que agent_get de um agente inalcançável retorna NOT_FOUND indistinguível de inexistente. As docstrings inline documentam isso; o 'full reference' não — um agente que investigue um NOT_FOUND de um agente existente não encontra a explicação na doc profunda.

**Evidência.** resources_docs.py:398-400 '# agent_list / agent_get\nList all registered agents (global), each with role/capabilities and last_seen_at; or read one agent's details.' vs application/identity.py:556-560 'Discovery is scoped by reachability (F2 ...): an AUTHENTICATED caller sees only the agents its comm scope can reach' e :573-576 (agent_get inalcançável -> NOT_FOUND 'byte-identical to the non-existent case'); tools/identity.py:307 e :320 (inline já documenta).

**Recomendação.** Adicionar ao bloco agent_list/agent_get/capability_list do resource: 'Authenticated callers see only agents reachable by their comm scope (plus themselves); an unreachable agent_id reads as NOT_FOUND, indistinguishable from nonexistent; anonymous callers see all'. Bumpar identity para v4.

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e conferi cada evidência no repo (somente leitura):

1) Resource "tool-docs/identity" — src/okto_nexus/adapters/inbound/mcp/resources_docs.py:364 (slug), :367 (version="3"), :398-400: o bloco "# agent_list / agent_get" diz literalmente "List all registered agents (global), each with role/capabilities and last_seen_at; or read one agent's details. Discovery surface for addressing." Sem qualquer menção a reachability. Pior: o cabeçalho do resource (:369-371) reforça a impressão de globalidade ("agent_list / agent_get / capability_list are deliberately cross-workspace (discovery)"). Grep case-insensitive por reachab|comm scope|comm_scope|unreachable em resources_docs.py: zero ocorrências; em resources.py (preflight/communication/monitoring): também nada. Ou seja, NENHUM resource profundo explica o filtro — a lacuna existe exatamente como descrita.

2) Comportamento real — src/okto_nexus/application/identity.py:549-565: agent_list chama _filter_reachable; docstring :556-560 "Discovery is scoped by reachability (F2 - 'visible = reachable'): an AUTHENTICATED caller sees only the agents its comm scope can reach (its own outbound AND each peer's inbound), plus always itself"; anônimo vê tudo (:559-560, e _filter_reachable :654-655 retorna sem filtrar quando caller_agent_id é vazio). agent_get :567-597: agente existente mas inalcançável é zerado (:586-590) e cai no mesmo raise NOT_FOUND "agent_id does not exist." (:591-596) — docstring :572-576 confirma "byte-identical to the non-existent case". A "dupla interseção" é confirmada no predicado compartilhado domain/tag_selector.py:354-380 (reachable = sender.outbound AND recipient.inbound, com self carve-out :370-375). capability_list também é escopado igual (identity.py:612-613, :620).

3) Docstrings inline já documentam — src/okto_nexus/adapters/inbound/mcp/tools/identity.py:307 ("Authenticated callers see only agents their comm scope can reach (plus themselves); anonymous callers see all"), :320 ("reads as NOT_FOUND, indistinguishable from a non-existent agent_id") e :330 (capability_list "agents scoped to your comm reach"). Assimetria inline-vs-resource confirmada.

4) "rev 14" — src/okto_nexus/adapters/inbound/mcp/server.py:178-188: a revisão 14 do changelog é exatamente "tag scoping F2 (inbound + 'visible = reachable')... Discovery is scoped: agent_list/capability_list list only agents REACHABLE from the caller (anonymous callers see all); agent_get of an unreachable agent reads as NOT_FOUND". Esse texto é comentário de código, não superfície agent-facing — não supre a lacuna do resource.

5) A recomendação não quebra nada: (a) bump de versão é a prática documentada — resources.py:39 "version is per-resource (bump on content change)", e nexus_info expõe resource_versions p/ stale-cache (server.py rev 12, :167-168); (b) paridade stdio/http intacta — resources registram no mesmo FastMCP compartilhado pelos dois transportes e test_http_parity cobre a superfície de TOOLS, não corpo de resource; (c) gate S7 "harness sem resources" intacto — a informação já vive nas docstrings inline (tools/identity.py:307/320/330), a recomendação só ADICIONA ao resource, não move nada para fora do inline; (d) lock "assertividade > tokens" — uma frase a mais num resource lido sob demanda (não residente) é custo desprezível e ganho direto de assertividade. A recomendação incluir capability_list no bloco é correta: o bloco do resource (:402-408) também omite o scoping que o inline :330 e identity.py:612-613 documentam.

Claim exata em todos os pontos: severidade media (gap de doc, sem bug de runtime) é proporcional. Veredito: CONFIRMADO.

</details>

### 12. tool-docs/artifacts não menciona a leitura audience-scoped do artifact_get (rev 25) — o resource sabe menos que o docstring inline

**Severidade:** media · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** tooldocs-vs-code · id `artifacts-audience-read-omitido`

**Problema.** O resource tool-docs/artifacts (v1) descreve artifact_get apenas como 'Retrieve an artifact by id within the workspace resolved from project_root', omitindo que desde a rev 25 a leitura é filtrada pela audience congelada do artifact (leitor fora da audience recebe NOT_FOUND indistinguível de id inexistente, AC8). O docstring inline documenta isso, invertendo o design lock (profundidade deveria estar no resource, não só inline).

**Evidência.** resources_docs.py:466-467 '# artifact_get\nRetrieve an artifact by id within the workspace resolved from project_root.' vs tools/artifacts.py:135 'Reads are audience-scoped: a caller outside the frozen audience gets NOT_FOUND (indistinguishable from a missing id).' e server.py:354-356 (rev 25: '``artifact_get`` now captures the caller and filters by the artifact's frozen audience').

**Recomendação.** Acrescentar ao resource: 'Reads are audience-scoped: the publisher's effective outbound audience is frozen onto the artifact at artifact_put; a reader outside it gets NOT_FOUND, indistinguishable from a missing id. No audience (publisher without bindings) = public.' Bumpar artifacts para v2.

### 13. tool-docs/identity omite effective_policies/governance/communication do retorno do agent_whoami

**Severidade:** baixa · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** tooldocs-vs-code · id `identity-whoami-campos-rev25-26`

**Problema.** O resource tool-docs/identity (v3) lista o retorno do agent_whoami como 'agent_id, operator-assigned role, capabilities, metadata, permissions (null = unrestricted)', omitindo os blocos condicionais effective_policies + governance (rev 25) e communication (rev 26), que o docstring inline já anuncia e o código retorna quando o caller tem bindings.

**Evidência.** resources_docs.py:378-380 'agent_id, operator-assigned role, capabilities, metadata, permissions (null = unrestricted)' vs tools/identity.py:220 'permissions, effective_policies + governance, plus communication style when set' e :232-244 (data['effective_policies'] / data['governance'] / data['communication']).

**Recomendação.** No mesmo bump para v4 do achado identity-discovery-sem-reachability, acrescentar uma linha: 'When you have policy/communication bindings the profile also carries effective_policies (<policy_id>@<version> | inline), a governance rule list and a communication style block; all omitted otherwise.'

### 14. target-grammar: bullet de edge cases restringe a rejeição de broadcast-em-mixed a message_create, mas ela é universal

**Severidade:** baixa · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** tooldocs-vs-code · id `target-grammar-mixed-broadcast-escopo`

**Problema.** Na seção 'Rules and edge cases' o target-grammar v4 diz '``direct_with_fallback`` and a ``broadcast`` nested in ``mixed`` are rejected on message_create (VALIDATION_ERROR)', sugerindo por contraste que handoff_create aceitaria broadcast aninhado em mixed. A gramática compartilhada rejeita broadcast-em-mixed em AMBOS os tools (handoff_create valida pelo mesmo validate_target), e a própria seção 'Strategies' do resource (linha 86-87) já afirma a rejeição incondicional — as duas passagens do mesmo resource se contradizem no escopo.

**Evidência.** resources_docs.py:104-105 '``direct_with_fallback`` and a ``broadcast`` nested in ``mixed`` are rejected on message_create (VALIDATION_ERROR).' vs domain/targets.py:232-238 (rejeição no validador estrutural único: 'broadcast may not be nested inside a mixed target') e application/handoff.py:314 'normalized_target = validate_target(target)'; server.py:127-129 (rev 3: 'no null/broadcast sub-rules - everywhere').

**Recomendação.** Trocar o bullet por duas frases separadas: '``direct_with_fallback`` is rejected on message_create (handoff-only).' e 'A ``broadcast`` nested in ``mixed`` is rejected everywhere (both tools share the grammar).' Bump do target-grammar para v5 junto com qualquer outra edição.

### 15. Changelog rev 25 declara +233 chars no ledger policies_b3; o ledger real registra 127

**Severidade:** baixa · **Veredito:** CONFIRMADO · **Auditor:** inline-vs-code · id `changelog-policies-b3-mismatch`

**Problema.** O comentário da SURFACE_REVISION 25 em server.py afirma "Growth ledger: policies_b3 (+233 docstring chars)", mas APPROVED_GROWTH em surface_metrics.py registra "policies_b3": 127 — os dois números não podem ser ambos o custo medido; um auditor do budget que confie no changelog reconcilia errado o gate AC5.

**Evidência.** server.py:359 "Growth ledger: ``policies_b3`` (+233 docstring chars)." vs surface_metrics.py:77 '"policies_b3": 127'.

**Recomendação.** Corrigir o comentário do changelog para o valor efetivamente medido no ledger (127) — o ledger é a fonte que o gate cuttable_reduction_pct consome.

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri os dois arquivos e conferi as linhas exatas. (1) D:\Projetos\Techridy\okto_labs_okto_nexus\src\okto_nexus\adapters\inbound\mcp\server.py:359 diz literalmente "parity is unchanged. Growth ledger: ``policies_b3`` (+233 docstring chars)." no bloco do changelog da SURFACE_REVISION 25 (linhas 349-359). (2) D:\Projetos\Techridy\okto_labs_okto_nexus\src\okto_nexus\adapters\inbound\mcp\surface_metrics.py:77 registra "policies_b3": 127 em APPROVED_GROWTH, e o próprio comentário do ledger (linhas 71-76) decompõe o custo: agent_whoami +9 e artifact_get +118, soma exata 127 — o ledger é internamente consistente em 127, e o changelog atribui o +233 explicitamente AO ledger ("Growth ledger: ..."), então não há leitura em que ambos sejam o valor registrado. Tentei refutar via git: git log -L mostra que os dois números nasceram no MESMO commit (d7e3c78, landing da rev 25) e nunca mudaram — inconsistência desde a origem, não correção posterior. Premissa da recomendação confirmada: cuttable_reduction_pct (surface_metrics.py:127-137) desconta sum(APPROVED_GROWTH.values()), logo 127 é o que o gate AC5 consome; auditor que confiasse no changelog erraria a reconciliação em 106 chars. A correção recomendada é segura: edição de comentário apenas — nenhum teste trava o texto do changelog nem o valor de policies_b3 (grep em tests/ por "Growth ledger|policies_b3": zero hits; "233" no repo só aparece em logs de playwright, uv.lock e CSS; testes travam só SURFACE_REVISION == 30 e outras chaves do ledger), sem impacto no lock assertividade>tokens (nenhum char residente muda), na paridade stdio/http (nenhuma tool muda) nem no gate S7 (nenhum resource muda).

</details>

## Orçamento de tokens da superfície residente

Medição live da superfície default (proxy chars/4, o mesmo do baseline BR8): instructions 3.681 chars (−67% vs 11.206), docstrings 6.595 (−53% vs 13.983), **params 17.512 (+6,7% vs 16.406 — único componente acima do baseline pré-Frente-1)**; cuttable 27.788 (~6.947 tokens). Os cortes propostos abaixo somam ~−2.070 chars em params e ~−2.250 chars nos resources on-demand, sempre respeitando o lock *assertividade > economia*.

### 16. Gate de 40% desconta memory_i6 (2.388 chars) que não está na superfície default

**Severidade:** alta · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `metrics-phantom-memory-discount`

**Problema.** cuttable_reduction_pct desconta a soma INTEGRAL de APPROVED_GROWTH (5.484), incluindo memory_i6=2388, mas desde a revision 29 os tools memory_* não são registrados com feature_memory=false — e o teste do gate constrói o servidor default (flag OFF). A redução reportada é 46,38%, mas a honesta (sem o desconto fantasma) é 40,63%: a folga real até romper o gate é ~265 chars, não ~2.653.

**Evidência.** surface_metrics.py:61-64 ('Revision 29 made this experimental at registration time, so the default surface no longer carries this cost') + :136-137 ('approved = sum(APPROVED_GROWTH.values())'); tests/test_frente1_measurement.py:44 ('bootstrap({"OKTO_NEXUS_HOME"...}, [])' — sem feature_memory). Medição live: cuttable=27788, baseline=41595.

**Recomendação.** Condicionar o desconto à presença real: em cuttable_reduction_pct (ou no teste), subtrair memory_i6 apenas quando os tools memory_* estiverem na lista medida (measure_resident_surface já tem os nomes). Alternativa: dividir APPROVED_GROWTH em {base, experimental} e o gate default usar só base.

**Δ tokens.** 0 chars cortados; protege ~2.388 chars (~600 tokens) de crescimento fantasma que o gate hoje deixaria passar

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei cada elo da claim nos arquivos e reproduzi a medição live. (1) Desconto integral: src/okto_nexus/adapters/inbound/mcp/surface_metrics.py:136-137 faz `approved = sum(APPROVED_GROWTH.values())` sem condicionar à presença dos tools; memory_i6=2388 está no ledger (surface_metrics.py:65) e a soma é 5.484. (2) Revision 29: server.py:381-385 documenta que com feature_memory=false os memory_* "are not registered or advertised at all"; o mecanismo é _EXPERIMENTAL_TOOL_MODULE_FLAGS (server.py:401-403) + o `continue` no loop de registro (server.py:642-645); config.py:187 confirma default False. (3) O teste do gate constrói o servidor default: tests/test_frente1_measurement.py:44 (`bootstrap({"OKTO_NEXUS_HOME": ...}, [])`, sem flag). (4) Medição live (script na venv do repo): flag OFF → cuttable=27788, zero tools memory_* na lista; cuttable_reduction_pct=46,378% ("46,38%" ✓); redução honesta descontando só 3.096 = 40,637% (o achado citou 40,63% — truncamento vs arredondamento, diferença de 0,007 p.p., irrelevante); folga até romper o gate: 2.653 chars com o desconto fantasma vs 265 chars sem ele — exatamente os números da claim. Flag ON → cuttable=30430 com os 3 memory_* (custo real atual 2.642 > ledger 2.388). A recomendação não quebra os locks: 0 chars de texto cortados (assertividade intacta), nenhum registro de tool alterado (paridade stdio/http de test_http_parity.py intacta), nenhum resource envolvido (gate S7 intacto). Ressalvas menores à recomendação (não à claim): measure_resident_surface retorna só agregados int — os nomes dos tools são listados internamente mas NÃO expostos no retorno, então implementar exige expor os nomes; e com desconto condicional um servidor flag-ON passaria o gate por apenas ~11 chars de folga (custo real 2.642 vs ledger 2.388).

</details>

### 17. Componente params (17.512 chars) já excede o baseline pré-Frente-1 (16.406); top-10 consumidores concentrados em handoff/message

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `params-component-above-baseline`

**Problema.** Medição live da superfície default: instructions 3.681 (-67% vs 11.206), docstrings 6.595 (-53% vs 13.983), params 17.512 (+6,7% vs 16.406) — todo o crescimento pós-Frente-1 aterrissou em params, e a redução global (cuttable 27.788, 6.947 tokens proxy) é sustentada apenas por instructions+docstrings. Top-10 consumidores (docstring+params): handoff_create 2.844, message_create 2.165, event_wait 1.239, handoff_verify 1.076, event_get 990, inbox_pull 902, agent_register 854, handoff_complete 837, handoff_reject 772, inbox_peek 767. Top params: handoff_create.target 1.077, message_create.target 916, agent_register.capabilities 377, verify_by 302, acceptance_criteria 267.

**Evidência.** surface_metrics.py:33-38 (BASELINE {instructions:11206, docstrings:13983, params:16406}); medição via measure_resident_surface no servidor real (.venv, bootstrap default): {instructions:3681, docstrings:6595, params:17512, cuttable:27788}.

**Recomendação.** Concentrar a próxima rodada de corte em params (achados target-cheatsheet, proot-sha256, handoff-session-secret e profile somam ~-2.070 chars, devolvendo o componente para ~15.4k, abaixo do baseline).

**Δ tokens.** diagnóstico; cortes propostos somam ~-2.070 chars (~517 tokens)

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Reproduzi tudo de forma independente, sem reutilizar o script do autor do achado. (1) Baseline: D:/Projetos/Techridy/okto_labs_okto_nexus/src/okto_nexus/adapters/inbound/mcp/surface_metrics.py:33-38 contém exatamente BASELINE {instructions: 11206, docstrings: 13983, params: 16406, cuttable: 41595}. (2) Medição live: escrevi meu próprio script (scratchpad/verify_measure.py) que faz bootstrap default (apenas OKTO_NEXUS_HOME em temp dir novo, sem flags herdadas do ambiente) via server.py:506 bootstrap + create_server, rodado com o .venv do repo; medi DUAS vezes — via measure_resident_surface (surface_metrics.py:95) e via recontagem manual sobre server.list_tools() — ambas deram instructions 3681 (-67,2%), docstrings 6595 (-52,8%), params 17512 (+6,7%), cuttable 27788, cuttable_tokens 6947, 43 tools. Todos batem com a claim. (3) Top-10 por docstring+params bate número a número: handoff_create 2844, message_create 2165, event_wait 1239, handoff_verify 1076, event_get 990, inbox_pull 902, agent_register 854, handoff_complete 837, handoff_reject 772, inbox_peek 767. (4) Top params bate: handoff_create.target 1077, message_create.target 916, agent_register.capabilities 377, handoff_create.verify_by 302, handoff_create.acceptance_criteria 267. (5) Aritmética da recomendação: 17512 - 2070 = 15442 ≈ 15,4k < 16406, consistente; 2070/4 ≈ 517 tokens confere. (6) Não quebra locks: tests/test_http_parity.py:44-47 compara description/inputSchema das superfícies stdio e HTTP geradas dos MESMOS módulos de tools, logo cortes em params preservam paridade; o gate S7/harness (tests/test_frente1_measurement.py:84-110) mede tarefas em harness vivo e não é afetado por um diagnóstico de priorização (este achado não move texto para resources por si; os cortes concretos são achados separados a validar individualmente contra o lock assertividade>tokens). Único arredondamento na claim: -67%/-53% vs -67,2%/-52,8% exatos — irrelevante.

</details>

### 18. Cheat-sheet inline de target ainda carrega ~391 chars de regras do rich-selector, 2x, duplicando o target-grammar resource

**Severidade:** media · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** token-budget · id `target-cheatsheet-rich-selector-dup`

**Problema.** handoff_create.target (1.077 chars) e message_create.target (916) são os 2 maiores parâmetros residentes; ambos embutem o fragmento idêntico de 391 chars com regras (absence trap NotIn/DoesNotExist, hierarquia '/' com 'ENG covers ENG/BACKEND not ENGX', exigência de catálogo) que o resource target-grammar já cobre quase verbatim — regras/edge-cases são profundidade segundo o próprio lock ('every strategy SHAPE stays inline... while the rules, examples and edge cases live in okto-nexus://reference/target-grammar').

**Correção do verificador.** handoff_create.target (1.077 chars) e message_create.target (916) são os 2 maiores parâmetros residentes da superfície MCP publicada (3º maior: agent_register.capabilities, 377); ambos embutem um fragmento byte-idêntico de 389 chars (não 391) com regras (absence trap NotIn/DoesNotExist, hierarquia '/' com 'ENG covers ENG/BACKEND not ENGX', exigência de catálogo) que o resource target-grammar (resources_docs.py:64-81) já cobre quase verbatim — regras/edge-cases são profundidade segundo o próprio lock inline ('every strategy SHAPE stays inline... while the rules, examples and edge cases live in okto-nexus://reference/target-grammar', messages.py:98-101). Nenhum gate codificado (S7 harness, compaction S2, tool_schemas, paridade stdio/http) exige essas regras inline; economia real com o replacement sugerido ≈ -498 chars (~125 tokens) residentes.

**Evidência.** messages.py:98-116 e handoff.py:88-104 (fragmento 'rich selector [...] operator-managed tag catalog)' = 391 chars medidos em cada) vs resources_docs.py:64-81 (mesmas regras no resource).

**Recomendação.** Manter todos os SHAPES inline (incl. a forma rich [{key,operator,values}]) e 1 caution curta; mover absence-trap, hierarquia e nota de catálogo só para o resource: ex. '...or rich [{"key":"<k>","operator":"In|NotIn|Exists|DoesNotExist","values":[...]}] (ANDed; absence/hierarchy rules: see target-grammar resource)'.

**Δ tokens.** ~-520 chars (~130 tokens) residentes (260 por tool)

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e medi tudo: (1) src/okto_nexus/adapters/inbound/mcp/tools/messages.py:88-116 — _P_TARGET_MSG tem exatamente 916 chars (medido via ast.literal_eval); comentário nas linhas 98-101 contém verbatim o lock citado ("every strategy SHAPE stays inline... while the rules, examples and edge cases live in okto-nexus://reference/target-grammar"). (2) src/okto_nexus/adapters/inbound/mcp/tools/handoff.py:88-104 — _P_TARGET_HANDOFF tem exatamente 1.077 chars. (3) O fragmento compartilhado ('rich selector [...] operator-managed tag catalog)') é byte-idêntico nos dois arquivos, mas mede 389 chars, NÃO 391 — este é o único erro factual do achado. (4) Superfície MCP viva (create_server + list_tools): handoff_create.target (1.077) e message_create.target (916) são de fato os 2 maiores parâmetros publicados; o 3º é agent_register.capabilities com 377. (5) resources_docs.py:64-81 cobre as mesmas regras quase verbatim: rich match-expression (64-69), ABSENCE TRAP NotIn/DoesNotExist + compose com Exists (70-73), HIERARCHY 'ENG covers ENG/BACKEND but never ENGX' (74-77), catálogo fail-closed (78-81) — duplicação real. (6) A recomendação NÃO quebra os gates: tests/test_frente1_harness.py (S7) exige apenas os shapes '"strategy":"direct"', '"strategy":"capability"', 'broadcast' inline; tests/test_frente1_compaction.py:107-135 exige shapes + ponteiro pro resource + direct_with_fallback só no handoff; tests/test_tool_schemas.py:65-99,144-161 exige enum 'one of:', cada nome de estratégia, 'raw JSON object' e o ponteiro — a recomendação preserva todos. O limite de 200 chars (compaction S2) aplica-se a descriptions de TOOL, não de parâmetro. Paridade stdio/http vale por construção (tests/test_http_parity.py:4 — mesmo create_server nos dois transportes). O lock 'assertividade de uso > economia de tokens' (resources.py:5, resources_docs.py:10-14) é operacionalizado pelo gate S7, que só exige shapes inline — e o próprio comentário do código já declara que regras/edge-cases pertencem ao resource, então mover o absence-trap/hierarquia/catálogo alinha o texto ao lock em vez de violá-lo. Ressalva menor (não-bloqueante): a nota de catálogo inline previne um VALIDATION_ERROR de primeira tentativa com tags não registradas em harness sem resources; o erro é fail-closed e autoexplicativo (lista os nomes não registrados), então a perda de assertividade é recuperável e não codificada em nenhum gate. Delta estimado com o replacement sugerido (~140 chars): ~2×249 ≈ -498 chars, compatível com o '~-520' do achado.

</details>

### 19. Mecânica 'workspace_id = sha256(realpath)' repetida em 18 parâmetros project_root

**Severidade:** media · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** token-budget · id `proot-sha256-tail-x18`

**Problema.** _P_ROOT (81 chars) aparece em 18 tools da superfície default (3 messages, 8 handoff, 3 events, 2 artifacts, 1 health, 1 identity) = 1.458 chars; o tail '; the server derives workspace_id = sha256(realpath).' (53 chars) é mecânica interna que não muda como chamar o tool — para chamar certo basta 'Absolute path to the project'.

**Correção do verificador.** _P_ROOT (81 chars exatos) aparece em 18 parâmetros project_root da superfície MCP default (3 messages, 8 handoff, 3 events, 2 artifacts, 1 health, 1 identity = workspace_resolve; os 3 de memory ficam fora pois feature_memory default=False não registra os tools) = 1.458 chars residentes; o tail '; the server derives workspace_id = sha256(realpath).' (53 chars) é mecânica interna do servidor que não muda como preencher o parâmetro. PORÉM, aplicando a recomendação como escrita (substituir nas outras 17 por 'Absolute path to the project (defines the workspace scope).', 59 chars), a economia residente é ~-374 chars (~-93 tokens no proxy chars/4), não ~-850 chars (~212 tokens); o delta de ~-850 só se realizaria removendo o tail sem texto substituto (17×53≈901 chars).

**Evidência.** messages.py:88-90, handoff.py:76-78, identity.py:66-68, events.py:54-56, artifacts.py:43-45, health.py:46-48 (cópias idênticas de 81 chars); medição live: 18 ocorrências de project_root com essa description.

**Recomendação.** Manter a derivação apenas em workspace_resolve.project_root (onde ela é o contrato) e no preflight resource; nas outras 17 usar 'Absolute path to the project (defines the workspace scope).'

**Δ tokens.** ~-850 chars (~212 tokens) residentes

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei todos os arquivos citados em D:/Projetos/Techridy/okto_labs_okto_nexus. (1) String e tamanhos: _P_ROOT tem exatamente 81 chars e o tail 53 chars (medido com len() em Python); cópias idênticas em src/okto_nexus/adapters/inbound/mcp/tools/messages.py:88-90, handoff.py:76-78, identity.py:66-68, events.py:54-56, artifacts.py:43-45, health.py:46-48 — todas as linhas de evidência conferem. (2) Contagem 18 na superfície default confirmada por grep de 'project_root: Annotated': messages 3 (243/278/292), handoff 8 (281/310/334/359/385/413/439/470), events 3 (112/139/153), artifacts 2 (110/132), health 1 (89), identity 1 (191 = workspace_resolve); os 3 usos extras em memory.py (159/194/208) ficam FORA do default porque feature_memory default é False (config.py:187) e o módulo memory é gateado no registro (server.py:401-403), i.e., os tools nem são publicados. 18×81=1.458 ✓. Todo project_root da superfície usa _P_ROOT (nenhuma description alternativa). (3) Recomendação não quebra nada: gate S7 (tests/test_frente1_harness.py:110-133) só exige description não-vazia + required em project_root, não pina o texto sha256 (grep em tests/ por sha256(realpath)/_P_ROOT = 0 hits); paridade stdio/http intacta (mesmo register() serve ambos, test_http_parity compara superfícies que mudariam identicamente); gate de budget (surface_metrics.py) mede crescimento — redução só ajuda o alvo ≥40%; lock 'assertividade > tokens' (resources.py:5) preservado pois o substituto mantém a dica de escopo e o contrato completo segue em workspace_resolve + resources_docs.py:374. (4) IMPRECISÃO: token_delta '~-850 chars (~212 tokens)' contradiz a própria recomendação — trocar 81 chars por 'Absolute path to the project (defines the workspace scope).' (59 chars) em 17 params economiza 17×22 = 374 chars (~93 tokens no proxy chars/4 do BR8, surface_metrics.py:27); ~-850 só valeria removendo o tail inteiro sem o parêntese substituto (17×53=901). Delta superestimado ~2,3×.

</details>

### 20. handoff._P_SESSION_SECRET (197 chars x5) viola o invariante 'one credential story bus-wide' declarado no próprio código

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `handoff-session-secret-wording`

**Problema.** inbox.py e handoff.py declaram em comentário que os verbos sensíveis 'share the trust wording... one credential story bus-wide', mas o _P_SESSION_SECRET do handoff tem 197 chars enquanto o do inbox tem 123 (messages 128) — 5 cópias longas em claim/complete/verify/reject/cancel = 985 chars onde 615 bastariam com o texto já usado pelo inbox.

**Evidência.** handoff.py:119-123 (197 chars) vs inbox.py:85 (123 chars); comentários handoff.py:113-114 e inbox.py:79-80; verificação por script: _P_SESSION_TRUST idêntico entre módulos, _P_SESSION_SECRET divergente.

**Recomendação.** Padronizar handoff._P_SESSION_SECRET para o texto do inbox ('session_secret from session_open for session_id (optional in open mode but VALIDATED if supplied; REQUIRED in strict mode).').

**Δ tokens.** ~-370 chars (~92 tokens) residentes

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei nos fontes (src/, não build/): (1) D:/Projetos/Techridy/okto_labs_okto_nexus/src/okto_nexus/adapters/inbound/mcp/tools/handoff.py:119-123 — _P_SESSION_SECRET medido por script AST = 197 chars exatos; (2) .../tools/inbox.py:85 = 123 chars; .../tools/messages.py:97 e .../tools/memory.py:77 = 128 chars ("for from_session_id"); (3) comentários "one credential story bus-wide" confirmados em handoff.py:113-114 e inbox.py:79-80; (4) _P_SESSION_TRUST idêntico entre handoff.py:115-118 e inbox.py:81-84 (124 chars ambos); (5) os 5 usos de _P_SESSION_SECRET em handoff.py (linhas 339/365/392/419/450) mapeados às funções handoff_claim/complete/verify/reject/cancel — 5x197=985 vs 5x123=615, delta 370 chars ~= 92 tokens pela heurística do próprio repo (cuttable_tokens = cuttable//4, tests/test_surface_metrics.py:42). Recomendação não quebra nada: o param do handoff chama-se session_id (handoff.py:337), então o texto do inbox ("for session_id") encaixa verbatim e preserva toda a semântica (optional em open / VALIDATED if supplied / REQUIRED em strict) — o lock "assertividade > tokens" já convive com essa redação nos verbos inbox; gate S7 (tests/test_frente1_harness.py) não asserta nada sobre "session" (grep vazio); paridade stdio/http preservada (mesma constante alimenta ambas as superfícies); gate S4 >=40% (tests/test_frente1_measurement.py:65) só melhora com a redução; nenhum teste trava o texto exato ("The session_secret returned"/"mismatch fails" não aparecem em asserções — só num docstring de tests/test_presence_trust.py:21). Ressalva menor que não invalida: o comentário do handoff lista 3 verbos (claim/complete/reject) enquanto a cópia longa aparece em 5 (verify/cancel vieram da spec I4), e messages/memory usam 128 chars por diferirem apenas no nome do parâmetro (from_session_id) — handoff segue sendo o único outlier real.

</details>

### 21. _P_PROFILE (163 chars) idêntico em 5 tools = 815 chars; enum mínimo bastaria

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `profile-param-dup-x5`

**Problema.** A description de profile repete em event_get, event_wait, inbox_pull, inbox_peek e inbox_history a explicação completa dos 3 perfis ('default=keep all fields minus dead ones; summary=minimal+follow_up; full=raw. Trims per-call tokens'); para chamar certo basta o enum + default — a semântica de cada perfil é profundidade.

**Evidência.** inbox.py:78 e events.py:72 (constantes idênticas de 163 chars); medição live: 5 ocorrências x163 = 815 chars.

**Recomendação.** Encurtar para 'Response size profile - one of: default, summary, full (optional; summary trims per-call tokens).' (~97 chars) e documentar o significado de cada perfil uma vez (tool-docs/events ou um parágrafo em tool-docs/inbox).

**Δ tokens.** ~-330 chars (~82 tokens) residentes

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e conferi tudo em primeira mão. (1) Constantes: src/okto_nexus/adapters/inbound/mcp/tools/events.py:72 e .../tools/inbox.py:78 definem _P_PROFILE byte-idêntico ("Response size profile: one of default/summary/full (optional; default=keep all fields minus dead ones; summary=minimal+follow_up; full=raw). Trims per-call tokens."), medido em exatamente 163 chars. (2) Usos: exatamente 5 sites em src/ — event_get (events.py:118), event_wait (events.py:160), inbox_pull (inbox.py:147), inbox_peek (inbox.py:216), inbox_history (inbox.py:246); 5x163=815 chars residentes (ocorrências em build/lib são artefato de build, não superfície viva). (3) "Basta enum+default": parse_profile em .../mcp/projection.py:98-114 — None/blank vira "default", vocabulário fechado (default,summary,full), valor inválido falha alto com VALIDATION_ERROR que já lista os suportados; a semântica de cada perfil vive na projeção e é profundidade, não pré-requisito de chamada. (4) Texto proposto mede exatamente 97 chars; delta (163-97)x5=330 chars ~82 tokens pelo próprio proxy do repo (chars/4, surface_metrics.py:26). Tentativas de refutação da recomendação falharam: o lock "assertividade > tokens"/gate S7 (tests/test_frente1_harness.py) cobre só as 6 tarefas canônicas e nenhum teste pina a descrição de profile (grep em tests/ zero hits); o gate S4 (tests/test_frente1_measurement.py:51) só impõe teto (>=40% de redução e < baseline) — encurtar ajuda; paridade stdio/http vem dos mesmos módulos tools/; o budget de descrição (tests/test_handoff_dependencies.py:1264-1268) cobre só handoff_create/_P_DEPENDS_ON; tool-docs (resources_docs.py) hoje NÃO documenta os perfis, então "documentar uma vez" adiciona sem duplicar. Caveats de implementação (não refutam): são DUAS constantes independentes — editar ambas (nada testa igualdade entre elas); pelo contrato S8 de stale-cache, mudança de superfície inline pede bump de SURFACE_REVISION (server.py:394, pinado ==30 em test_handoff_dependencies.py:1256) e bump da version string do resource tool-docs alterado.

</details>

### 22. Loop de recepção e receipts contados 3x entre resources: communication, tool-docs/inbox e tool-docs/messages

**Severidade:** media · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `communication-inbox-receipts-3x`

**Problema.** O resource communication dedica 691 chars ('YOUR INBOX') ao loop count→pull→ack e 870 chars ('DELIVERY & READ RECEIPTS') a receipts; tool-docs/inbox (2.231) re-explica o mesmo loop e os mesmos receipts por tool; tool-docs/messages '# message_create' (849) repete delivery-confirmation + receipts pela terceira vez. Três fontes para o mesmo contrato = 3x o custo on-demand e 3 pontos de drift (o drift do lease default já ocorreu em um deles).

**Evidência.** resources.py:193-218 (blocos de 691 e 870 chars medidos) vs resources_docs.py:158-202 (tool-docs/inbox) e :120-132 (message_create block, 849 chars).

**Recomendação.** communication mantém apenas a DECISÃO de canal (direct/handoff/broadcast) + 2 linhas de 'como você recebe' + ponteiro para tool-docs/inbox; mecânica de lanes/receipts vive só em tool-docs/inbox.

**Δ tokens.** ~-1.100 chars (~275 tokens) por leitura do resource communication; elimina drift triplo

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei todos os arquivos citados em D:/Projetos/Techridy/okto_labs_okto_nexus e medi os blocos via AST (ast.literal_eval dos kwargs de add_resource). (1) TAMANHOS: resources.py:193-203 bloco 'YOUR INBOX' = 689 chars crus / 691 com os \n\n separadores (bate com a claim); resources.py:205-218 bloco 'DELIVERY & READ RECEIPTS' = 869-870 chars; resources_docs.py:153-203 tool-docs/inbox = 2.208 chars crus = ~2.231 servidos (add_resource injeta frontmatter 'version:' — resources.py:65, confirmado por test_frente1_resources.py:140-145 que exige o frontmatter no corpo servido); resources_docs.py:121-132 bloco '# message_create' = 847-849 chars. Todas as medidas batem dentro da convenção de contagem (±1-2 chars de newline). (2) TRIPLICAÇÃO: o loop count→pull→ack + receipts (message.delivered no pull, message.read no ack, message.read_receipt no inbox do sender) está em resources.py:196-217, repetido por tool em resources_docs.py:159-202 (inbox_pull emite delivered :169; inbox_ack emite read + read_receipt :174-177), e delivery-confirmation (recipients/delivered_count) + message_status + receipt events pela 3a vez em resources_docs.py:122-128. (3) DRIFT DO LEASE: CONFIRMADO — resources_docs.py:168 diz 'default 120' mas config.py:24 define DEFAULT_INBOX_LEASE_TTL_SECONDS = 300 e a descrição inline do tool (tools/inbox.py:61-63) interpola a constante real via f-string; o drift já ocorreu (ironicamente no próprio tool-docs/inbox que a recomendação elege como fonte única — o fix deve corrigir 120→300). (4) RECOMENDAÇÃO SEGURA: gate S7 (tests/test_frente1_harness.py:10-14,110) lê SOMENTE list_tools(), nunca resources/read — encolher o resource não o afeta; o lock 'assertividade de uso > economia de tokens' (test_frente1_harness.py:4, resources.py:5) protege a superfície INLINE, intocada pela recomendação; os testes que pinam o loop count→pull→ack pinam as SERVER_INSTRUCTIONS inline e o ponteiro para okto-nexus://reference/communication (test_tools_surface.py:140-171), não o corpo do resource; paridade stdio/http é automática pois ambos registram do mesmo registry _RESOURCES (mcp/server.py:744 e http/app.py:300-317); nenhum teste pina o conteúdo do corpo de communication (test_frente1_resources.py só exige não-vazio + frontmatter). Condições ao aplicar: bump da version do resource (resources.py:39 — nexus_info expõe resource_versions para stale-cache, S8) e atualizar a description em resources.py:163 que hoje promete 'the inbox reception loop, and delivery/read receipts'.

</details>

### 23. monitoring re-explica event_get/event_wait/event_cursor que tool-docs/events já cobre (~700 chars de overlap)

**Severidade:** baixa · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `monitoring-events-docs-overlap`

**Problema.** A seção '# LISTENING FOR EVENTS' do monitoring (1.137 chars) descreve snapshot polling, long-poll com clamp de ceiling e o anchor de cursor — a mesma semântica de tool-docs/events (1.506 chars). O monitoring é o maior resource (9.316 chars; só os 2 pseudocódigos somam 3.891) e é lido por qualquer agente que monte listener.

**Evidência.** resources.py:227-242 (bloco de 1.137 chars medido) vs resources_docs.py:210-236 (tool-docs/events cobrindo os mesmos modos).

**Recomendação.** Reduzir a seção do monitoring à lista de 4 modos (1 linha cada) + 'semântica dos tools: tool-docs/events'; manter invariantes e pseudocódigo (profundidade legítima).

**Δ tokens.** ~-650 chars (~162 tokens) por leitura do monitoring

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Verifiquei tudo diretamente nos arquivos e por medição programática (importando o registro _RESOURCES de src/okto_nexus/adapters/inbound/mcp/resources.py):

NÚMEROS — todos batem exatamente:
(1) Seção '# LISTENING FOR EVENTS' = 1.137 chars, em resources.py:227-242 (o header seguinte '# MONITORING FROM A CAPABLE HARNESS' está na linha 244) — evidência citada correta.
(2) tool-docs/events = 1.506 chars (corpo servido com frontmatter; raw 1.484), definido em resources_docs.py:205-237 com corpo nas linhas 210-236 — evidência correta.
(3) monitoring = 9.316 chars, o MAIOR dos 12 resources (o segundo é tool-docs/handoff com 7.024).
(4) Os 2 pseudocódigos somam exatamente 3.891 chars (# REFERENCE MONITOR 2.390 em resources.py:296-343 + # EPT REMOTE POLLER 1.501 em resources.py:344-377).

OVERLAP SEMÂNTICO — real e em parte near-verbatim: as frases "NOT how you receive messages addressed to you - that is the inbox", "clamped to the server ceiling" e "then returns the page; loop on next_cursor" aparecem literalmente em AMBOS os corpos (resources.py:228-236 vs resources_docs.py:212-235). Snapshot polling (resources.py:231-232 vs resources_docs.py:218-222), long-poll com clamp (resources.py:233-236 vs resources_docs.py:230-236) e anchor de cursor (resources.py:229-230 vs resources_docs.py:224-228) estão duplicados. A claim enumera precisamente esses três itens como o overlap (não afirma que a seção inteira duplica — o bullet EPT, ~250 chars, não tem contraparte em tool-docs/events, o que é coerente com "~700 chars de overlap" de 1.137). E o clamp/anchor ainda é re-demonstrado dentro do próprio monitoring (comentário "25 <= ceiling 30s" em resources.py:316; "I4: anchor at now" em 308), reforçando que a redução não perde semântica.

A RECOMENDAÇÃO NÃO QUEBRA OS LOCKS:
- Lock "assertividade > tokens" (resources.py:3-16): governa o que fica INLINE (instructions + docstrings) vs. resource; deduplicar entre DOIS resources segue o precedente explícito do próprio repo — o resource target-grammar foi criado exatamente para eliminar ~1.000 chars duplicados entre message_create/handoff_create (resources_docs.py:12-14). O cross-reference já existe no sentido inverso: tool-docs/events aponta para reference/monitoring "for the listener patterns" (resources_docs.py:235-236); a recomendação fecha a divisão de responsabilidades (padrões em monitoring, semântica dos tools em events) sem circularidade.
- Paridade stdio/http: test_http_parity.py:56-67 só asserta que a URI okto-nexus://reference/monitoring existe nos dois transports — mudança de corpo não afeta.
- Gate S7 "harness sem resources": test_frente1_harness.py:163-172 (test_s7_td) asserta apenas a superfície INLINE de tools (event_cursor/event_wait com param stream descrito) — não toca corpo de resource.
- test_frente1_resources.py só verifica set fechado de 12 URIs, corpo não-vazio e frontmatter "version:" — nenhum teste asserta o conteúdo da seção LISTENING.

Única ressalva de implementação (não invalida a claim): ao editar, bumpar version do monitoring ("4"→"5") por convenção de stale-cache (resources.py:16 "bump on every change").

</details>

### 24. Regra 'verbo autenticado avança o heartbeat; session_heartbeat só quando idle' dita em 4 lugares

**Severidade:** baixa · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** token-budget · id `heartbeat-guidance-4x`

**Problema.** A mesma orientação de presença aparece em SERVER_INSTRUCTIONS passo 2 (~280 chars), no preflight resource passo 2 (verbatim, verificado por script: 'advances your heartbeat, so working keeps you present' presente nos dois), em tool-docs/identity '# session_open' (bloco de 733 chars) e '# session_heartbeat' (335 chars). O preflight resource (2.133 chars) repete o inline quase 1:1 em vez de só aprofundar.

**Correção do verificador.** A regra 'verbo autenticado avança o heartbeat; session_heartbeat explícito só quando idle' é ditada em 4 lugares: SERVER_INSTRUCTIONS passo 2 (server.py:108; passo de 386 chars, sentença de heartbeat de 248 chars, contendo a frase 'advances your heartbeat, so working keeps you present'), preflight resource passo 2-PRESENCE (resources.py:134-142; variante QUASE-idêntica, não verbatim — 'each one advances your heartbeat, so working (receiving, sending, claiming) keeps you present'), tool-docs/identity '# session_open' (resources_docs.py:410-420, bloco de 731 chars) e '# session_heartbeat' (resources_docs.py:422-426, bloco de 333 chars). O preflight resource (2.133 chars) duplica a sentença de heartbeat do inline quase 1:1, embora seu passo 2 também acrescente deltas (consequência de exclusão da audiência de broadcast e a nota self-only de session_open). A recomendação (inline mantém 1 frase; profundidade só em tool-docs/identity; preflight vira delta + ponteiros) é segura: nenhum teste pina o texto dos bodies, a paridade stdio/http compara só URIs (test_http_parity.py) e o gate S7 lê apenas a superfície inline (test_frente1_harness.py); requer apenas bump do campo version dos resources editados.

**Evidência.** server.py:108 vs resources.py:134-142 (frase idêntica confirmada por script) vs resources_docs.py:410-420 e :422-427 (blocos medidos 733/335 chars).

**Recomendação.** Inline mantém 1 frase (lock); a profundidade de presença fica SÓ em tool-docs/identity; preflight resource passa a conter apenas o delta (erros comuns, permissões) + ponteiros.

**Δ tokens.** ~-500 chars (~125 tokens) somados nos resources preflight/identity

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri e medi por script (Python importando os módulos reais): (1) D:/Projetos/Techridy/okto_labs_okto_nexus/src/okto_nexus/adapters/inbound/mcp/server.py:108 — passo 2 do PRE-FLIGHT contém a frase exata 'advances your heartbeat, so working keeps you present ... reserve an explicit session_heartbeat for IDLE turns'; o passo 2 mede 386 chars (sentença de heartbeat isolada: 248), não ~280. (2) src/okto_nexus/adapters/inbound/mcp/resources.py:134-142 — passo '2. PRESENCE' do preflight repete a orientação, MAS a alegação de verbatim é FALSA: `'advances your heartbeat, so working keeps you present' in body == False` — o texto real é 'each one advances your heartbeat, so working (receiving, sending, claiming) keeps you present' (parêntese inserido, 'each one', pontuação diferente). Body total do preflight = 2133 chars (bate exato). (3) src/okto_nexus/adapters/inbound/mcp/resources_docs.py:410-420 ('# session_open', medido 731 chars vs 733 alegados) e :422-426 ('# session_heartbeat', 333 vs 335) — ambos repetem a mesma regra em paráfrase; confirmado. (4) 'Repete quase 1:1 em vez de só aprofundar' é meia-verdade: o passo 2 do preflight (619 chars) duplica a sentença quase 1:1 mas também adiciona deltas (consequência de broadcast-audience, nota self-only). Recomendação verificada como segura: tests/test_tools_surface.py:138 só compara identidade de SERVER_INSTRUCTIONS; tests/test_http_parity.py:53-68 compara apenas conjuntos de URIs (resources compartilhados via resources.py — paridade preservada); gate S7 (tests/test_frente1_harness.py:110) lê só list_tools(), e o inline mantém a frase; grep por 'keeps you present'/'IDLE turns' em tests/ = zero (nenhum teste pina os bodies). Cuidado menor: bump do campo version dos resources alterados.

</details>

### 25. tool-docs/artifacts (601 chars) é órfão e ~100% redundante com os params inline de artifact_put

**Severidade:** baixa · **Veredito:** CONFIRMADO · **Auditor:** token-budget · id `artifacts-resource-orphan-redundant`

**Problema.** Nenhum docstring aponta para tool-docs/artifacts, e todo o seu conteúdo (path OR content required, dentro do workspace root, max_inline_bytes, json well-formed, enum de tipos) já está nos 650 chars de params inline de artifact_put — o resource não carrega profundidade adicional além do nome do evento emitido.

**Evidência.** resources_docs.py:451-467 (body de 601 chars) vs artifacts.py:46-51 (_P_ARTIFACT_TYPE 164 + _P_PATH 170 + _P_CONTENT 123 cobrindo os mesmos fatos) e :117,:135 (docstrings sem ponteiro).

**Recomendação.** Opção A (preferida, mantém BR9 12 URIs): encurtar _P_PATH/_P_CONTENT/_P_ARTIFACT_TYPE para o mínimo (~-250 chars residentes) e adicionar 'Docs: okto-nexus://reference/tool-docs/artifacts.' no artifact_put. Opção B: aposentar o resource (exige revisar o closed set BR9).

**Δ tokens.** ~-250 chars (~62 tokens) residentes na opção A

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri os arquivos em D:\Projetos\Techridy\okto_labs_okto_nexus (src/, não build/) e tentei refutar cada fato; todos resistiram.

(1) 601 chars — EXATO. O literal do body em src/okto_nexus/adapters/inbound/mcp/resources_docs.py:451-468 tem 578 chars, mas o resource é servido com frontmatter `---\nversion: "1"\n---\n\n` (resources.py:33-35,65); importei o módulo e medi o body registrado: exatamente 601 chars.

(2) Redundância ~100% — CONFIRMADA por comparação fato a fato. Cada fato do resource existe quase verbatim inline em tools/artifacts.py: "path OR content - at least one REQUIRED" em _P_PATH (linha 48, 170 chars) e _P_CONTENT (linha 49, 123 chars); "must stay within the workspace root; only path + metadata stored, never bytes" em _P_PATH; "bounded by max_inline_bytes; json must be well-formed" em _P_CONTENT; enum "one of: file, text, json, markdown" + "inline-vs-reference is decided by content-vs-path" em _P_ARTIFACT_TYPE (linha 46, 164 chars — as três contagens do achado batem exatas); a frase de abertura é o próprio docstring de artifact_put (linha 117). O único fato exclusivo do resource é "Emits ``artifact.created``" (resources_docs.py:463-464) — exatamente a exceção que o claim já concede. Para artifact_get o resource carrega MENOS que o inline (o docstring da linha 135 adiciona o comportamento audience-scoped NOT_FOUND, ausente no resource). Soma dos 6 params de artifact_put = 654 chars (~"650" do claim).

(3) Órfão — CONFIRMADO no sentido definido pelo claim: grep por "tool-docs/artifacts" no repo só encontra a registração (resources_docs.py:452) e os closed-sets de teste (tests/test_frente1_resources.py:49, tests/test_frente1_harness.py:102). Nenhum docstring aponta (artifacts.py:117 e :135 verificados), em contraste com o padrão da casa: messages.py:259, inbox.py:174/:262, handoff.py:292/:474, identity.py:207/:220 têm "Docs:/Full docs: okto-nexus://reference/tool-docs/...".

(4) A RECOMENDAÇÃO não quebra os travamentos verificados: (a) BR9 = closed set de EXATAMENTE 12 URIs, travado em test_frente1_resources.py:36-52 e test_frente1_harness.py:92-105 — Opção A preserva; Opção B de fato exigiria revisar os dois testes + resources_docs.py:20, como o achado avisa. (b) Lock "assertividade de uso > economia de tokens" (resources.py:3-16): permite explicitamente mover profundidade mantendo inline name/type/required/minimal-enum — o encurtamento é compatível desde que "path OR content, at least one REQUIRED" e o enum fiquem inline; há precedente direto: max_inline_bytes só aparece inline em artifacts (_P_CONTENT) — messages/handoff/identity já moveram esse limite para resources. (c) Gate S7 "harness sem resources" (test_frente1_harness.py): grep confirma ZERO asserções sobre params de artifact_* — nada quebra. (d) Paridade stdio/http: as descrições vêm de um único módulo (tools/artifacts.py) consumido por ambos os transportes; test_http_parity não é afetado. Ressalva menor, não-refutante: o delta líquido da Opção A é ~-200 chars (não -250), pois o ponteiro "Docs: okto-nexus://reference/tool-docs/artifacts." adiciona ~49 chars — mas o achado usa "~", e o gate de surface_metrics.py mede redução (só crescimento não-ledgered dispara), então segue verde.

</details>

### 26. agent_register.capabilities (377 chars) embute mecânica de operador que já vive em tool-docs/identity

**Severidade:** baixa · **Veredito:** PARCIAL (correção registrada abaixo) · **Auditor:** token-budget · id `capabilities-param-operator-mechanics`

**Problema.** O trecho 'operators register names on the dashboard Registry or POST /api/v1/capabilities' (~85 chars) descreve o fluxo do OPERADOR, irrelevante para o agente chamar agent_register certo (ele só precisa saber: nomes devem existir no catálogo; descubra com capability_list); o mesmo conteúdo já está no resource tool-docs/identity.

**Correção do verificador.** O trecho 'operators register names on the dashboard Registry or POST /api/v1/capabilities' (79 chars) em _P_CAPABILITIES (identity.py:72-79, exatamente 377 chars, usado só por agent_register linha 204) descreve fluxo do OPERADOR, não-acionável pelo agente; o mesmo conteúdo já vive no resource tool-docs/identity (resources_docs.py:393-394) E na mensagem de erro runtime (application/capabilities.py:130-133), que o entrega exatamente quando é acionável. A recomendação é segura (nenhum teste asserta o texto; paridade stdio/http preservada pela constante compartilhada; gate S7 coberto pelo erro runtime e pela menção a capability_list que permanece), mas o corte real com o texto recomendado é ~-71 chars (~18 tokens) residentes, não ~-110 chars (~27 tokens).

**Evidência.** identity.py:72-79 (_P_CAPABILITIES, 377 chars) vs resources_docs.py:391-396 ('dashboard Registry or POST /api/v1/capabilities' no resource).

**Recomendação.** Cortar para: '...FAIL-CLOSED: every name must already exist in the central capability catalog (discover with capability_list).'

**Δ tokens.** ~-110 chars (~27 tokens) residentes

<details><summary>Verificação (o que o cético abriu e viu)</summary>

Abri src/okto_nexus/adapters/inbound/mcp/tools/identity.py:72-79 — _P_CAPABILITIES existe, tem exatamente 377 chars (contado via Python), contém o trecho de operador (79 chars, não ~85) e é usado apenas por agent_register (linha 204). Abri src/okto_nexus/adapters/inbound/mcp/resources_docs.py — o texto duplicado está na linha 394, dentro do add_resource(slug="tool-docs/identity") declarado nas linhas 363-364; evidência confere. Verificação adicional: src/okto_nexus/application/capabilities.py:128-135 mostra que a mensagem de erro VALIDATION_ERROR já entrega a mecânica de operador ("dashboard Registry or POST /api/v1/capabilities") em runtime — o conteúdo é triplicado, e o gate S7 (harness sem resources) fica coberto pelo erro no momento acionável. Grep em tests/ por "operators register|dashboard Registry|central capability catalog": zero matches, nenhum teste asserta o texto. Paridade stdio/http preservada: a constante é compartilhada pelo mesmo módulo auto-registrado nos dois transportes. Única imprecisão: aplicando o texto exato da recomendação, o delta real é -71 chars (~18 tokens), não ~-110 chars (~27 tokens) — superestimado em ~55%.

</details>

### 27. Ponteiros 'Full docs: okto-nexus://...' presentes em só 8 de 35 tools; tool-docs/events e tool-docs/artifacts não são referenciados por nenhum

**Severidade:** media · **Veredito:** NÃO-VERIFICADO (verificador caiu por limite de sessão — conferir evidência antes de agir) · **Auditor:** token-budget · id `docs-pointers-inconsistent`

**Problema.** Somente message_create, inbox_ack, message_status, handoff_create, handoff_get, agent_register, agent_whoami e event_wait (→monitoring) apontam para resources; nenhuma superfície inline referencia tool-docs/events nem tool-docs/artifacts (descoberta só via resources/list). event_wait ainda aponta para monitoring 2x no mesmo tool (docstring + _P_TIMEOUT). O prefixo também varia ('Full docs:' vs 'Docs:' vs 'Patterns:').

**Evidência.** events.py:120 (event_get sem ponteiro) e :162 ('Patterns: okto-nexus://reference/monitoring.') + :67-71 (_P_TIMEOUT repete 'Listener patterns: okto-nexus://reference/monitoring'); artifacts.py:117,135 (sem ponteiro) vs resources_docs.py:451-467 (resource existente).

**Recomendação.** Padronizar 'Docs: okto-nexus://reference/tool-docs/<d>.' em UM tool de entrada por família (event_get→tool-docs/events, artifact_put→tool-docs/artifacts, inbox_pull→tool-docs/inbox, handoff_claim→tool-docs/handoff) e remover o ponteiro duplicado do _P_TIMEOUT de event_wait.

**Δ tokens.** ~+180 chars nos 4 ponteiros novos, -54 do duplicado; custo líquido ~+126 chars justificado pelo lock (assertividade/descoberta primeiro)

---

# Plano de correção sugerido (triagem)

Em ordem de custo-benefício; itens 1-3 são mecânicos e sem risco de regressão de comportamento:

1. **Fixes de exatidão nos resources + bump de `version`** (achados 1, 4, 6-15): corrigir a
   chamada do `event_cursor` no pre-flight (inline + resource), reescrever o resource
   `governance` (v2) e o `hitl` (v2) para o modelo binding-driven pós-rev-25, corrigir lease
   default 120→300 (idealmente interpolando a constante como o inline já faz), adicionar
   `trace_id` às filter keys, reachability no tool-docs/identity, audience-scoped read no
   tool-docs/artifacts. Todo fix de resource exige bump da `version` — e vale considerar um
   teste que falhe quando um número documentado divergir da constante de config (a classe
   lease-120 de drift).
2. **Fix do gate de 40%** (achado 16): condicionar o desconto de `memory_i6` à presença real dos
   tools memory_* na superfície medida (ou dividir APPROVED_GROWTH em {base, experimental}).
   Protege ~2.388 chars de crescimento fantasma; a folga honesta do gate hoje é ~265 chars.
3. **Rodada de corte em params** (achados 18-21, ~−2.070 chars): devolve o componente params
   (17.512) para ~15.4k, abaixo do baseline pré-Frente-1 (16.406).
4. **Consolidação dos resources** (achados 22-27, ~−2.250 chars on-demand + fim do drift triplo
   do loop de recepção): communication mantém só a decisão de canal; mecânica de lanes/receipts
   vive só em tool-docs/inbox; monitoring aponta para tool-docs/events; padronizar os ponteiros
   `Docs: okto-nexus://reference/...` (um por família de tools).
5. **Spec do aspecto 1** (Parte 1): inbox_wait com semântica de delta; ack-no-próximo-pull
   opt-in amarrado a sessão + flush no session_close + nack; last_served no row do token EPT;
   `parked` no retorno de inbox_count.

## Proveniência

Gerado a partir do workflow `wf_2f982d83-24a` (2026-07-12, 37 agentes, ~2,59M tokens; 3 auditores
+ 1 arquiteto + 1 crítico + 26 verificadores céticos; 32 achados, 0 refutados, 6 não-verificados).
Dados brutos (JSON estruturado por achado, com veredito e raciocínio de verificação): sessão
Claude Code `769fbe42`, scratchpad `aspect1.json` / `aspect2.json`.
