# Results: mapa de prova e contrato proposto — HST-002/003

Inspeção somente leitura em 2026-11-17, checkout observado `b2436d3b00e402d01ebbc70c36cb5d4fdc37a4d8`. O pacote normativo é `C:/Users/jpamb/Downloads/NEXUS_HOME_ESTADOS_R1_PACOTE_CODEX`, especialmente §§6 e 8, HST-011–017, requisitos R09–R12/R15–R20 e cenários D/E/I. O SHA de referência do plano não foi restaurado. Este documento propõe o contrato para G0; não declara implementação, testes executados, browser, AT ou harness real.

Foram lidos o prompt, requisitos/tarefas do ledger, especificação pertinente e fontes abaixo. A instrução RTK e CONTRIBUTING foram consultadas. Nenhuma alteração de produto, testes, banco, instalação, protocolo, Core/Connector ou ledger foi feita nesta auditoria.

## 1. Conclusão para G0

1. Results já possui provas distintas de encerramento de turno, handoff e reporte externo. Elas devem alimentar dimensões diferentes, sem converter `SUCCEEDED` em tarefa concluída ou `COMPLETED` em verificação aprovada.
2. `verification_state` atual não é um verdict: SQL projeta `handoffs.status` ou `historical_claim`. Nenhum consumidor deve interpretá-lo como selo de QA.
3. Há verificação canônica real no Server: `HandoffService.handoff_verify`. Sua autoridade, CAS e anti-autoverificação devem ser reutilizados. **A prova positiva futura é implementável com extensão aditiva dos eventos existentes**, sem novo workflow/tabela e sem Core/Connector. Falta hoje a ligação explícita evento → claim/versão da entrega verificada.
4. O caminho sem runtime nativo só gera Results para handoffs `COMPLETED`/`REJECTED`; uma entrega em `VERIFYING` sem turno nativo não aparece nessa consulta. É uma lacuna concreta para E03, distinta da existência de Attention de verificação.
5. O contrato novo deve separar outcome produtivo, estado atual da tarefa, verificação, limpeza e conteúdo. Históricos sem prova suficiente continuam `unknown`; não devem receber retroativamente um selo.

## 2. Relação existente e identidade

`src/okto_nexus/adapters/outbound/sqlite/home.py:115–178` define `RESULTS`:

- `execution_operations.action='turn.submit'` mais a última revisão de `execution_receipts`, apenas estágios `SUCCEEDED`, `FAILED` ou `CANCELLED` (128–141). Abertura/fechamento de sessão, silêncio e texto livre não satisfazem esse predicado. `OUTCOME_UNKNOWN` não cria uma entrega concluída.
- Associação persistida por `execution_domain_deliveries` **e** `execution_delivery_attempt_history` → `runtime_handoff_bindings` → handoff de **workspace exato**. O histórico não é ligado por nome, família ou sessão mais recente.
- Identidade lógica: handoff/claim quando existe associação; caso contrário server/executor/operation. Há uma linha representativa por `result_group,workspace_id`, escolhida por `received_at,operation_id`. Operações de um mesmo claim não são entregas adicionais no contrato atual.
- Artefatos são agregados **antes** de escolher essa linha, por resultado/claim/workspace e vínculos persistidos `runtime_results.canonical_*` → `artifacts`. Não mudar isso para coletar só a operação mais recente ou para agrupar nomes de arquivos.
- Fallback de handoff terminal é omitido quando já existe resultado nativo do mesmo handoff/claim. Assim a transição de estado pode atualizar a mesma entrega sem duplicá-la.

`result_item` (182–203) publica ID estável, `source_ref.revision=digest(facts)`, alvo exato e ocorrência de visto. `claim_epoch`, `stream_epoch`, sequência terminal e revisão do recibo participam dos fatos/revisões, mas não são publicados como um contrato semântico explícito de entrega. A nova apresentação precisa transportar a referência pertinente, não decifrar IDs opacos.

**Limite importante:** uma operação histórica de claim anterior pode continuar em Results. Ela não conclui o claim atual. Um work compartilhado pode ter múltiplas conexões provadas; isso não permite selecionar uma execução sucessora por agente ou pelo ID público do harness.

## 3. Matriz de fatos e mensagens

| Fato/fonte autorizada | O que comprova | Representação proposta | O que permanece separado |
|---|---|---|---|
| Último recibo `turn.submit=SUCCEEDED`, sem handoff | Turno produtivo encerrado com sucesso | `scope=turn`, outcome succeeded; “Turn completed/Response available” conforme captura | `task_state=not_applicable`, verification not_applicable; não inventar tarefa pendente |
| Mesmo recibo associado ao claim atual OPEN/CLAIMED | Fim do turno daquele claim | Resultado do turno disponível; tarefa ainda aberta/claimed | Não concluir handoff, não marcar verificado |
| Handoff atual `VERIFYING` com entrega persistida | Entrega submetida ao workflow de verificação existente | `task_state=verifying`, verification pending | Só operador elegível recebe ação `verify_handoff`; atribuição não prova pausa do harness |
| Handoff `COMPLETED`, sem prova específica de verdict | Conclusão da tarefa/claim | `scope=handoff`, tarefa concluída | `verification=unknown`, ou not_applicable apenas com contrato sem critérios comprovado; sem selo approved |
| Evento futuro de `handoff_verify(pass)` com claim e revisão exatos | Aceite canônico da mesma entrega | verification approved + referência auditável; tarefa concluída | Não é aprovação de ferramenta nem evidência de sucesso de outro turno |
| `handoff_verify(fail)` | Rejeição da entrega que estava em VERIFYING | verification rejected da entrega referida; “Delivery not approved” | Serviço retorna tarefa a CLAIMED e incrementa epoch; mostrar estado atual real, não dizer runtime CANCELLED |
| Recibo produtivo `FAILED` | Execução encerrada com falha | execution_outcome failed | Preservar saída parcial/artefatos; sem retry genérico |
| Recibo produtivo `CANCELLED` | Cancelamento confirmado daquele turno | execution_outcome cancelled | Não apagar resultado parcial; não inferir rejeição do handoff |
| Handoff `REJECTED` | Rejeição canônica da tarefa/entrega | scope handoff, task_state rejected | Não mapear para sucesso ou cancelamento nativo; não equivale automaticamente a verificação negativa |
| Containment `REQUESTED` da sessão/generation pertinente | Limpeza ainda solicitada | cleanup pending, outcome produtivo preservado | Não reexecutar trabalho para resolver limpeza |
| Containment `RELEASED` com prova canônica pertinente | Liberação daquele containment | cleanup complete somente nesse escopo | Ausência de linha não prova cleanup complete; caso sem cleanup aplicável é distinto de fonte indisponível |
| Recibo terminal, captura ausente/não publicada | Término confirmado, conteúdo ainda não comprovado disponível | content pending/not_captured/unavailable segundo prova de captura | `preview=null` sozinho não decide: texto pode ser vazio, artefato pode existir ou cobertura faltar |
| `external_completion_unseen` de `observation.completion` | Reporte explícito de término e sua proveniência | scope external_report, evidence reported, “Completion reported / Not verified by Nexus” | Não converte runtime, claim, grant ou tarefa para sucesso |
| Resultado de claim anterior | Fato histórico confirmado daquele episódio | historical=true, claim/ref originais | Verificação atual não é herdada, e unknown posterior não apaga esse histórico |
| OUTCOME_UNKNOWN sem terminal | Incerteza de execução | Permanece contexto/Attention autorizada | Não criar resultado concluído nem novo turno/replay |

Há ainda um detalhe a corrigir na projeção nova: `CASE WHEN claim_epoch=current_epoch ... ELSE 'historical_claim'` (home.py:164) também cai no ELSE quando não existe handoff, pois NULL=NULL não é true em SQL. Portanto a semântica de turno independente deve explicitamente ser não aplicável à tarefa; não tomar esse string legado como prova de histórico.

## 4. Origem real da verificação e lacuna de vínculo

### Autoridade existente

`application/handoff.py:HandoffService.handoff_complete` (1293–1379) consulta `read_verification`; critérios presentes levam CLAIMED→VERIFYING, sem critérios levam CLAIMED→COMPLETED. O evento `handoff.verification_requested` é metadata-only, e a entrega é lida pelo caminho autorizado de handoff. Isso não cria motor QA novo.

`HandoffService.handoff_verify` (1391 em diante) exige ator real, permissão `handoffs/work`, visibilidade do handoff, estado VERIFYING, anti-autoverificação, elegibilidade dinâmica do `verify_by` e claim atual. `SqliteHandoffRepo.transition_verifying` (490–537) revalida workspace/status/epoch na atualização condicional:

- pass → COMPLETED; evento **existente** `handoff.completed` contém `verified_by`;
- fail → CLAIMED, feedback/lease atualizados, **claim_epoch incrementado**; evento existente `handoff.verification_failed`.

Migration018 guarda acceptance_criteria, verify_by e **apenas último feedback negativo**. Não guarda verdict positivo/verifier por entrega. Não foi encontrado produtor canônico independente chamado review_task/verification_receipt no domínio/SQLite; um task com título “review” não é prova de verificação. `tasks.status` também não substitui a decisão.

### O que falta hoje

Os payloads em `handoff_complete` (1357–1366) e `handoff_verify` (1508–1521,1553–1567) não carregam claim_epoch nem revisão da entrega. `_emit` (3118–3155) acrescenta trace_id, não esse vínculo. O evento pass com verified_by demonstra que houve um aceite, mas **não deve ser associado a qualquer entrega atual só pelo handoff_id ou timestamp**. Feedback isolado pode sobreviver à aprovação posterior. Histórico/retention ou emissor opcional indisponível também impedem prova completa.

### Extensão mínima concreta — somente Server

Implementar em `application/handoff.py:HandoffService.handoff_verify`, depois de `_require_claim_epoch` e de `read_outcome`, **antes** de chamar `transition_verifying`:

1. Capturar `verified_claim_epoch = handoff.claim_epoch` da linha autorizada, nunca do valor opcional do argumento nem de `updated.claim_epoch` após fail.
2. Construir uma referência da entrega persistida: workspace_id + handoff_id + epoch verificado + revisão determinística do **resultado persistido lido nessa UoW**. Proposta: hash versionado do JSON canônico `[workspace_id,handoff_id,verified_claim_epoch,outcome.result]`; o resultado serializado original não é exposto. Definir uma única função pura para calcular exatamente a mesma revisão na submissão e na leitura. `None` deve ser representado explicitamente, sem virar string vazia.
3. Acrescentar aos **dois eventos existentes**: `claim_epoch=verified_claim_epoch`, `delivery_ref`, `delivery_revision`, `verification_verdict=pass|fail`, `verified_by=agent_id` quando pertinente. Manter todos campos legados. No fail, adicionar opcionalmente `current_claim_epoch=updated.claim_epoch` para distinguir a tentativa de retrabalho; isso nunca substitui o epoch verificado.
4. Em `handoff_complete`, acrescentar o mesmo delivery_ref/revision/claim_epoch ao evento existente `handoff.verification_requested` (e à conclusão simples, se útil). Não incluir conteúdo novo no evento metadata-only.
5. Na leitura batch Home, projetar somente o ID do evento, verdict, ator autorizado e referência/revisão coincidente. Usar evento canônico persistido, com workspace/visibilidade e origem do produtor confirmados; não basta encontrar JSON com um `verified_by` arbitrário. A consulta não cria evento, ACK nem verificação.

Isso é payload **aditivo** do produtor já autorizado; não altera elegibilidade, anti-self-verification, CAS, máquina de estados ou protocolo Core/Connector. Não exige tabela/workflow QA novo. O event_id continua pertencendo ao EventEmitter, atribuído no mesmo evento/transação. Para o DTO, publicar um `verification_evidence_ref` opaco desse evento/revisão e metadados mínimos, sem result/feedback privado.

Históricos sem esses campos ficam unknown, sem backfill por timestamp ou reescrita de receipts/hashes. Eventos de aprovação antigos não são prova da versão atual. Ausência/retention do evento também reduz a prova a unknown, não a approved. O custo deve ser um batch autorizado na mesma UoW, restrito aos handoffs/claims candidatos, não consulta por card ou scan de payload/transcript por entrega.

Para E03/E07 sem turno nativo, usar a entrega explicitamente referida por verification_requested/failed e seu claim. O handoff atualmente em VERIFYING pode fornecer o conteúdo existente quando sua revisão coincidir. Após retrabalho, não anexar o `handoffs.result` atual a uma revisão histórica diferente. Se a versão histórica não tiver conteúdo retido, preservar metadata de rejeição e content unavailable. Essa extensão habilita prova positiva futura; não adia todo o requisito de verificação.

## 5. DTO, paginação e consumidores

Proposta de contrato lógico alinhada ao §8, a congelar junto da negociação da apresentação:

- `HomeResult.delivery_semantics` obrigatório para a apresentação nova, com version, scope, evidence, execution_outcome, task_state, verification, verification_evidence_ref, cleanup, content_state, historical e semantic_revision.
- Acrescentar `delivery_ref` explícito, com identidade do resultado e claim/operation pertinente. Manter IDs legados, source_ref, detail_target e referência das sessões/operações originais. IDs públicos/nome do harness nunca são essa chave.
- Para a linha representativa com operação nativa explícita, scope=turn mesmo que possua handoff associado; task_state/verification descrevem esse vínculo separadamente. O fallback sem operação usa scope=handoff. Não transformar a identidade agregada por claim em alegação de que todos os turnos do claim foram aprovados individualmente.
- `not_applicable` só quando a fonte comprova que aquela dimensão não pertence ao objeto; falha/ausência de fonte significa unknown. Para aprovação/rejeição, exigir evidence_ref e correspondência da revisão/claim, não apenas enum.
- A revisão semântica inclui verdict/proof/ref, task_state atual, cleanup e content availability. Não inclui generated_at sozinho. Mudança de verificação atualiza a mesma entrega, mas invalida os cursores pertinentes.
- A versão de apresentação deve entrar em query, scope/cursor/revision e capacidade; manter contrato legado quando ausente. Um campo opcional sozinho não resolve os consumidores estritos que validam distribuição de colunas. O nome exato da seleção é decisão compartilhada de HST-003, não implementado aqui.

Pontos de alteração sincronizada:

| Superfície | Atual | Delta mínimo |
|---|---|---|
| Python `domain/home.py:HomeResult` | Strings abertas verification_state/cleanup_state | Tipo fechado versionado das dimensões e ref de prova; manter membros antigos para consumidores antigos |
| SQLite `home.py:RESULTS/result_item` | status de handoff chamado verification; cleanup só pending; preview limitado | Metadata segura de estado/claim/revisão/captura e projeção pura da semântica; nunca reinterpretar legado como verdict |
| `home_harness_board.py:delivery_dto` | canonical/reported, result/report e entry original | Propagar semântica da origem, preservar unidade delivery e referências compartilhadas |
| `homeTypes.ts:HomeResult/HomeHarnessDelivery` | Strings atuais e completion_evidence | Mesmos enums, ref e versão; sem `any` ou fallback “approved” |
| `homeController.ts:validHarnessSlice` (472–481) | Para delivery valida basicamente ID result/report e canonical/reported | Validar combinações semânticas, proof-required para verdict, scope/server/workspace/claim e versão suportada |
| `HomeHarnessCard.tsx:HomeHarnessSignalCard` | “Completion recorded · Outcome: SUCCEEDED” e instrução genérica | Mapa de mensagens da tabela normativa, projeto em All projects, origem e tempo recebido/atualizado |
| `homePresentation.ts:homeResultLabel` / `HomeCards.tsx:ResultRow` | Concatena enums; verification pode desaparecer quando cleanup existe | Centralizar o mesmo mapa; apresentar outcome/task/verification/cleanup sem suprimir dimensão independente |

Results continua objeto separado do card operacional. Não mover harness para Results ao terminar, nem adicionar quarto destino. Os validadores novos devem negar combinações como evidence=reported+verification=approved sem prova canônica correspondente, e preservar fallback para versão não suportada.

## 6. Preferências, retenção, conteúdo e ação humana

`attention_results.py` mantém episódio handoff/claim ou server/executor/epoch/terminal_sequence; `application/attention_results.py` produz ocorrências resolvidas com ações de inspeção. `home.py:result_attention` usa essas preferências para seen/unseen, ou not_tracked se não há ocorrência. A ausência de rastreamento não é unseen.

`home_board.column_for` e `home_harness_board` preservam a política local existente de recentes/24h para resultados vistos; unseen/not_tracked e reportes externos seguem seus contratos. A consulta Results legada não recebe uma retenção universal nova. Não modificar as âncoras/episódios existentes só para gerar outro contador “novo”. Abrir preview/detalhe não decide, não verifica, não avança inbox nem marca itens invisíveis.

Conteúdo nativo tem proveniência em `execution_results` (migration095): stream_epoch/terminal_sequence com FK para ingress, output_event_count/truncated/captured_at. Uma preview vazia não comprova falta de captura. Cleanup vem de `execution_session_containment` (migration138: REQUESTED/RELEASED), no owner_generation correto; ausência do join não é prova de liberação.

D03/D04: `attention_operations.py` já calcula verification_pending a partir de VERIFYING/verify_by; categoria/action depende da permissão atual, visibilidade e anti-autoverificação. Um handoff para outro agente ou resultado pendente não cria ação humana por conta própria. D06–D14 continuam usando os recibos/intenção canônicos; um verdict da entrega ou HTTP202 de decisão não comprova retomada nativa. Seen/snooze nunca são evidência de execução.

## 7. Etapas pequenas e testes significativos propostos

Nenhum dos testes abaixo foi executado nesta auditoria.

1. **HST-003/011 — domínio/contrato:** tabela pura cobrindo E01–E15 e contradições. Verificar explicitamente turno sem handoff, COMPLETED sem proof, FAILED/CANCELLED, unknown não terminal, cleanup separado e output vazio. Negativo de mesmos operation_id em executores diferentes; manter IDs históricos.
2. **HST-012 — produtor existente:** teste real do serviço handoff_complete/verify pass/fail com UoW temporária. Conferir eventos existentes com delivery_revision+epoch **antes** do incremento no fail; outsider/self-verifier/CAS antigo negados. Entrega B não herda evento da entrega A, mesmo handoff/título. Sem Core ou novo runtime.
3. **HST-011/012 — batch SQLite/HTTP:** turno+handoff CLAIMED→VERIFYING→verified pass atualiza a mesma entrega; fluxo sem turno também acessível; fail da versão N e nova submissão N+1 nunca aprovam N+1. Fonte de evento ausente/histórica/sem referências é unknown. Medir query count constante 1/10/100, sem N+1 nem transcript.
4. **HST-013 — regressões de vínculo/visto:** artefatos de várias operações/executores do mesmo claim preservados; foreign workspace mais recente não toma o grupo nem oculta resultado legítimo; delivery histórico de outro claim separado. Seen/Snooze/GET não escrevem grants, verificação, ACK ou watermark; itens fora da página não são vistos.
5. **HST-014/017 — apresentação/validador:** tabela Node/SSR com textos normativos e combinações inválidas; projeto em All projects, tempos honestos, falha/cancelamento sem retry. Comparar consumidor legado/novo e revision/cursor após mudança semântica.
6. **D/E/I e browser posterior:** entrega verificada só com alvo exato; badge/bell compartilham ocorrência; teclado/nome acessível, foco ao mesmo ID após atualização, estado além de cor, 360px/200%, draft guard e logout. Node/SSR não qualificam AT/browser. Não iniciar provider para criar essas provas.

## 8. Limites e fontes fixadas

Não foram executados pytest, Node, build, browser, serviço, native CLI ou provedor nesta frente. Nenhuma hipótese está rotulada como reprodução. Permanecem as limitações/gates anteriores: campanha nativa encerrada com resultado/consumo desconhecido não é sucesso, metering observado não é teto atômico, AT/humano/multi-host/OS não executados não são qualificados por SQLite ou Node, default da nova apresentação exige gate próprio. Este mapa não reabre nem apaga esses bloqueios.

Fontes de apresentação e semântica foram inspecionadas no checkout atual; os seguintes hashes permitem detectar drift antes de implementar:

| Arquivo | SHA256 |
|---|---|
| `sqlite/home.py` | `e457a441560631b81f6a3cc78b299f04ead79265594d5b5b6e959577c57759c5` |
| `application/handoff.py` | `ddd4512c4b381fa257941c79e1fdabedc7a069d00a785d910973f952b78b453e` |
| `sqlite/handoff_repo.py` | `4498188272d21d7282fe99195977c773505c978be9b3b248514499f02a1d6cef` |
| `domain/home_harness_board.py` | `e3714d2e3601a0a611baaf14dc4fea594c52ff7851944d4364f0b8ceaf3197d0` |
| `frontend/src/homeController.ts` | `390efec0d1b2af755cae5a37b0f411a75d8dea9fac1ef1f91577486c9c5cd810` |
| `HomeHarnessCard.tsx` | `37f9a631728ad9a3cdfe5a6e4cb03b1072ae368f10a73339a38815837c1c9d3e` |

Demais fontes consultadas: domain/home.py, domain/home_board.py, domain/home_entries.py; sqlite/home_entries.py, attention_results.py, attention_operations.py, attention_external.py; application/attention_results.py, attention_operations.py; migrations018/044/045/095/138; frontend homeTypes.ts, homePresentation.ts, HomeCards.tsx e HomeEntryInspection.tsx. Os números de linha são do corte inspecionado e podem mudar.
