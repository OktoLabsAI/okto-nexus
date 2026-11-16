# Plano para o Codex — evolução da Home operacional do Okto Nexus

**Revisão:** HOME-R1  
**Objetivo:** evoluir a Home existente para acompanhamento e intervenção consolidados.  
**Entregas propostas:** 7 PRs incrementais, 36 tarefas e 73 cenários de aceite.  
**Natureza:** plano de implementação fundamentado em inspeção estática. Nenhum teste do Nexus foi executado nesta elaboração; nenhum repositório foi alterado.  
**Relação com o plano anterior:** complemento focado na Home; preserva daemon, preset generalista, identidade persistente, fluxo cotidiano pelo terminal e dashboard opcional. Não substitui o plano de onboarding/integração.

## 0. Instruções de execução

O Codex deve começar pela PR-00. Inspecionar o checkout real e registrar drift antes de modificar arquivos. Não recriar recursos já implementados, não sobrescrever trabalho local, não aplicar reset/clean, não fazer force-push, não iniciar campanha com dados/credenciais de produção e não publicar deploy ou release sem autorização.

Os nomes de serviços, modelos, endpoints e arquivos novos deste documento são **propostas de contrato**, não afirmações de que já existem. Reutilizar equivalentes mais recentes quando preservarem os requisitos. Cada tarefa precisa de evidência de implementação e de validação; presença de arquivo, teste sintético ou trecho de documentação não comprova qualificação completa.

### Baseline consultado

| Referência | SHA consultado | Uso |
|---|---|---|
| `feature/v0.3.3` | `4ba6fa40383a4157eb0fe5e1b9a943bf112a089b` | Base principal da inspeção da Home e de seus serviços. |
| `main` | `8d77b50c00b417c86818d027aed7497fababac34` | SHA observado na listagem de branches; não é a base deste plano de evolução. |
| `develop` | `1a459f7fb19f3ce5ebd1d9ca3bc7f6b5b84855f6` | Referência observada, não alvo obrigatório. |

Na base principal, `frontend/package.json` declara 0.3.3. Isso identifica a branch inspecionada, não comprova versão publicada nem a build instalada pelo usuário. Usar o checkout atual acordado, não retroceder ao SHA por conveniência.

## 1. Objetivo de produto e fronteiras

A Home deve permitir responder, sem trocar de tela: **quem está trabalhando; em quê; o que está aguardando; o que depende de mim; o que ficou pronto**. Clicar abre o registro exato e permite a ação autorizada no contexto. Telas especializadas continuam para aprofundamento.

Não é um painel de indicadores históricos, nem um segundo orquestrador, nem um terminal multiplexer. O foco é o trabalho corrente, os resultados e as decisões. Complexidade técnica permanece disponível em detalhes, não como conteúdo principal.

### Invariantes obrigatórios

1. Dashboard continua opcional: instalar, conectar, pedir, acompanhar, responder e obter resultado pelo terminal não ganha etapa web obrigatória.
2. Server mantém autoridade de coordenação; Core executa; Connector hospeda execução remota. Esta frente não exige mudança de protocolo desses componentes por padrão.
3. A Home lê/projeta fatos canônicos. Não mantém outra fila, máquina de estados de execução, scheduler ou agente interpretando eventos.
4. Abrir, recarregar, filtrar ou expandir a Home não inicia inferência, aprova, completa trabalho, reivindica handoff, reconhece inbox ou amplia grant.
5. Conectividade, presença, atividade, capacidade, admissão, aceitação nativa, resultado e verificação permanecem conceitos separados.
6. Permissões de leitura de cada fonte valem para resumos, contadores, prévias, detalhes e links. Uma referência visível não concede capacidade de ação.
7. Ações continuam nas APIs existentes, com revisão, correlação, idempotência e revalidação atuais. Resultado desconhecido não autoriza replay.
8. Identidade de agente é persistente e pode ter múltiplas sessões. A unidade primária da Home é uma atividade lógica, não o agent_id isolado.
9. Observação externa é identificada como reportada/inferida, com validade e origem. Não prova execução gerenciada nem conclusão de tarefa.
10. Desabilitar a nova Home não muda nenhum desses contratos nem interfere nos agentes em execução.

### Fora de escopo inicial

Não construir editor de políticas na Home, widgets personalizáveis, gráficos financeiros, estimativas de custo sem fonte, porcentagem de progresso inferida, terminal PTY novo, novo protocolo Herdr, redistribuição automática de tarefas, sumarização por LLM, notificações externas obrigatórias ou uma migração completa do sistema de navegação/localização.

## 2. Diagnóstico concreto da base existente

| Fato observado | Consequência para a evolução |
|---|---|
| `HomeView.tsx` já reúne graph, sessões, mensagens, Attention e observação externa, com atalhos. [S01] | Refatorar a Home em vez de criar outra tela ou recomeçar o dashboard. |
| `App.tsx` já seleciona Home inicialmente nesta branch. [S02] | Preservar esse comportamento e contexto; não tratar “criar Home inicial” como tarefa ausente. |
| `conversation_sessions` filtra interações originadas por `operator`. [S03] | Nova visão precisa incluir trabalho agente→agente. Não usar esse diretório como inventário universal. |
| `graph_snapshot` tem nós globais, mesmo com workspace filtrado. [S04] | Não chamar `nodes.length` de agentes atuando no projeto. Criar agregação escopada própria sem mudar a semântica do Graph. |
| Visão de runtime é por agente e distingue instâncias de turnos concluídos. [S05] | Reaproveitar semântica/portas, mas não chamar o endpoint uma vez por agente na Home. |
| Attention já tem revisões, prioridade, atualidade, ações e visto/adiado. [S06–S07] | Não criar outro detector de pendências nem outro mecanismo concorrente de visto. |
| `AttentionInspection` já abre registros exatos e componentes canônicos. [S08] | Generalizar a composição contextual. A inspeção pode continuar modal no M1; não reimplementar decisões. |
| `useSSE` já existe no dashboard. [S09] | Reutilizar o stream compartilhado e auditar cobertura; não criar SSE por cartão. |
| `operatorUnread` usa marcador temporal local para Messages e Meta-harness. [S10] | Não adicionar Home à marcação global e não zerar mensagens novas por exibir apenas um resumo. |
| A Home declara leituras sem escrita de visto/decisão. [S01] | Manter esse princípio; eventual marcação de visto deve ser uma ação explícita e separada. |

**Conclusão:** a evolução é principalmente um modelo de leitura operacional, composição de componentes existentes e correlação de dados. Não se resume a reorganizar cartões, pois duas fontes atuais têm escopo inadequado para a visão pretendida.

## 3. Experiência alvo

### 3.1 Estrutura padrão

| Região | Conteúdo | Limite inicial proposto |
|---|---|---|
| Cabeçalho | Home/Visão geral, nome do projeto ou Todos, atualidade, Novo pedido, Conectar agente. | Sem IDs longos por padrão. |
| Resumo | Atividades executando, aguardando início, ocorrências que dependem do operador, resultados novos quando rastreáveis. | Quatro indicadores clicáveis. |
| Precisa de você | Pergunta ou motivo, agente, trabalho, idade, ação primária válida. | 3 ocorrências, com total e expansão na própria Home. |
| Trabalho em andamento | Objetivo, agente, estado, motivo, projeto/host/harness secundários, tempo e acompanhar. | 10 itens e carregamento incremental. |
| Respostas e entregas | Resumo, autor, status canônico, artefatos e abrir/continuar. | 6 entregas e carregamento incremental. |
| Agentes conectados | Agentes sem trabalho destacado, presença/conectividade e capacidades de observação conhecidas. | 6 itens compactos; não chamar todos de disponíveis. |
| Atividade recente | Eventos de negócio legíveis e correlacionados. | 12 eventos no M3. |

Os limites são parâmetros iniciais de apresentação e API, não motivos para truncar silenciosamente o conjunto. Sempre informar `has_more` e total quando conhecido. Listas não devem exigir navegar para outra tela para acessar a próxima página.

No desktop, trabalho e resultados recebem maior área; pendências ficam no topo ou numa coluna lateral compacta conforme largura. No mobile, ordem: resumo, precisa de você, trabalho, resultados, agentes, feed. Preservar componentes, cores, temas e padrão linguístico existentes; exemplos em português aqui não impõem reescrita do frontend em outro idioma.

### 3.2 Estados proporcionais ao uso

- Sem agentes: uma chamada Conectar primeiro agente usando o onboarding existente; nenhuma página de configurações avançadas como etapa padrão.
- Um agente conectado e nenhum trabalho: confirmar projeto/harness e oferecer Fazer pedido ou Conversar. Não exibir seis painéis vazios.
- Operação normal: trabalho e resultados são o conteúdo principal; ausência de pendências aparece em uma linha discreta.
- Pendências: mostrar o motivo e a ação, não apenas um número ou cor.
- Dados indisponíveis: mostrar erro/limitação e recuperação de leitura, não “não existe atividade”.
- Fonte externa ausente: a Home nativa continua completa. MCP-only sem telemetria de atividade mostra participação/presença conhecida e “atividade não informada”.

### 3.3 Seleção de workspace

Usar o contexto explícito da abertura pelo terminal quando houver, respeitando seleção válida já persistida. Não fixar o workspace inicial do Server como seleção global perpétua. Nomes amigáveis vêm do catálogo atual. IDs completos aparecem em detalhe/cópia.

Em Todos, todos os itens mostram projeto. Em um projeto, todos os contadores e listas operacionais são filtrados antes da paginação. Agentes globais não são automaticamente participantes ativos de cada projeto. Incidentes realmente globais, quando autorizados, têm uma faixa “Servidor” separada dos números daquele projeto.

### 3.4 Detalhe contextual

Clique em Acompanhar/Responder/Ver resultado abre o alvo exato, preservando a Home. Desktop pode usar drawer lateral; mobile pode usar camada de tela inteira com semântica acessível. A escolha modal/não modal deve ser coerente com foco, backdrop e teclado, nunca apenas visual.

O detalhe mostra pedido/contexto autorizado, fatos de execução, conversa correlacionada, pendências e resultados. IDs, recibos e tentativas ficam em Detalhes técnicos. Não carregar transcript completo no overview.

Fechar devolve foco e scroll. Trocar de item, filtro ou projeto não move uma decisão pendente para outro contexto. Rascunhos ficam no componente/sessão adequada e não são copiados para URL/localStorage indiscriminadamente. Logout ou revogação limpa dados sensíveis.

### 3.5 Pedido e continuidade

Novo pedido reutiliza composer/serviços existentes, com escolha explícita entre trabalho rastreável (handoff) e conversa (mensagem). O seletor só mostra agentes e alvos elegíveis/visíveis sob os contratos atuais. A elegibilidade exibida é uma prévia e é revalidada no envio.

Continuar conversa exige correlação explícita de workspace, destinatário e sessão. Não abrir automaticamente “a sessão mais recente do agente”. Sessão encerrada, incompatível ou sem autorização pede novo contexto explícito. Intervenção humana usa identidade do operador, nunca o autor agente de uma pergunta anterior.

## 4. Modelo de leitura: o que representa cada linha

### 4.1 ActivityItem é uma projeção, não uma entidade de execução

`ActivityItem` agrupa referências canônicas. Não é gravado como uma segunda tarefa e não assume responsabilidade por despacho. Tipos iniciais: `handoff`, `conversation_turn`, `direct_operation`; `external_instance` é observação visual separada.

Identificadores incluem o namespace do Server e a chave da origem. Para runtime, manter executor e sessão/operação. Para observação externa, incluir fonte, instância e geração. Usar IDs estruturados opacos ou serialização canônica, não concatenação ambígua de strings controláveis.

### 4.2 Regras de agrupamento

1. Handoff existente é o item pai; operações/tentativas explicitamente vinculadas entram em detalhe. Abrir sessão não cria outro trabalho.
2. Sem handoff, uma entrega de conversa destinada à execução pode ser o item pai; uma entrega lógica possui apenas um item apesar dos retries.
3. Operação direta sem entrega/handoff aparece pelo seu ID canônico. `steer` e controles ligados à operação não viram tarefa nova.
4. Um handoff filho delegado a outro agente é trabalho distinto e mostra a relação com o pai; não colapsar um DAG inteiro em uma única linha.
5. Mensagem informativa ou broadcast não se transforma em tarefa porque existe inbox unread.
6. Sessão sem operação ativa vai para Agentes/sessões, não Em andamento. Pool aquecido, manutenção e processos abertos não são progresso produtivo.
7. Handoff, mensagem, resultado e artefato só são agrupados por referência persistida. Sem relação comprovada, manter entradas distintas com tipo claro.
8. Mesmo agente em vários workspaces/sessões continua com atividades distintas. Um único badge agregado não substitui os estados filhos.
9. Native e externo não são fundidos por nome/PID/agent_id. Associação explícita pode permitir exibir sinais juntos, mantendo autoria, geração e diferença de garantia.

### 4.3 Estados de apresentação

Estes rótulos não alteram as máquinas de estado canônicas:

| Evidência | Rótulo proposto | Não inferir |
|---|---|---|
| Intenção/entrega aceita e fila canônica comprovada | Na fila | Que uma mensagem unread já está na fila de execução. |
| Handoff OPEN sem bloqueio de dependência | Aguardando responsável | Que alguém está executando ou que o Core já recebeu. |
| Handoff CLAIMED sem execução confirmada | Assumido | RUNNING. |
| Dependência não satisfeita | Aguardando dependência | Falha do agente. |
| Recibo de aceitação nativa sem início confirmado | Recebido pelo harness | Trabalho concluído ou em execução confirmada. |
| Turno/execução corrente confirma RUNNING | Executando | Percentual de avanço ou conclusão. |
| Pedido nativo pendente ao operador | Aguardando você | Que qualquer operador pode responder como o destinatário original. |
| Pergunta pendente a outro agente | Aguardando outro agente | Intervenção humana obrigatória. |
| Handoff VERIFYING | Aguardando verificação | Entrega aceita. |
| Recibo/evidência inconclusiva | Resultado não confirmado | Falhou sem efeitos; é seguro repetir. |
| Handoff COMPLETED | Trabalho concluído | Que resultados de outro claim/época também valem. |
| Turno SUCCEEDED, mas handoff ainda não concluído | Turno concluído; trabalho pendente | Handoff concluído por derivação. |
| Produtivo SUCCEEDED com cleanup pendente | Resultado disponível + pendência de limpeza | Reexecutar o trabalho. |
| Externo working/blocked/done | Atividade reportada/inferida | Autoridade, capacidade ou task success. |

A classificação considera a versão/época atual e conserva evidências desconhecidas. Se houver estados simultâneos, mostrar resumo e contagens internas (ex.: uma execução ativa e uma pergunta), sem sobrescrever tudo com um status único. Tempo mostrado é tempo desde mudança de estado quando conhecido, não tempo desde criação disfarçado; ausência de timestamp é exibida honestamente.

### 4.4 Definição dos contadores

- **Em execução:** atividades lógicas distintas com execução corrente confirmada. Dentro de uma atividade com múltiplos turnos, detalhes mostram quantos; não multiplicar o total pelo número de joins.
- **Aguardando início:** atividades que aguardam fila, responsável ou despacho, com discriminação no filtro; dependência e espera de resposta são estados próprios. Não usar unread inbox nem número de sessões.
- **Precisa de você:** ocorrências acionáveis da atenção destinadas ao operador sob o contrato atual; respeitar adiado e distinguir aberto de não visto. Uma atividade pode ter mais de uma decisão.
- **Resultados novos:** ocorrências de resultado com rastreamento de visto por episódio/revisão. Quando não houver rastreamento confiável, mostrar Resultados recentes, nunca zero ou total inferido.

São unidades diferentes e os quatro números **não devem ser somados como total de tarefas**. Atividades externas têm contagem identificada separadamente. Totais desconhecidos, parciais ou desabilitados usam `null`/metadados apropriados, não `0`.

## 5. Arquitetura e contrato propostos

### 5.1 Responsabilidades

Frontend → adaptador HTTP existente → serviço de leitura da Home → portas de consultas agregadas/projeções existentes → SQLite e fatos duráveis já publicados. Core e Connector não são chamados por cartão, por refresh ou dentro de uma transação de leitura.

Componentes propostos: `HomeOverviewService`, `HomeOverviewQueries`, `HomeActivity`, `HomeSummary`, `HomeTarget`, `HomeDataState` e `HomeDetailPanel`. Podem ser substituídos por equivalentes do repositório após a PR-00. Funções puras fazem classificação/apresentação; SQL agrega com escopo e índices; aplicação compõe; UI renderiza.

Projeções da Attention, runtime e observação são reutilizadas, mas seus endpoints não devem ser chamados por HTTP internamente pelo próprio Server. Reutilizar use cases/portas e criar consultas em lote quando a versão atual só tiver API por agente. Não concatenar páginas limitadas para fingir inventário completo.

### 5.2 Endpoints de leitura sugeridos

```text
GET /api/v1/home/overview?workspace_id=<id>&limit_work=10&limit_attention=3&limit_results=6
GET /api/v1/home/work?workspace_id=<id>&state=<state>&agent_id=<id>&cursor=<opaque>
GET /api/v1/home/results?workspace_id=<id>&cursor=<opaque>
GET /api/v1/home/activity?workspace_id=<id>&cursor=<opaque>
```

Omitir workspace_id significa Todos, condicionado à autorização já existente. Não transformar o sentinela `all` em um ID real no backend. Usar o envelope padrão `/api/v1` do projeto; não misturar formatos de `/v1`. Paginação de Attention e controle de visto/adiado continuam pelas rotas canônicas ou por adaptação fina ao mesmo serviço.

Detalhes e efeitos permanecem nas APIs canônicas de cada objeto. Não criar `/home/approve`, `/home/retry`, `/home/execute` com semântica paralela. Um resolver somente-leitura de alvos é aceitável se for necessário e reaproveitar os mesmos controles de acesso.

### 5.3 Forma conceitual do payload

O exemplo abaixo é contrato proposto, não resposta de uma API disponível:

```typescript
type SectionStatus = 'ready' | 'partial' | 'unavailable' | 'disabled' | 'forbidden';
interface HomeSection<T> {
  status: SectionStatus;
  as_of: string | null;
  next_refresh_at: string | null;
  items: T[];
  total: number | null;
  total_is_exact: boolean;
  has_more: boolean;
  next_cursor: string | null;
  reason_code?: string;
}
interface HomeActivity {
  id: string;
  kind: 'handoff' | 'conversation_turn' | 'direct_operation';
  source_ref: { type: string; id: string; revision: string };
  workspace_id: string;
  title: string;
  title_origin: 'canonical_title' | 'message_subject' | 'fallback';
  agent_ids: string[];
  display_state: string;
  state_since: string | null;
  last_activity_at: string | null;
  evidence_status: 'confirmed' | 'unknown';
  attention_refs: string[];
  runtime_refs: Array<{ executor_id: string; session_id: string; operation_id?: string }>;
  detail_target: HomeTarget;
}
interface HomeOverview {
  version: 1;
  scope: { workspace_id: string | null; agent_id?: string; state?: string };
  generated_at: string;
  snapshot_id: string;
  event_cursor: number | null;
  event_low_watermark: number | null;
  summary: HomeSummary;
  work: HomeSection<HomeActivity>;
  attention: HomeSection<AttentionOccurrence>;
  results: HomeSection<HomeResult>;
  agents: HomeSection<HomeAgent>;
  external_activity: HomeSection<ExternalObservation>;
}
```

`HomeTarget`, `HomeSummary`, `HomeResult`, `HomeAgent`, `AttentionOccurrence` e `ExternalObservation` devem ser especificados ou reutilizados na PR-00/01. Não converter esse exemplo incompleto em tipos `any` para acelerar a implementação. URLs de ações não são arbitrárias: ações são enum/referência tipada resolvida por uma lista permitida de handlers.

`event_cursor` só representa o stream ao qual realmente pertence. Não assumir que toda mudança de runtime/atenção gera evento nesse stream. Se as fontes têm revisões diferentes, carregar a revisão por seção. `snapshot_id` serve a consistência/diagnóstico; não é token de autoridade.

### 5.4 Consistência, limites e falhas

Usar um instante do servidor e uma transação de leitura curta para seções respaldadas pelo mesmo SQLite, de modo que lista e total correspondam. Reutilizar o contexto/UoW suportado, sem abrir snapshots conflitantes em cada subconsulta. Não ler filesystem de artefato, journal integral, API de provedor ou processo dentro dessa transação.

Valores de validade temporal pertencem a cada origem; um payload acabado de gerar pode conter observação antiga. Não prometer snapshot atômico de vários hosts: a Home mostra os últimos fatos duráveis publicados, com seu tempo e atualidade.

Paginar por chaves e ordenação determinística, com cursores opacos vinculados a escopo/filtros/ordem/contrato. No mínimo incluir um desempate imutável. Se uma revisão estrutural invalidar a página, retornar condição explícita para reiniciar a leitura, preservando seleção quando autorizado. Não manter transação SQLite aberta entre cliques nem implementar um banco de snapshots para esse MVP.

Em erro transitório, o cliente pode reter a última leitura **apenas do mesmo servidor, identidade e escopo**, com aviso e timestamp. Em 401/403/revogação, limpar o protegido. Erro de um bloco não vira lista vazia nem derruba automaticamente todos os outros. Se os contadores dependerem de uma fonte indisponível, ficam parciais/desconhecidos.

## 6. Reutilização de ações e leitura de resultados

### 6.1 Atenção

A Home usa os mesmos IDs/revisões/ações permitidas da Attention. Não mantém preferências ou resoluções próprias. Para itens com várias ações, oferecer uma principal e detalhes. Adiado afeta o destaque da atenção, não o fato de uma atividade continuar bloqueada.

Os controles atuais de perguntas e aprovações devem ser componentes reutilizáveis, não páginas copiadas. Revalidação pode transformar o alvo em resolvido, expirado ou indisponível entre clique e envio. Tratar isso na UI sem concluir que o comando falhou sem efeito.

### 6.2 Visto não é ACK

Há três conceitos: entrega/ACK de inbox, visualização de mensagem do operador e preferência de atenção. Não fundir nenhum deles.

Para resultados já associados a `result_unseen`, reutilizar visto por ocorrência/revisão. A ação inicial recomendada é explícita: “Marcar como visto” após abrir o resultado; não observar viewport para marcar automaticamente. Uma abertura bem-sucedida pode futuramente ser tratada como visto somente por decisão documentada e teste de escopo/revisão.

Para resultados não cobertos por esse contrato, começar com “Recentes” e `view_state=not_tracked`. Não criar outro watermark global nem declarar contador exato de novos. Se futuramente for necessário unificar o rastreamento de todo resultado, fazer ADR e migração aditiva do modelo compartilhado, incluindo interoperabilidade com Messages/Meta-harness; isso não é autorização para redesenhar a inbox.

### 6.3 Prévia e privacidade

Título vem de título/assunto existente ou fallback determinístico, com origem explícita. Não inferir um objetivo lendo prompts privados ou com LLM. Resumos vêm de campos já permitidos e limitados. Truncamento é indicado; conteúdo completo requer consulta e autorização próprias.

Artefatos usam preview/download atuais, sanitização e isolamento de conteúdo. Redação de segredos e ocultação de paths seguem políticas existentes. Links internos não carregam tokens, textos de pergunta, respostas, prompt ou paths privados.

## 7. Atualização em tempo real e estabilidade de uso

Reutilizar uma assinatura SSE no shell e expor invalidações para a Home. Mapear eventos por bloco; um token de output não provoca refetch do overview inteiro. Valor inicial proposto: debounce de 300–500 ms, no máximo uma releitura consolidada por segundo em burst, uma requisição em voo e uma invalidação pendente. Medir e ajustar sem perder eventos finais.

O carregamento inicial combina assinatura e snapshot com reread quando necessário para cobrir a janela de corrida. Reconnect, cursor antigo, lacuna de retenção e retomada da aba exigem snapshot atualizado; não tratar SSE como fonte exclusiva de verdade nem como prova de exactly-once.

Manter fallback limitado — inicialmente 15 s para overview, alinhado ao comportamento atual — e programar refresh pelo `next_refresh_at` quando uma validade terminar antes. Mudanças de prazo acontecem sem evento. Pausar ou reduzir polling em background, retomando com leitura fresca antes de ação. Prefetch de conteúdo sensível sem necessidade é proibido.

Distinguir estado do transporte (`connecting/live/reconnecting/off`), estado da consulta (`loading/ready/stale/error/forbidden`) e atualidade da fonte. Não colocar tudo num único círculo verde.

Para evitar movimento de tela, atualizações não roubam foco, não colapsam itens e não reordenam o cartão que está sendo editado. Novos itens podem gerar “Há atualizações” com aplicação controlada quando houver interação em curso. A pausa visual controla atualização da apresentação, nunca execução dos agentes; decisões continuam exigindo revalidação fresca e consentimento atual.

Usar avisos acessíveis agrupados; não anunciar cada token. Referências de acessibilidade: [W01–W02].

## 8. Arquivos e componentes

### Existentes confirmados e a preservar

- `frontend/src/views/HomeView.tsx`: evolução principal; separar layout, dados e apresentação conforme a dimensão real da mudança.
- `frontend/src/App.tsx`: contexto, autenticação, seleção de Home e stream; evitar fazer do shell um novo serviço de domínio.
- `frontend/src/views/AttentionView.tsx` e `frontend/src/attentionTypes.ts`: contratos e apresentação compacta compartilhável.
- `frontend/src/components/AttentionInspection.tsx`: composição de inspeções; extrair/generalizar alvos sem duplicar formulários.
- `frontend/src/useSSE.ts`: stream; auditar reconexão/cobertura antes de ampliar.
- `frontend/src/operatorUnread.ts`: preservar semântica atual; Home fora de marcação temporal em massa.
- `src/okto_nexus/application/meta_harness_sessions.py`: manter diretório do operador; não ampliar por acidente a semântica de seus consumidores.
- `src/okto_nexus/application/observability.py`: manter nós globais do Graph; nova consulta resolve escopo operacional.
- `src/okto_nexus/application/agent_runtime_administration.py`: reaproveitar autorização e classificação sem chamadas por agente.

### Organização nova sugerida, condicionada ao checkout

```text
src/okto_nexus/domain/home_overview.py              # projeções/regras puras, se esse padrão fizer sentido
src/okto_nexus/application/home_overview.py         # composição do caso de leitura
src/okto_nexus/application/home_overview_ports.py   # contrato de consultas agregadas
src/okto_nexus/adapters/outbound/sqlite/home_overview.py
<registro HTTP existente>/home_overview.py
frontend/src/homeTypes.ts
frontend/src/homePresentation.ts
frontend/src/homeNavigation.ts
frontend/src/hooks/useHomeOverview.ts
frontend/src/components/home/                       # blocos e detalhe; dividir por necessidade
```

Não criar todos esses arquivos por obrigação. Não abrir um framework genérico de dashboards. Extrair somente duplicação real e preservar interfaces públicas existentes. Core/Connector só entram numa alteração se um fato necessário não puder ser obtido de contratos publicados; documentar lacuna, impacto e qualificação separada em vez de acoplar a Home ao host.

## 9. Desempenho, acessibilidade e critérios de produto

### Metas propostas para validação, não medições existentes

- Usuário identifica trabalho, bloqueio e entrega em até aproximadamente 10 segundos num cenário de demonstração; testar com pessoa que não conhece as telas internas.
- Uma ativação abre o alvo exato a partir da Home; confirmar aprovação continua sendo gesto separado e explícito.
- Visão inicial útil em até 2 s e endpoint de overview p95 até 500 ms numa fixture/hardware registrados. Ajustar somente com justificativa, baseline e comparação; rede e provedor não entram como dependência da leitura.
- Até 10 linhas de trabalho, 3 de atenção e 6 entregas no payload inicial; metadados/preview idealmente abaixo de 200 KiB. Conteúdo completo fora desse limite é carregado sob demanda.
- Número de queries por overview limitado pelo conjunto de blocos, não pelo número de agentes, sessões ou cartões. Instrumentar para provar ausência de N+1.
- Testar 1/10/100 agentes, 1.000 atividades abertas e 100.000 eventos históricos em SQLite descartável; não são promessas de capacidade de produção.
- Sem múltiplos streams duplicados, revalidações por token ou leitura completa de logs. Inserção de índices depende de EXPLAIN e mede custo de escrita.
- Teclado, leitor de tela, foco restaurado, cores com texto, mobile de 360 px e zoom 200%; respeitar preferência de movimento reduzido.

Métricas de produto locais/opt-in: tempo até abrir pendência, tempo até encontrar resultado, transições de tela para uma ação cotidiana, taxa de falha/abandono e motivo. Não coletar prompts, respostas, paths, chaves ou IDs privados em telemetria externa. Não presumir instrumentação de uso autorizada por esta solicitação.

## 10. Marcos e ordem das entregas

**M1 — Visibilidade operacional:** PR-00, PR-01 e PR-02. Trabalho real incluindo agente→agente, pendências concretas e resultados básicos, com referências exatas e sem troca de tela para pesquisar. Inspeções existentes podem manter a forma modal atual. Não depende do feed avançado, de Herdr ou de novas integrações.

**M2 — Operação no contexto:** PR-03 e PR-04. Detalhes integrados, decisões, pedidos, continuidade e visualização de resultados coerentes; reutilização das mesmas autorizações.

**M3 — Home padrão qualificada:** PR-05 e PR-06. Feed legível, atualização/falhas robustas, observação externa opcional, acessibilidade, desempenho medido e rollout. Testes de segurança, unidade e integração entram em cada PR; não são adiados para M3.

O backend de leitura e os componentes de apresentação podem avançar em paralelo após o contrato. Core/Connector não são dependências de entrega salvo lacuna confirmada. Não liberar “M1” que apenas redesenha atalhos sem corrigir cobertura agente→agente e contadores.

## 11. Backlog executável

Todos os itens começam como `TODO`. Status permitidos no ledger: `TODO`, `IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`. `IMPLEMENTED` sem testes não é `VERIFIED`. Cada tarefa deve apontar evidência por arquivo/commit e teste/campanha correspondente.

### PR-00 — Baseline, fontes e contrato

**Resultado:** Nenhuma alteração de comportamento; estabelecer uma base verificável.

#### HOME-001 — Reconciliar checkout e implementação

**Estado inicial:** TODO  
**Implementação:** Registrar branch, HEAD, working tree, versão e Home atual. Comparar com o SHA de referência; preservar alterações do usuário e registrar diferenças, sem checkout destrutivo.  
**Aceite:** baseline.md com arquivos reais e dependências; nenhuma suposição silenciosa sobre main ou feature.

#### HOME-002 — Mapear origens e autorização

**Estado inicial:** TODO  
**Implementação:** Rastrear handoffs, entregas lógicas, operações, recibos, perguntas, artefatos, atenção, observação e workspace até as consultas/controles atuais.  
**Aceite:** source-map.md com permissões, correlação, atualidade, cobertura de SSE e lacunas por origem.

#### HOME-003 — Congelar semântica de apresentação

**Estado inicial:** TODO  
**Implementação:** Implementar ou especificar funções puras de classificação, agrupamento, identificadores e contadores. Registrar ADR sobre estado de visualização de resultados.  
**Aceite:** Contrato versionado e tabela de casos; OPEN, CLAIMED, SUBMITTED, RUNNING e resultado incerto continuam distintos.

#### HOME-004 — Preparar fixtures e baseline de experiência

**Estado inicial:** TODO  
**Implementação:** Criar fixtures mínimas para um agente, cooperação A→B→C, múltiplas sessões, fonte stale, resultado com cleanup e autorização revogada. Instrumentar tempos e navegação sem conteúdo privado.  
**Aceite:** Fixtures reproduzíveis e medidas locais de referência; nenhum número de produção inventado.


### PR-01 — Projeção operacional e API de leitura

**Resultado:** Leitura consolidada sem novos comandos de execução.

#### HOME-005 — Criar a fronteira de leitura da Home

**Estado inicial:** TODO  
**Implementação:** Criar HomeOverviewService e HomeOverviewQueries, ou equivalentes existentes, com contratos tipados; nenhuma dependência direta do frontend em SQL/runtime.  
**Aceite:** Portas, modelos e testes de import boundary; nomenclatura proposta reconciliada com o repositório.

#### HOME-006 — Projetar trabalho canônico

**Estado inicial:** TODO  
**Implementação:** Consultar trabalho iniciado por operador e por agentes; agregar handoff, entrega e operações com correlação comprovada; preservar tentativas e sessões como detalhes.  
**Aceite:** Atividades estáveis, sem duplicação por abertura de sessão, steer, retries ou publicação de resultado.

#### HOME-007 — Implementar escopo e agregações

**Estado inicial:** TODO  
**Implementação:** Filtrar antes de contar; separar conectividade global e atuação no workspace; contadores sobre o conjunto autorizado, não sobre a página.  
**Aceite:** Totais, lista e escopo consistentes no mesmo snapshot; desconhecido não é zero.

#### HOME-008 — Integrar pendências existentes

**Estado inicial:** TODO  
**Implementação:** Consumir projeções da Attention e referências de decisões nativas; respeitar prioridade, adiamento, destinatário e feature desabilitada.  
**Aceite:** Home recebe itens concretos e ações previstas sem criar outra fila de aprovações.

#### HOME-009 — Projetar resultados resumidos

**Estado inicial:** TODO  
**Implementação:** Consultar resultados, respostas e metadados de artefatos; classificar conclusão de turno versus entrega de handoff e erro de limpeza.  
**Aceite:** Resultados básicos disponíveis já no M1; nenhuma necessidade de ler todos os payloads.

#### HOME-010 — Publicar APIs e contratos de erro

**Estado inicial:** TODO  
**Implementação:** Adicionar /api/v1/home/overview e paginação por bloco, ou extensão equivalente; autenticação atual, limites, cache privado/no-store, revisão e respostas parciais explícitas.  
**Aceite:** Testes HTTP reais, validação de parâmetros, 401/403 tratados e ausência de efeitos de execução nos GETs.


### PR-02 — Home operacional mínima

**Resultado:** M1: entender a operação sem visitar outras telas.

#### HOME-011 — Evoluir o layout existente

**Estado inicial:** TODO  
**Implementação:** Refatorar HomeView/HomeOverview; cabeçalho compacto, resumo, Precisa de você, Em andamento, Resultados e Agentes conectados. Rebaixar atalhos grandes.  
**Aceite:** A mesma Home, não uma segunda rota concorrente; leitura útil em desktop e mobile.

#### HOME-012 — Construir lista de trabalho

**Estado inicial:** TODO  
**Implementação:** Cartões/linhas por atividade, agrupamento opcional por agente e expansão de tentativas/sessões; rótulos legíveis, motivo e tempo no estado.  
**Aceite:** Uma identidade com sessões distintas não recebe um status único enganoso; warm/idle fora de Em andamento.

#### HOME-013 — Mostrar atenção compacta

**Estado inicial:** TODO  
**Implementação:** Extrair componentes de apresentação existentes; mostrar até três ocorrências prioritárias com contexto e abrir a inspeção atual.  
**Aceite:** Uma decisão pendente abre o registro exato; não é necessário esperar um novo drawer para o M1.

#### HOME-014 — Mostrar resultados iniciais

**Estado inicial:** TODO  
**Implementação:** Resumo de resposta, resultado e artefato com referências exatas; visualização usa controles existentes e não marca visto em massa.  
**Aceite:** É possível localizar e abrir uma entrega pela Home, sem procurar outra vez na tela de destino.

#### HOME-015 — Resolver estados vazios e filtros

**Estado inicial:** TODO  
**Implementação:** Preservar workspace selecionado; usar nomes existentes; filtros rápidos de atenção/estado/agente e estados zero-agente, sem trabalho, parcial, forbidden e stale.  
**Aceite:** Zero agentes indica Conectar agente pelo fluxo plug and play; falha de leitura não mostra onboarding falso.


### PR-03 — Detalhamento e ações no contexto

**Resultado:** M2, parte 1: operar sem perder a Home.

#### HOME-016 — Generalizar referência tipada de navegação

**Estado inicial:** TODO  
**Implementação:** Criar HomeTarget/OperationalTarget para handoff, operação, sessão, mensagem, aprovação, resultado e observação; validar escopo e resolver no servidor.  
**Aceite:** Links, voltar/avançar e reabertura apontam ao mesmo objeto; URLs não carregam segredo ou conteúdo.

#### HOME-017 — Reaproveitar inspeções no painel de detalhes

**Estado inicial:** TODO  
**Implementação:** Extrair composição de AttentionInspection sem trocar as máquinas de estado internas; desktop lateral e mobile em camada acessível.  
**Aceite:** Mesmos formulários/serviços de ApprovalInspection, HandoffInspection e runtime; uma única camada ativa.

#### HOME-018 — Conectar ações canônicas

**Estado inicial:** TODO  
**Implementação:** Responder, aprovar/negar, verificar, inspecionar recuperação e interromper somente quando o contrato atual permite; revalidar antes do envio.  
**Aceite:** Conflitos e resultado incerto permanecem visíveis; não há approve genérico, retry-all ou ação por inferência.

#### HOME-019 — Adicionar pedido e continuidade contextual

**Estado inicial:** TODO  
**Implementação:** Extrair composer existente; distinguir Nova tarefa (handoff) de Conversar (mensagem); continuar somente na sessão explicitamente correlacionada.  
**Aceite:** Operador nunca personifica agente; encerramento/revogação da sessão exige novo contexto explícito, não fallback silencioso.

#### HOME-020 — Proteger rascunhos, foco e navegação

**Estado inicial:** TODO  
**Implementação:** Não remontar formulários em refresh; confirmar descarte na troca de alvo/workspace quando necessário; manter seleção, scroll e ação em curso.  
**Aceite:** SSE, filtros, Escape e botão Voltar não apagam uma resposta digitada nem redirecionam uma decisão.


### PR-04 — Resultados e leitura coerentes

**Resultado:** M2, parte 2: fechar o ciclo pedido→resultado→continuação.

#### HOME-021 — Agrupar entregas correlacionadas

**Estado inicial:** TODO  
**Implementação:** Agrupar somente relações explícitas entre resultado, resposta e artefatos; manter autores, revisão, origem e metadados separados.  
**Aceite:** Uma entrega com três arquivos não parece quatro trabalhos; ausência de correlação não é preenchida com heurística.

#### HOME-022 — Reutilizar visto por ocorrência/revisão

**Estado inicial:** TODO  
**Implementação:** Para result_unseen, reutilizar a preferência da Attention por ocorrência/revisão. Para fontes sem esse contrato, mostrar Recentes, sem contador novo fictício.  
**Aceite:** Home não altera watermark temporal global nem ACK de inbox; visualização em uma ocorrência não oculta outra.

#### HOME-023 — Abrir resultados e artefatos com segurança

**Estado inicial:** TODO  
**Implementação:** Carregar conteúdo sob demanda, com componentes existentes, limites, sanitização e autorização de origem.  
**Aceite:** Resumo não expõe payload confidencial; HTML e outros artefatos não ganham execução privilegiada.

#### HOME-024 — Concluir a interação contextual

**Estado inicial:** TODO  
**Implementação:** Depois de resposta/decisão, mostrar registro da decisão separado de aplicação no runtime; depois de entrega, permitir continuar com identidade e escopo corretos.  
**Aceite:** Ação enviada não equivale a aplicada; interação mantém correlação e recupera a mesma operação após resposta perdida.


### PR-05 — Atividade recente e atualização robusta

**Resultado:** M3, parte 1: acompanhar operação viva sem ruído.

#### HOME-025 — Auditar sinais de invalidação

**Estado inicial:** TODO  
**Implementação:** Documentar eventos que invalidam cada bloco, mudanças que só ocorrem por passagem do tempo e retenção de eventos.  
**Aceite:** Matriz fonte→evento→fallback→TTL; nenhuma confiança em SSE para mudanças sem evento comprovado.

#### HOME-026 — Compartilhar e limitar atualização

**Estado inicial:** TODO  
**Implementação:** Reutilizar stream do shell; debounce com teto, uma requisição em voo por escopo, cancelamento/geração de requests, reread após reconnect e fallback limitado.  
**Aceite:** Sem nova conexão SSE por cartão; fonte antiga não substitui resposta de escopo novo.

#### HOME-027 — Tratar paginação, revisão e relógio

**Estado inicial:** TODO  
**Implementação:** Cursores opacos por filtro/escopo/ordem e invalidação explícita; timestamps do servidor, atualidade por bloco e refresh no vencimento.  
**Aceite:** Não há skips/duplicatas silenciosos; transport live não transforma fonte stale em current.

#### HOME-028 — Adicionar feed legível

**Estado inicial:** TODO  
**Implementação:** Selecionar mudanças de negócio em templates determinísticos; agrupar bursts só quando não ocultar distinções, decisões ou falhas.  
**Aceite:** Feed limitado e correlacionado; sem tokens, heartbeats ou LLM resumindo a operação.

#### HOME-029 — Consolidar observação externa sem misturar garantias

**Estado inicial:** TODO  
**Implementação:** Incorporar projeção externa existente no bloco de agentes/atividade e em Attention; separar reportado/inferido, atual/stale e execução gerenciada.  
**Aceite:** Herdr done nunca completa handoff, libera slot ou soma como sucesso nativo; ausência da feature não bloqueia Home.

#### HOME-030 — Validar acessibilidade e responsividade

**Estado inicial:** TODO  
**Implementação:** Teclado, leitor de tela, contraste, focus restore, pause visual e largura mobile; textos seguem o idioma/padrão do frontend.  
**Aceite:** Fluxo completo sem mouse; atualizações não roubam foco; pausa visual não pausa agentes nem remove validação de segurança.

#### HOME-031 — Medir e otimizar custo

**Estado inicial:** TODO  
**Implementação:** EXPLAIN QUERY PLAN, índices aditivos necessários, contagens paginadas, payload e taxas de requests em fixtures pequenas e ampliadas.  
**Aceite:** Sem N+1 por agente/cartão; metas medidas com ambiente documentado, não alegadas por inspeção.


### PR-06 — Qualificação e rollout

**Resultado:** M3: habilitação segura da experiência padrão.

#### HOME-032 — Executar matriz integrada

**Estado inicial:** TODO  
**Implementação:** Unidade, repositório, HTTP, componente e navegador; testar flags, tenant/operador atual, escopos, sessão, revogação e concorrência.  
**Aceite:** Relatório liga cada cenário às evidências; testes Node/static não são vendidos como e2e de navegador.

#### HOME-033 — Executar campanha real isolada

**Estado inicial:** TODO  
**Implementação:** Um harness já qualificado e um fluxo local; remoto/multiagente e Herdr conforme ambientes disponíveis, sempre com consentimento e dados descartáveis.  
**Aceite:** Evidência de pedido, atividade, pergunta/decisão e resultado; registrar explicitamente o que ficou NOT_RUN.

#### HOME-034 — Implementar rollout e reversão

**Estado inicial:** TODO  
**Implementação:** Controle independente da nova apresentação; retorno à Home anterior sem parar processos, revogar grants ou desfazer migrações.  
**Aceite:** Desabilitar Home nova mantém daemon, CLI, Attention e controles originais operantes.

#### HOME-035 — Publicar documentação e diagnóstico

**Estado inicial:** TODO  
**Implementação:** Guia curto da Home, estados e limites; docs do contrato, capturas sem dados privados, troubleshooting e evidências.  
**Aceite:** Nenhuma documentação confunde sessão aberta, conexão, entrega, execução, resultado e verificação.

#### HOME-036 — Revisar contrato e critérios do produto

**Estado inicial:** TODO  
**Implementação:** Revisão final de drift, segurança, interação e UX; confirmar primeiro valor e opcionabilidade do dashboard.  
**Aceite:** Gate M3 decidido com evidências, baseline atualizado e limitações explícitas; sem deploy automático em produção.

## 12. Matriz de teste e aceite

Os cenários abaixo são requisitos, não resultados obtidos. Usar o menor nível que comprove cada regra e complementar com integração real nas fronteiras. Cada cenário terá status `NOT_RUN`, `PASS`, `FAIL` ou `BLOCKED`, caminho/saída de teste, commit, ambiente e limitação. Fixar o relógio nos testes temporais e usar barreiras determinísticas nas corridas, não sleeps frágeis.

### A. Escopo, identidade e autorização

- **HOME-T-A01 — NOT_RUN:** Projeto A não inclui atividades, pendências ou contadores de B, embora um mesmo agente exista nos dois.
- **HOME-T-A02 — NOT_RUN:** Todos os projetos é uma união autorizada, sem duplicar agente, handoff ou entrega por join.
- **HOME-T-A03 — NOT_RUN:** Um agente global sem vínculo ou atividade autorizada em A não aparece como atuante em A.
- **HOME-T-A04 — NOT_RUN:** Uma credencial de agente ou monitor não herda acesso de operador à Home.
- **HOME-T-A05 — NOT_RUN:** Revogação/logout remove payloads protegidos da lista, drawer e caches; o histórico do browser não os restaura.
- **HOME-T-A06 — NOT_RUN:** Troca A→B com resposta lenta de A não mistura dados, contadores ou formulários.
- **HOME-T-A07 — NOT_RUN:** Referência de alvo incompatível com workspace é recusada, mesmo quando o ID existe.
- **HOME-T-A08 — NOT_RUN:** Ocorrências Server-wide são identificadas separadamente e não atribuídas a todos os projetos por conveniência.

### B. Trabalho, correlação e contadores

- **HOME-T-B01 — NOT_RUN:** Sessão aberta sem turno não conta como execução em andamento.
- **HOME-T-B02 — NOT_RUN:** Instância one-shot aquecida, processo iniciando ou cleanup isolado não contam como novo trabalho produtivo.
- **HOME-T-B03 — NOT_RUN:** CLAIMED sem evidência nativa mostra Assumido, não Executando.
- **HOME-T-B04 — NOT_RUN:** SUBMITTED/native accepted sem RUNNING mostra aceitação, não conclusão nem execução confirmada.
- **HOME-T-B05 — NOT_RUN:** Um handoff com runtime.start, turn.submit, steer e retries aparece uma vez na lista principal.
- **HOME-T-B06 — NOT_RUN:** Tentativas são preservadas em detalhe e resultados de tentativa antiga não completam tentativa atual.
- **HOME-T-B07 — NOT_RUN:** Fluxo A→B sem mensagem do operator aparece na Home.
- **HOME-T-B08 — NOT_RUN:** Um agente com dois turnos/sessões mostra ambos com estados próprios, inclusive um bloqueado e outro executando.
- **HOME-T-B09 — NOT_RUN:** Mensagem informativa/broadcast não vira tarefa ou posição de fila por estar unread.
- **HOME-T-B10 — NOT_RUN:** Totais vêm do conjunto autorizado completo; paginação, limite de preview ou falha parcial não reduzem o total para o tamanho visível.

### C. Atenção e ações

- **HOME-T-C01 — NOT_RUN:** Pergunta destinada ao operador abre o pedido nativo exato e mantém suas opções/tipos.
- **HOME-T-C02 — NOT_RUN:** Pergunta destinada a outro agente permite acompanhamento, não personificação nem resposta em nome do agente.
- **HOME-T-C03 — NOT_RUN:** Aprovação expirada ou já decidida por outro cliente deixa de aceitar decisão ao revalidar.
- **HOME-T-C04 — NOT_RUN:** Duplo clique e resposta HTTP perdida recuperam a mesma intenção/operação, sem dupla decisão.
- **HOME-T-C05 — NOT_RUN:** Decisão registrada aparece separada de decisão aplicada pelo harness.
- **HOME-T-C06 — NOT_RUN:** Resultado incerto oferece inspeção e recuperação canônica, nunca retry automático.
- **HOME-T-C07 — NOT_RUN:** Item adiado continua visível no trabalho quando pertinente, mas não reaparece como prioridade em cada refresh.
- **HOME-T-C08 — NOT_RUN:** Marcar visto não aprova, cancela, conclui ou reconhece inbox; novo episódio/revisão preserva sua própria atenção.
- **HOME-T-C09 — NOT_RUN:** Attention desabilitada não impede uso dos controles canônicos originais; bloco explicita indisponibilidade.
- **HOME-T-C10 — NOT_RUN:** Interromper usa a sessão/turno selecionados e contrato atual; não encerra todos os processos do agente.

### D. Resultados e continuidade

- **HOME-T-D01 — NOT_RUN:** Turno SUCCEEDED sem handoff_complete não aparece como handoff concluído.
- **HOME-T-D02 — NOT_RUN:** Entrega em VERIFYING é apresentada como aguardando verificação, não como aceita.
- **HOME-T-D03 — NOT_RUN:** Resultado produtivo bem-sucedido com cleanup pendente mantém sucesso e pendência técnica separados.
- **HOME-T-D04 — NOT_RUN:** Resposta, resultado e artefatos explicitamente relacionados formam uma entrega legível, sem multiplicar tarefas.
- **HOME-T-D05 — NOT_RUN:** Abrir Home ou mostrar preview não avança o marcador temporal global de mensagens novas.
- **HOME-T-D06 — NOT_RUN:** Abrir/ver uma ocorrência não marca outra fora da página ou em outro projeto como vista.
- **HOME-T-D07 — NOT_RUN:** Conteúdo de artefato exige autorização própria; HTML não executa com privilégios do dashboard.
- **HOME-T-D08 — NOT_RUN:** Continuar conversa usa o contexto confirmado; sessão fechada/revogada não é substituída silenciosamente nem atribui fala ao agente original.

### E. Tempo real, atualidade e recuperação

- **HOME-T-E01 — NOT_RUN:** Resultado commitado antes de o cliente assinar SSE aparece no primeiro snapshot.
- **HOME-T-E02 — NOT_RUN:** Evento entre snapshot e assinatura/reconexão não é perdido; lacuna de retenção provoca ressincronização.
- **HOME-T-E03 — NOT_RUN:** Eventos duplicados ou fora de ordem não duplicam cartões nem fazem estados regredir.
- **HOME-T-E04 — NOT_RUN:** Burst de eventos gera atualização agrupada com teto, não uma consulta por token.
- **HOME-T-E05 — NOT_RUN:** Stream conectado com fonte externa expirada mantém badge stale da fonte.
- **HOME-T-E06 — NOT_RUN:** Expiração de autorização, TTL de observação e prazo de atenção sem evento explícito são atualizados por relógio/fallback.
- **HOME-T-E07 — NOT_RUN:** Falha de um bloco preserva outros blocos e mostra falha; 401/403 limpam o protegido.
- **HOME-T-E08 — NOT_RUN:** Duas abas podem observar; uma decisão concorrente resulta em conflito claro na aba antiga.
- **HOME-T-E09 — NOT_RUN:** Aba em background reduz trabalho; voltar revalida antes de habilitar ações sensíveis.
- **HOME-T-E10 — NOT_RUN:** Pausa de atualização visual não pausa agentes, não amplia autoridade e não permite confirmar um estado antigo sem revisão atual.

### F. Navegação e experiência

- **HOME-T-F01 — NOT_RUN:** Sem agentes, a Home oferece o onboarding plug and play existente, não formulários avançados.
- **HOME-T-F02 — NOT_RUN:** Com um agente conectado sem trabalho, a Home oferece pedido/conversa e não uma grade vazia de métricas.
- **HOME-T-F03 — NOT_RUN:** Clicar num item abre seu registro, não uma página genérica para procurar novamente.
- **HOME-T-F04 — NOT_RUN:** Fechar drawer preserva filtros, página, expansão e posição de scroll.
- **HOME-T-F05 — NOT_RUN:** Refresh com resposta digitada não remonta formulário, perde foco ou muda destinatário.
- **HOME-T-F06 — NOT_RUN:** Troca de projeto/alvo com rascunho solicita descarte quando necessário; logout limpa dados protegidos.
- **HOME-T-F07 — NOT_RUN:** Voltar/avançar/deep link revalidam alvo e autorização; referência inexistente tem saída clara.
- **HOME-T-F08 — NOT_RUN:** Home utiliza os mesmos nomes de workspace, harness, temas e convenções linguísticas do dashboard.

### G. Atividade externa

- **HOME-T-G01 — NOT_RUN:** Somente reporte externo working não é contado como execução gerenciada autorizada.
- **HOME-T-G02 — NOT_RUN:** Done do Herdr é atividade externa finalizada, não task success, ACK, claim release ou handoff_complete.
- **HOME-T-G03 — NOT_RUN:** Reportes expirados passam a desconhecido/desatualizado, nunca idle por suposição.
- **HOME-T-G04 — NOT_RUN:** Mesmo agent_id com sessão nativa e observação externa permanece distinguível; deduplicação exige associação comprovada.
- **HOME-T-G05 — NOT_RUN:** Observação sem workspace confiável não é incluída por inferência no projeto selecionado.
- **HOME-T-G06 — NOT_RUN:** Herdr ausente/desconectado ou publicação desabilitada não bloqueia Home nem modifica runtime/MCP.

### H. Acessibilidade, segurança e desempenho

- **HOME-T-H01 — NOT_RUN:** Teclado percorre filtros, cards, drawer e ações; foco retorna ao item ou a um destino estável.
- **HOME-T-H02 — NOT_RUN:** Leitor de tela recebe avisos úteis agrupados, não todo stream; estado não depende só de cor.
- **HOME-T-H03 — NOT_RUN:** Layout a 360 px, zoom 200% e desktop mantém ações acessíveis e sem overflow horizontal obrigatório.
- **HOME-T-H04 — NOT_RUN:** GETs da Home não criam mensagens, claims, grants, sessões, ACKs ou decisões; metadados de autenticação preexistentes são avaliados separadamente.
- **HOME-T-H05 — NOT_RUN:** Resumo omite credenciais, prompts completos, argumentos de ferramentas e paths privados; deep links não incluem segredos.
- **HOME-T-H06 — NOT_RUN:** Fixtures de 1, 10 e 100 agentes não aumentam queries por agente; consultas e resposta têm limites documentados.
- **HOME-T-H07 — NOT_RUN:** Carga de 1.000 atividades abertas e 100.000 eventos preserva paginação; histórico total não é serializado no overview.
- **HOME-T-H08 — NOT_RUN:** O ledger registra hardware, dataset, medições p50/p95, tamanho do payload, taxa de requests e eventuais metas não atingidas.

### I. Rollout e regressão

- **HOME-T-I01 — NOT_RUN:** Feature da Home nova OFF restaura a experiência anterior sem parar daemon, Core ou Connector.
- **HOME-T-I02 — NOT_RUN:** Migrations aditivas preservam histórico e não exigem remoção de tabelas para reverter apresentação.
- **HOME-T-I03 — NOT_RUN:** Todo o ciclo padrão pelo terminal continua funcionando sem qualquer visita à Home.
- **HOME-T-I04 — NOT_RUN:** Build empacotado inclui frontend correto e os contratos compatíveis, sem depender de dev server.
- **HOME-T-I05 — NOT_RUN:** Campanhas simuladas, navegador e harness real são registradas separadamente; cenário não executado fica NOT_RUN.

## 13. Comandos de validação e evidências

No checkout inspecionado, `frontend/package.json` define os comandos abaixo. Executá-los apenas após preparar as dependências conforme o repositório atual:

```sh
cd frontend
npm ci
npm test
npm run build
```

O script test usa testes Node em `tests/*.test.mjs`; não presumir que ele abre navegador. Localizar a infraestrutura de e2e existente e reaproveitá-la. Se não houver, propor adição mínima e justificar dependências; teste que procura strings no código não comprova foco, drawer, teclado, races de rede ou comportamento mobile.

Para Python, identificar comandos e extras em `pyproject.toml`, CONTRIBUTING e CI atuais, rodar suites focadas e regressão pertinente. Não declarar aqui um comando de campanha real sem conferir seu alvo, configuração e efeitos. Campanha com provedor requer consentimento, home descartável, workspace isolado, autorização limitada e limpeza confirmada.

Entregáveis de evidência sugeridos, sob `plans/home_evolution/` ou localização equivalente existente:

```text
baseline.md
source-map.md
contracts.md
adr-result-view-state.md
execution-ledger.json
test-ledger.json
performance.md
release-report.md
```

Relatório por PR: arquivos alterados, contratos reutilizados, mudanças públicas, migrações, comandos executados, resultados reais, cenários não executados, riscos e forma de rollback. Não anexar banco real, tokens, prompts privados ou capturas com dados pessoais.

## 14. Rollout, persistência e rollback

A primeira versão da projeção deve ser computada sobre fatos existentes. Não criar tabela home_tasks, home_queue ou home_execution_status. Preferências novas só são admitidas quando não houver contrato compartilhado equivalente, com ADR e isolamento por Server/operador/escopo apropriado.

Índices ou preferências adicionais usam migrações aditivas com a próxima revisão do checkout real; não inventar número de schema. Antes de alterar query relevante, medir o plano e o custo de escrita.

Introduzir controle independente de apresentação da Home nova ou estratégia equivalente já existente no projeto. Durante validação, permitir voltar à Home anterior. Seu estado não pode habilitar/desabilitar runtime, Attention, MCP, daemon, grants ou observações. O fallback preserva filtros quando possível e não apaga preferências de outros módulos.

Sequência: fixtures e testes → instalação isolada do pacote → um cenário real local → validação multiagente/remota conforme disponibilidade → ativação gradual acordada. Não inferir suporte a todas as plataformas/provedores a partir de uma campanha local.

Reversão operacional desabilita a nova apresentação e mantém dados/contratos aditivos. Não restaurar um banco antigo enquanto executores continuam ativos, nem reexecutar trabalho para “reconstruir” a Home. Retenção remove evidência conforme contratos existentes; a UI indica lacuna e não sintetiza fatos ausentes.

## 15. Riscos e mitigação

| Risco | Mitigação exigida |
|---|---|
| Home bonita, mas ainda limitada ao operador | Teste obrigatório A→B→C sem mensagem do operator; nova consulta de trabalho canônico. |
| Mistura de projetos | Escopo antes de agregação; testes de agentes globais e caches; dados de outro workspace nunca ficam transitórios na tela. |
| Duplicar atividade por join | Chave lógica canônica e correlação explícita; tentativas em detalhe; teste de start+submit+steer+retries. |
| Confundir idle, ready e autorizado | Fatos separados, labels verificáveis e nenhuma inferência de capacidade. |
| Perder alertas/novidades ao abrir Home | Não avançar marcador temporal global; visto por ocorrência/revisão existente; fontes sem rastreamento mostram Recentes. |
| Decisão na referência errada | Alvos tipados, leitura canônica fresca, forms estáveis e CAS/idempotência existentes. |
| SSE esconder lacunas | Snapshot inicial/reconnect, low watermark quando existente, fallback por tempo e atualização por bloco. |
| Custo alto de leitura | Agregações em lote, limites, índices medidos e sem consultar hosts/provedores em GET. |
| Poluir a Home com configuração | Só ações cotidianas; políticas e diagnóstico profundo ficam nas telas especializadas. |
| Reinventar Attention e controles | Reusar composição de AttentionInspection e serviços, sem novas filas/autoridades. |
| Regressão de adoção plug and play | E2E por terminal sem abrir dashboard como gate de release. |

## 16. Definição de pronto

M1 só passa quando dados corretos e completos no escopo — inclusive cooperação entre agentes — são compreensíveis na Home e uma pendência/resultado abre o registro exato. M2 só passa quando ações e continuidade funcionam com autorização, correlação e rascunhos preservados. M3 só passa após revisão de segurança, acessibilidade, tempo real, performance e evidência de integração, com limitações registradas.

Entrega final deve demonstrar: um agente local trabalhando, outro com pergunta/decisão, uma atividade remota quando qualificada, uma entrega recente e uma falha parcial; navegar entre projetos; resolver a decisão; observar resultado; fechar/reabrir detalhe; desconectar/reconectar sem duplicar trabalho; desabilitar Home nova sem interromper agentes. A observação externa entra como variante opcional, não condição para usar a Home.

Não aceitar uma implementação que: chama a tela de consolidada mas só agrega contadores/atalhos; oculta atividade entre agentes; declara offline como ocioso; marca resultados invisíveis como vistos; permite retry indiscriminado; ou exige reconfigurar agentes existentes para obter a visão.

## 17. Prompt de arranque para o Codex

```text
Implemente o plano PLANO_CODEX_NEXUS_HOME_OPERACIONAL_R1.md no repositório
OktoLabsAI/okto-nexus, começando pela PR-00. A referência inspecionada foi
feature/v0.3.3, SHA 4ba6fa40383a4157eb0fe5e1b9a943bf112a089b, mas use o checkout
atual acordado após registrar branch, HEAD, working tree e drift. Não faça
checkout/reset/clean destrutivo, force-push ou deploy.

Evolua HomeView existente. Não recrie daemon, onboarding, Attention ou runtime.
Corrija a cobertura de trabalho entre agentes e o escopo dos contadores antes
de apenas mudar o layout. A Home é uma projeção somente de leitura, com ações
nas APIs canônicas e detalhes no contexto. Session open não é RUNNING; turno
concluído não é handoff completo; observação externa não concede autoridade.

Reutilize AttentionInspection e controles por referência exata. Não adicione
Home à marcação temporal global de mensagens como vistas. Preserve o fluxo
completo pelo terminal e o dashboard opcional.

Antes de implementar, produza baseline, mapa fonte→permissão→correlação→SSE,
contrato de projeção/contadores e ADR do estado de visualização de resultados.
Depois siga as PRs incrementais, com testes em cada entrega, sem redesenhar
Core/Connector salvo lacuna confirmada. Use nomenclatura equivalente já
existente quando apropriado e registre desvios justificados.

Mantenha ledger de tarefas e testes; não marque VERIFIED/PASS sem executar.
Diferencie fixtures, integração HTTP, navegador e harness real. Não use dados
ou credenciais de produção. Ao concluir cada PR, informe mudanças, evidências,
limitações, migrações, rollback e o próximo incremento.
```

## 18. Fontes da inspeção

As referências abaixo fixam a base observada. São evidência de implementação estática, não de execução em produção. O Codex deve reler os arquivos no HEAD real.

- **[S01] Home atual:** `frontend/src/views/HomeView.tsx`. Leituras de graph, sessões do Meta-harness, mensagens e observação; contadores Attention; atalhos genéricos; atualização de 15 segundos.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/views/HomeView.tsx

- **[S02] Shell e navegação:** `frontend/src/App.tsx`. Home já está no menu e é a seleção inicial nesta branch. Preservar autenticação, workspace, avisos e alterações não salvas.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/App.tsx

- **[S03] Sessões do operador:** `src/okto_nexus/application/meta_harness_sessions.py`. conversation_sessions filtra mensagens originadas por operator. Não é inventário universal de trabalho entre agentes.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/src/okto_nexus/application/meta_harness_sessions.py

- **[S04] Graph e presença:** `src/okto_nexus/application/observability.py`. graph_snapshot mantém nós globais; relações e parte das contagens são por workspace. Não reutilizar contagem de nós como agentes atuando no projeto.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/src/okto_nexus/application/observability.py

- **[S05] Administração de runtime:** `src/okto_nexus/application/agent_runtime_administration.py`. overview é por agente e separa sessões de turnos finalizados. Reutilizar sem fan-out por agente na Home.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/src/okto_nexus/application/agent_runtime_administration.py

- **[S06] Contratos de atenção:** `frontend/src/attentionTypes.ts`. Ocorrências, ações, revisões, atualidade, visto/adiado e cursores já têm contratos.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/attentionTypes.ts

- **[S07] Visão de atenção:** `frontend/src/views/AttentionView.tsx`. Apresentação, foco, visto/adiado e callbacks; extrair versão compacta sem duplicar regras.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/views/AttentionView.tsx

- **[S08] Inspeção contextual existente:** `frontend/src/components/AttentionInspection.tsx`. Já encaminha referências exatas para ApprovalInspection, HandoffInspection, runtime, mensagens e observação externa.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/components/AttentionInspection.tsx

- **[S09] Stream compartilhado:** `frontend/src/useSSE.ts`. EventSource /api/v1/stream e cursor. Auditar cobertura e lacunas; comentário sobre garantias não substitui teste.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/useSSE.ts

- **[S10] Mensagens novas do operador:** `frontend/src/operatorUnread.ts`. Marcador temporal local; OPERATOR_VIEWS contém Messages e Meta-harness. Home não deve avançar o marcador global.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/src/operatorUnread.ts

- **[S11] Comandos frontend:** `frontend/package.json`. npm test usa node --test tests/*.test.mjs; npm run build usa tsc -b e vite build. Isso não comprova testes em navegador.  
  Fonte fixada: https://github.com/OktoLabsAI/okto-nexus/blob/4ba6fa40383a4157eb0fe5e1b9a943bf112a089b/frontend/package.json

- **[W01] W3C/WAI — Pause, Stop, Hide (WCAG 2.2, 2.2.2):** orientação para conteúdo autoatualizado e mecanismos de pausa/controle visual. Aplicação ao plano: permitir acompanhar sem movimento involuntário e sem confundir pausa da UI com parada de agentes.  
  https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide

- **[W02] W3C/WAI — Status Messages (WCAG 2.2, 4.1.3):** orientação para avisos de estado identificáveis por tecnologia assistiva sem mover foco. Aplicação ao plano: mensagens curtas agrupadas, não anúncio de todo o stream.  
  https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html

---

**Controle deste documento:** plano HOME-R1; implementação e campanhas pendentes. Toda alteração de requisito deve preservar os invariantes e ficar registrada junto à evidência correspondente.
