# Fontes, rastreabilidade e decisões de projeto

## 1. Natureza deste pacote

Este é um plano novo para implementar as correções da revisão anterior. As fases, tabelas propostas, defaults e cenários de teste são decisões de projeto, não funcionalidades já implementadas ou resultados experimentais obtidos neste pacote.

A PR foi reconfirmada pelo conector GitHub em 22/09/2026: HEAD `d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`, base `27b06fe48b9f95b35c94f50827fea83d178f4e12`, estado aberto no momento da consulta. Isso fixa a referência, mas não dispensa P00 no ambiente do Codex.

A revisão anterior é usada como registro dos achados. Sua transcrição integral anterior não foi recuperada; os invariantes relevantes também foram conferidos no documento histórico disponível e reproduzidos neste pacote. Não se afirma que todos os arquivos da PR ou todos os protocolos tenham sido reexecutados nesta etapa de planejamento.

## 2. Fontes do projeto

### S01 — PR #34, metadados e descrição

`https://github.com/OktoLabsAI/okto-nexus/pull/34`

Fonte para escopo anunciado, HEAD/base, conectores, ferramentas, evidências relatadas e limitações declaradas. Os totais de testes na descrição são afirmações históricas da PR, não resultados da execução deste plano.

### S02 — Guia operacional da PR, no SHA revisado

`https://github.com/OktoLabsAI/okto-nexus/blob/d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397/docs/harness-integrations/operator-guide.md`

Fonte para as capacidades que devem continuar disponíveis, formas legadas de payload, configuração de backend e limites do attach. O guia contém trechos historicamente divergentes da descrição mais recente da PR; P00/P11 devem reconciliá-los com código e testes, e não tratar toda frase como contrato atual comprovado.

### S03 — Migração 029

`https://github.com/OktoLabsAI/okto-nexus/blob/d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397/src/okto_nexus/migrations/029_harness_sessions_and_events.sql`

Fonte para tabelas já existentes, IDs, índices, foreign keys e distinção entre histórico persistido e liveness. Justifica ampliar/reutilizar as estruturas, em vez de sobrescrevê-las ou gerar uma segunda entidade de sessão redundante.

### S04 — Proposta histórica de arquitetura

Arquivo da Library: `okto_nexus_a2a_architecture_v0_1_4.md`, versão 1, análise datada de 25/08/2026.

Seções relevantes: decisão executiva; Agent/AgentEndpoint; outbox; portas de aplicação; fluxos de mensagem; `consume_on_accept`/`mirror_only`; idempotência; handoffs; identidade/autorização; composição stdio/serve.

O documento propõe identidade única, inbox canônica, envio após commit, endpoints múltiplos e outbox durável. Não obriga que esta PR implemente A2A real. O plano atual refina casos que o texto inicial não fechava completamente: concorrência pull/push antes do ACK, envio ambíguo e captura de resultado antes da projeção.

### S05 — Arquivos inspecionados na revisão anterior

Anchors de investigação no mesmo SHA, sem depender de números de linha que podem mudar:

- `application/harness_supervisor.py`: `open`, `send`, `_on_inbox_delivery`, `_resolve_relay_depth`, `_handle_event`, `_persist_event`, `_deliver_notable_message`, `close`, `_bounded_start`, `_bounded_call`.
- `adapters/outbound/sqlite/identity_repo.py`: `SqliteAgentRepo.upsert`.
- `application/messages.py`: `create_message`, `_maybe_notify_inbox_subscribers`.
- `adapters/outbound/inbox_notifier.py`: `publish`.
- `adapters/inbound/mcp/tools/harness.py`: registro das tools, factories e normalização de backend.
- `adapters/inbound/http/routes.py`: rotas e autorização de harness.
- `adapters/inbound/mcp/server.py`: publicação de tools, composition roots e instruções canônicas de coordenação.
- `domain/harness.py`, `application/ports.py`: capacidades/port/sessões.
- `tests/test_harness_target_grammar.py`: composição das fixtures e testes de relay/presença.

P00 precisa abrir os caminhos atuais e registrar renomeações. Estes anchors são pontos de partida, não uma dispensa de investigação nem evidência de que outros caminhos não existam.

## 3. Fundamentos técnicos primários consultados

### S06 — SQLite: WAL

`https://sqlite.org/wal.html`

Relevante para concorrência/serialização de writers, checkpoint, backups e características locais do WAL. Este plano não trata SQLite como um broker de mensagens nativo nem presume que uma notificação em memória exista entre processos só por compartilharem o banco.

### S07 — SQLite: synchronous

`https://sqlite.org/pragma.html#pragma_synchronous`

Relevante à distinção entre commit lógico, fsync e garantias de perda de energia. O modo durável proposto precisa ser validado nas conexões efetivas e no filesystem; um journal em memória ou WAL com configuração mais fraca não sustenta a mesma promessa.

### S08 — Python: futures e subprocessos

`https://docs.python.org/3.13/library/concurrent.futures.html`

`https://docs.python.org/3/library/subprocess.html`

Relevantes à impossibilidade de tratar timeout/cancel de uma espera como cancelamento garantido de código em execução, e ao gerenciamento real de processos/pipes/encerramento. O plano exige limites, isolamento e reconciliação em vez de threads descartadas sem contabilização.

### S09 — OpenAI: Codex App Server

`https://developers.openai.com/fr-FR/docs/app-server`

`https://openai.com/fr-FR/index/unlocking-the-codex-harness/`

A documentação consultada descreve turnos, eventos bidirecionais, steering, interrupt e pedidos de aprovação. Ela não substitui testar o binário efetivamente instalado nem autoriza transportar parâmetros de uma versão para outra sem validar o schema. Não foi escolhida uma nova versão obrigatória do Codex por este pacote.

## 4. Mapa de achados para entregas

| Achado | Contrato principal | Tarefas/fases | Grupos de teste |
|---|---|---|---|
| F01 | Identidade e cardinalidades; perfil não mutável pelo lifecycle | P01–P03 | ID, MIG |
| F02 | RequestContext, grants e matriz de autorização | P01/P04/P11 | AUTH, API |
| F03 | Seleção/lane e reserva de consumo | P02/P05–P07 | ENDP, CONS, DISP |
| F04 | Enqueue transacional, dispatcher e fencing | P05/P06 | TX, DISP, CONS |
| F05 | Journal, projeção e limites da durabilidade | P08 | JRN, E2E |
| F06 | Envelope/correlação/normalização na borda | P02/P07/P08 | API, LIFE, JRN |
| F07 | Handoff/claim/resultado/approval canônicos | P04/P09 | WORK, AUTH, TX |
| F08 | Root/parent/budget persistidos | P10 | RELAY |
| F09 | AdapterRegistry e capacidades efetivas | P02/P07 | ENDP, API, LIFE |
| F10 | Flags, ownership por serve e superfícies opcionais | P01/P06/P11 | API, DISP, MIG |
| F11 | Lifecycle observado, birth ownership, timeout e close | P07/P12 | LIFE, DISP, E2E |
| F12 | Workspace/presença/targets | P03/P05/P11 | PRES, ENDP |
| F13 | Perfis, secret refs, grants, native options | P03/P04/P07 | AUTH, WORK |
| F14 | Replay, cursor e evidence index por SHA | P08/P11/P12 | JRN, API, MIG, E2E |

## 5. Decisões novas que não devem ser confundidas com fatos existentes

São escolhas propostas neste pacote: a nomenclatura completa de estados; a reserva de consumidor gerenciado; os grants restritos quando os mecanismos atuais forem insuficientes; o journal durável de ingresso; o período de reconciliação de 30 segundos; os budgets iniciais de 4 hops, 32 mensagens e 16 execuções por root; a herança ambiente opt-in; os números iniciais de concorrência; e o rollout por etapas.

Essas escolhas podem ser ajustadas pelo Codex à arquitetura real quando houver equivalente melhor, mediante decisão registrada e testes. Não podem ser substituídas por uma implementação que perca as garantias que motivaram a escolha.

A ausência de ACK/dedupe/replay no peer não é corrigida com um novo campo local. Onde não houver garantia de protocolo, manter estado incerto ou operação limitada e explicar a fronteira da garantia. Isso preserva a capacidade disponível sem dar ao usuário uma promessa falsa.


### Decisão de implementação: observação de contexto v1

A rota opcional ContextObservationConnector.observe_context, marcada por
input_schema.context_observation_contract=1, é uma decisão nova para cumprir T-CONS-07/F03/F09.
Sua base é o requisito de observação sem outro executor em 02_CONTRATOS_E_ESTADOS.md, não uma
capacidade atribuída aos protocolos Pi, Codex ou Claude. O quinto adaptador de teste comprova a rota
pela composição HTTP/MCP real; os quatro conectores nativos continuam sem essa capacidade comprovada.
A ausência da rota positiva foi reproduzida em a6a18b4 e registrada no milestone b263de9.
Código, decisões de persistência e execuções por geração: plans/pr34-remediation/P12_MIRROR_OBSERVATION.md.
