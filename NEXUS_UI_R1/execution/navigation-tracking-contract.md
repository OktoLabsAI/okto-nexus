# UI-R1 — proposta de contrato de navegação e acompanhamento (UI-003)

Proposta para revisão PR-00, baseada no HEAD Nexus
`856c7f459d16719aa7dfa54c3dc64c85199cf563`, plano §§3–7 e UI-003. Não é API
implementada ou teste executado. Freeze técnico PR-00 aceito pelo root em
16/11/2026 para orientar implementação; não constitui aprovação de produto,
release ou campanha. O mapa de fontes e
autoridades está em [source-map.md](source-map.md). Preservar Home atual,
alvos/controllers/ações e seus consumidores durante a migração.

Atualização de baseline comunicada pelo root: branch de entrega
`feature/v0.3.5`, bump commit `9de55d95`; Connector `feature/v0.0.13`, commit
`414e3e7`; Core permanece0.0.14. A inspeção de fontes acima antecede somente
esses bumps, não autoriza regressão do checkout. Conferir baseline.json para
SHAs completos e drift antes de implementar.

## Navegação e compatibilidade

Registro futuro separa `id`, `label`, `section`, `group` e feature/visibilidade.
`id` aceita os19IDs atuais tipados por `View` mais o índice `Advanced`; label
não participa de comparadores, permissão, preferência ou URL. Principais:
`Home`, `Meta-harness`→`Conversations`, `Graph`, `Artifacts`. Secundário:
`Advanced`; destinos/grupos completos estão no mapa, sem novos menus Harnesses,
Executions ou Sessions. Attention permanece alvo interno e vira fila global
sob demanda, acessível mesmo no fallback clássico. Approvals mantém acesso à
decisão corrente independentemente da feature que controla catálogo/setup.

| Contrato atual | Compatibilidade obrigatória / delta proposto |
|---|---|
| `View`, comparadores e callbacks App | Preservar IDs e destinos; todo navigate passa pelo guard. Mostrar Advanced selecionado em subpágina e breadcrumb de retorno, preservando workspace. |
| `OPERATOR_VIEWS` e markers | Continuam Messages/Meta-harness. Alterar rótulo não marca mensagens nem visto de resultado. |
| LocalStorage e flags existentes | Preservar chaves e semântica; feature visibility não concede autoridade. Rollout não liga Home nova automaticamente. |
| `home_target` JSON allowlisted | Preservar encoder/parser e IDs opacos; extensão aditiva de kind, sem reescrever IDs antigos ou URLs baseadas em rótulos. |
| `/home/overview`, work/results/agents/activity/external/attention/server-attention | Continuam com significado/envelopes atuais para consumidores existentes. Não usar primeiras páginas como inventário novo. |
| APIs Attention/runtime/setup | Ações canônicas intactas; nenhum `/home/approve`, retry-all ou force-resume. |

Sino global usa a Attention canônica independente do filtro de projeto; exibe
escopo do conteúdo e troca explícita ao abrir ocorrência de outro projeto.
Server global não é trabalho de todos os projetos. Uma única camada ativa
respeita dirty guard; não empilhar fila/drawer/terminal.

## Projeção tipada proposta

Os nomes seguintes são proposta aditiva na fronteira Home, sem tabela nova de
tarefas. `HomeSourceRef`, `HomeSection`, `HomeDisplayState`,
`AttentionOccurrence` e alvos atuais são reutilizados com revisão explícita;
tipos críticos não recebem `any` nem string irrestrita para ações/estado.

```ts
type EntryKind = 'work' | 'session' | 'connection' | 'external' | 'attention';
type Evidence = 'confirmed' | 'reported' | 'inferred' | 'unknown';
type PassiveState = 'configured' | 'connected' | 'idle' | 'offline' | 'stale';
type EntryState = HomeDisplayState | PassiveState;
interface SessionRef {
  server_id: string; executor_id: string; workspace_id: string;
  session_id: string; // exact canonical tuple, not latest
}
interface ConnectionRef {
  server_id: string; executor_id: string; binding_id: string;
  workspace_id: string; agent_id: string;
}
type EntryAction =
  | { kind: 'inspect'; target: ExtendedHomeTarget }
  | { kind: 'attention'; attention_id: string; action: AttentionAction };
type ExtendedHomeTarget = HomeTarget
  | { kind: 'session'; server_id: string; executor_id: string;
      workspace_id: string; session_id: string }
  | { kind: 'connection'; server_id: string; executor_id: string;
      workspace_id: string; binding_id: string; agent_id: string };
interface HomeEntry {
  id: string; kind: EntryKind; source_ref: HomeSourceRef;
  workspace_id: string | null; agent_id: string | null;
  title: string; harness_label: string | null; host_label: string | null;
  display_state: EntryState; evidence: Evidence; state_since: string | null;
  sessions: SessionRef[]; sessions_total: number | null;
  has_more_sessions: boolean; sessions_cursor: string | null;
  attention_refs: string[]; result_refs: string[];
  target: ExtendedHomeTarget | null; actions: EntryAction[];
  as_of: string | null; next_refresh_at: string | null;
}
interface HomeEntryGroup {
  id: string; server_id: string; executor_id: string | null;
  workspace_id: string | null; agent_id: string | null;
  connection: ConnectionRef | null; label: string;
  children: HomeEntry[]; children_total: number | null;
  has_more_children: boolean; children_cursor: string | null;
}
```

Validação runtime também é obrigatória: allowlist de campos/kinds/ações;
identificadores não vazios e limites coerentes com domínio atual; números
inteiros seguros não negativos; estado/evidence conhecidos; timestamps válidos;
cursores opacos limitados. `null` representa desconhecido/ausente, nunca
executor/session fictício. A ação não aceita URL arbitrária. A ocorrência
canônica autoriza quais `AttentionAction` podem ser apresentadas; enviar exige
revisões atuais. O DTO não concede grant por carregar IDs.

### Identidade, correlação e não duplicação

Group ID é derivado de chave estruturada versionada de Server, conexão/binding
quando conhecido, agente, workspace e executor/host/harness comprovados; label
nunca é chave. Sem vínculo de conexão, usar chave própria da atividade, sem
simular grupo técnico. Entry ID deriva da origem canônica estável e mantém
identidade quando recebe executor e muda de grupo. Claim/revision/attempt são
contexto do episódio e revisão, não tarefa nova; não mudar ID a cada render.

Precedência: handoff → entrega lógica sem handoff → operação direta sem pai.
Retries, steer, runtime.open, recibos e resultados comprovados são detalhes do
mesmo pai. Filhos delegados preservam IDs próprios e referência ao pai.
Sessões não cobertas tornam-se entradas session; conexão relevante sem sessão
nem representação vira connection. Pergunta/resultado/artefato relacionados
enriquecem a entrada; órfãos permanecem com origem explícita. Externo só se
associa por vínculo persistido verificável, nunca por PID/nome/agent_id apenas.

Não usar `conversation_sessions` operator-only como universo. A query atual
HomeFACTS é base de atividades A→B, mas será estendida para sessões/conexões
independentes; queries novas precisam autorização antes de joins/contagem.

### Página, filtros e contadores

Propostas, ainda inexistentes: `GET /api/v1/home/entries` e
`GET /api/v1/home/entries/{group_id}/children`. O group_id é opaco e URL-encoded,
revalidado no servidor. Sessões adicionais usam a leitura proposta
`GET /api/v1/home/entries/{group_id}/children/{entry_id}/sessions`, com envelope
`HomeSection<SessionRef>` mais os mesmos metadados de página, group_id e
entry_id. A rota não carrega transcript. Revalidar relação entry→group e
entry→session no escopo atual; IDs não concedem acesso. Os três endpoints
aceitam filtros normalizados e cursor/limit; parâmetros desconhecidos ou
repetidos são rejeitados, conforme a família Home atual.

Envelope version1 reutiliza scope, server_id, generated_at, snapshot_id,
event_cursor/low_watermark e `HomeSection<HomeEntryGroup>`. Acrescenta summary
com unidade/exatidão, aviso Server compacto e revisão de contrato. Proposta
inicial:10grupos/página,3filhos/prévia, limites1..100 validados; transcript nunca
no overview. Filhos retornam group_id e scope canônicos iguais ao pedido,
revision e cursor. Totais exatos ou null/parcial; has_more conhecido e cursor
não são substituídos por tamanho da página.

Sequência no backend: autenticar → resolver escopo → relógio/UoW curta →
relações canônicas de trabalho → sessões/bindings em lote → Attention/resultados
sem perder evidência do destinatário → sessões/conexões descobertas ainda não
representadas → observações externas → deduplicar/grupar → ordenar/contar →
paginar. Não concatenar work/results/agents em React ou executar query por linha.

Filtros rápidos são uma seleção única `active | needs_you | results | all`;
workspace/agente/harness/host/state adicionais são allowlisted e vinculados ao
cursor. `active` inclui execução e esperas distinguíveis; needs_you só operador
atualmente destinatário/autoridade; all inclui conexões sem trabalho. Default
inclui trabalho não terminal, sessões vivas/conexões relevantes e resultados
terminais24h. Não vistos rastreados seguem alcançáveis além dessa janela,
respeitando retenção. Não traduzir fonte inacessível em zero/onboarding.

Contadores: atividades lógicas distintas; pendências por ocorrência acionável;
resultados por entrega/episódio; sessões separadamente no grupo. Não somar essas
unidades nem grupos como trabalhos. Server global é partição independente, fora
dos totais de projeto; aviso aparece só com incidente relevante.

Ordenação: ação humana → problema/incerto → running → espera → resultado recente
não visto → conectado sem trabalho; timestamp canônico e ID estável desempata.
Campo state_since só quando existe transição comprovada, senão última
atualização/início com rótulo correto. Ao editar/expandir, aplicar texto sem
trocar alvo; reordenação que desloca foco aguarda “Há atualizações”.

### Cursor, erros e versão

Cursor opaco vincula versão de contrato, Server, identidade/escopo autorizado,
filtros normalizados, partição, parent/group_id para filhos, revisão e tupla de
ordenação. Toda página reautoriza; não manter transação entre páginas. Mudança
de revisão incompatível rejeita cursor explicitamente com CONFLICT e releitura
da página inicial, sem união silenciosa de snapshots. Campos/limites/kinds
inválidos usam VALIDATION_ERROR; alvo retido usa NOT_FOUND; scope divergente
CONFLICT; sem autoridade PERMISSION_DENIED/HTTP401–403 conforme mapper atual.
Falha de fonte usa status partial/unavailable/disabled e razão canônica, total
null, preservando partes autorizadas. Proposta não inventa novos códigos HTTP.

Adicionar novos targets conjuntamente em homeTypes/homeNavigation, domain/home,
HTTP/resolver, inspector e testes round-trip. Não reinterpretar versões antigas;
mudança incompatível do envelope exige versão nova, com fallback explícito.

## Alvo exato e sessão sem turno

Exemplo válido proposto (não aceito pelo parser atual até UI-019):

```json
{"kind":"session","server_id":"srv-a","executor_id":"exe-remote","workspace_id":"project-a","session_id":"session-2"}
```

O resolver autentica, carrega sessão pelo tuple real, compara Server/executor/
workspace/session, retorna scope completo/revisões e só então habilita leitura.
Não exige `turn.submit` nem operation_id: uma sessão aberta sem turno é caso
legítimo. `runtime.open` interno não vira identidade fictícia de trabalho.
Histórico retido/inexistente é indisponível. Múltiplas sessões pedem seletor
explícito, nenhuma escolha da mais recente.

Exemplos inválidos: session sem executor; execution com `operation_id:""`;
`session_id:"latest"` usado como alias; resposta com workspace/executor distinto;
connection com binding de outra identidade; action com URL fornecida pelo
agente; total2 quando só se sabe que a prévia tem2; global Server atribuído aos
contadores de project-a; unir externo por hostname; deduzir RUNNING de claim.
String opaca legitimamente igual a “latest” só seria ID real se resolvida como
tal, nunca alias de seleção implícita.

## Painel e invalidação

Reutilizar `HomeInspection`/`CanonicalInspection`/`AgentActionModal`, extrair o
corpo de SessionTerminalModal para drawer/fullscreen mobile, manter wrappers
antigos. Tail/history são RuntimeSessionTail/RuntimeHistory/RuntimeTerminal e
eventos autorizados/redigidos; maximizar amplia a mesma camada. Abrir/fechar
não executa nem interrompe; pause é visual. Sessão termina → histórico mesmo ID.
Responder, aprovar, continuar, cancelar handoff e interromper turno mantêm
efeitos e APIs distintos, revalidação de destinatário/revisão/TTL e recuperação
idempotente após perda de resposta. Dirty guard e foco/scroll retornam ao mesmo
entry ID mesmo se grupo mudar; se invisível, âncora estável, nunca posição antiga.

Estender HomeController/useHomeOverview com entries/filhos preservando1inflight,
generation/cancelamento, escopo de cache e 15s fallback/deadlines. SSE do shell
invalida, não é payload autoritativo; sem stream por linha. Attention reutiliza
seu controller/stream, fonte única do badge/fila/preferências. Reconnect/gap/
tab resume provocam releitura;401/403/logout apagam protegido, drafts sensíveis
e observação local. Consultar transcript apenas da sessão selecionada visível.

## Aceite documental e próximos testes

UI-003 está como proposta implementada para revisão, não VERIFIED automático.
Cobertura documental: IDs/rótulos/compatibilidade; tipos e fontes; precedência;
sessão sem turno; paginação backend; unidades; filtros/ordem; erros/versões e
exemplos válidos/inválidos. As três rotas novas são propostas de contrato para
implementação conjunta do DTO/query; não estão disponíveis no HEAD inspecionado.

T-NAV-01 requer browser autenticado e sidebar nova; T-DATA-01/T-DATA-06 exigem
SQLite/HTTP da projeção nova; T-PANEL-01 exige parser/resolver de session sem
operation_id. Todos continuam NOT_RUN nesta etapa. Mapas antigos não promovem
esses cenários novos. HOME-R1 H02/I01/campanha/avaliação humana/performance e
rollout continuam com seus limites; nem UI-003 nem um menu novo aprovam M3.
