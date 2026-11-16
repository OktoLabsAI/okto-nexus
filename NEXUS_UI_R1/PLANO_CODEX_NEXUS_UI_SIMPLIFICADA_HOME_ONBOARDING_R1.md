# Okto Nexus — plano unificado de UI simples, acompanhamento na Home e onboarding

**Revisão:** UI-R1 — 16/11/2026  
**Destinatário:** Codex / agente de implementação com capacidade intermediária.  
**Estado:** especificação de trabalho; não é declaração de implementação ou testes executados.  
**Objetivo:** conectar harnesses, pedir trabalho, acompanhar a execução, intervir e receber resultados sem aprender a arquitetura interna do Nexus.  
**Conteúdo:** 47 tarefas, 145 cenários de aceite, 18 requisitos e 9 entregas incrementais.  
**Escopo obrigatório:** navegação básica/Avançado + acompanhamento único na Home + abertura da sessão exata + escolha entre retomar uma conexão e adicionar outro harness, no terminal e no onboarding acessível pela UI.  
**Princípio:** o usuário começa simples e continua podendo usar o padrão. Avançado serve para personalizar e investigar; não é uma etapa obrigatória do uso normal.

## Como entregar este plano ao executor

Entregar este Markdown e `NEXUS_UI_EXECUTION_LEDGER_R1.json` ao Codex. Usar o prompt de `PROMPT_CODEX_NEXUS_UI_R1.md`. O Markdown define comportamento; o JSON registra execução. Os IDs de requisitos, tarefas e cenários precisam permanecer rastreáveis. Não marcar uma tarefa como validada apenas porque seu arquivo foi criado.

Não começar implementando todos os capítulos ao mesmo tempo. Executar os incrementos da seção de backlog, respeitando dependências e os critérios de aceite. Antes de editar, reconciliar o checkout real com a referência abaixo. O usuário informou que outro trabalho da Home está sendo commitado gradualmente: preservar esse trabalho e incorporar mudanças, em vez de recomeçar a Home.

---

# 1. Base consultada, evidências e precedência

## 1.1 Snapshot da inspeção

| Componente | Referência consultada | Situação observada |
|---|---|---|
| Nexus | `feature/v0.3.4` — `3d95aad8c1b5d2e6354cd872512586fd7a02aec9` | `pyproject.toml` e frontend declaram 0.3.4; dependência Core fixada em 0.0.14. |
| Último commit dessa branch na consulta | `feat(home): isolate Server attention and preserve scoped source reads` — 16/11/2026, 15:38:46 UTC | Posterior ao corte `6b3e8e8` discutido anteriormente. Não presumir que continuará sendo o HEAD. |
| Connector | `feature/v0.0.12` — `a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b` | Referência de compatibilidade dos fluxos de onboarding e daemon remoto; não inferir ordem cronológica de todas as branches pelo número no nome. |
| Core | Dependência 0.0.14 do Nexus consultado | Não foi feita nova auditoria integral do Core. Alteração de protocolo não é necessária por padrão neste escopo. |

Fontes: [S01–S03], [S14]. Inspeção estática de arquivos selecionados e dos registros do projeto. Não executei suites, navegador, processos Nexus/Connector ou harnesses reais para elaborar este documento. Os relatos de testes no ledger existente pertencem aos autores desse ledger e ao corte que eles registraram; não são testes executados nesta elaboração.

## 1.2 O que já existe e deve ser aproveitado

| Evidência no snapshot | Consequência obrigatória |
|---|---|
| `App.tsx` contém Home, Attention, Graph, Messages, Handoffs, Meta-harness, Events, Artifacts, Memory, Workspaces, Agents, Registry, Policies, Guardrails, Communication, Approvals, Runtimes, Execution log e Settings. [S04] | Mudar organização e rótulos, não remover capacidades ou reimplementar todas as páginas. |
| A Home operacional usa `OperationalHome`, `useHomeOverview`, alvos tipados, composer e inspeções canônicas. [S05–S08] | Evoluir esse conjunto. Não criar uma terceira Home. |
| A Home operacional ainda depende de `localStorage['okto-nexus-home-operational'] === 'enabled'`. [S04] | Tratar transição/fallback explicitamente. O básico não pode perder perguntas e aprovações durante o rollout. |
| A composição atual tem listas distintas para Needs you, Work, Results, Agents, External reports e Recent activity. [S05] | Este plano substitui a apresentação simultânea dessas listas por um acompanhamento principal único. Preservar suas fontes e regras. |
| `HomeTarget` representa execução/resultado com `operation_id`, mas não possui alvo autônomo de sessão. [S07–S08] | Adicionar alvo de sessão para abrir um harness ocioso ou sessão sem operação selecionada. Não inventar `operation_id`. |
| `SessionTerminalModal` e `RuntimeTerminal` já mostram sessão, histórico e saída somente leitura. [S09–S10] | Extrair/reutilizar o corpo visual e a leitura. Não construir PTY, shell web ou segundo viewer. |
| `connect.py` deriva o perfil implícito do caminho do projeto; escolhas explícitas diferentes conflitam com o perfil salvo. [S11] | Implementar seleção de conexão antes de decidir criar/reusar perfil. Esse trabalho é obrigatório. |
| `connect` inicia/reutiliza Server, revisa o setup e entra no prompt interativo; `work` possui retomada e controles canônicos. [S12–S13] | Preservar esse caminho. A nova UI não cria dependência de navegador. |
| Connector tem wizard, retomada de checkpoints, aprovações remotas e daemon; o wizard interativo rejeita JSON/noninteractive. [S15] | Implementar a escolha de conexão usando seu armazenamento/contratos reais. Não supor que seu CLI é idêntico ao do Server. |
| A correção mais recente isola Attention global do Server e preserva evidência do destinatário ao filtrar remetente. [S06] | Manter essas correções na nova projeção. Um filtro do usuário não apaga fatos necessários à classificação. |

O ledger da Home registra ainda pendências de qualificação, pacote e desempenho. Ler sua versão atual antes do trabalho. Uma interface simplificada não autoriza apagar, dispensar ou reclassificar como resolvido um bloqueio anterior. [S16]

## 1.3 Relação com os planos anteriores

Este é o plano unificado para a evolução discutida depois de `PLANO_CODEX_NEXUS_HOME_OPERACIONAL_R1.md` e da revisão R3 de integração/onboarding. Ele é autocontido para o escopo atual.

**Substitui expressamente:** o layout com várias listas paralelas da Home; a exposição de todas as páginas na barra lateral; o tratamento de adicionar outro harness como item complementar/opcional.

**Preserva:** projeções corretas da Home, cobertura agente→agente, atenção canônica, vistos por ocorrência, autorização, correlação, histórico, daemon, setup transacional, identidade persistente e uso cotidiano pelo terminal.

Não reiniciar os ledgers anteriores nem renumerar seus testes. Criar um ledger UI-R1 e registrar quais evidências antigas foram reutilizadas, em qual SHA e por que continuam aplicáveis. Implementação reaproveitada precisa passar pelos cenários novos que a afetam.

---

# 2. Objetivo do produto e requisitos fechados

## 2.1 Jornada essencial

O usuário quer: **“Tenho um ou mais harnesses. Quero colocá-los para trabalhar juntos, ver o que estão fazendo, responder quando necessário e encontrar o que entregaram.”**

A interface básica deve cobrir: conectar → selecionar/continuar contexto → pedir → acompanhar → responder/autorizar quando permitido → receber resultado → voltar a trabalhar.

Não exigir compreensão prévia de profile, binding, executor, claim epoch, grant, policy, catálogo de capacidades ou receipt. Esses conceitos continuam existindo e ficam explicados nos detalhes quando forem relevantes.

## 2.2 Requisitos obrigatórios

| ID | Requisito |
|---|---|
| R01 | Barra lateral com quatro destinos principais: Home, Conversas, Grafo e Artefatos. |
| R02 | Uma única entrada secundária Avançado, organizada por finalidade; não expandir todas as opções avançadas na barra principal. |
| R03 | Home com uma única região principal de acompanhamento, reunindo trabalho, harness/sessão, perguntas e resultados relacionados. |
| R04 | Não criar menu/tela adicional de Harnesses, Execuções, Sessões ou Monitoramento. |
| R05 | Clicar em uma atividade/sessão abre seu contexto exato dentro do Nexus, num painel contextual, sem procurar novamente em outra página. |
| R06 | Múltiplas sessões/harnesses da mesma identidade permanecem distinguíveis; trabalho iniciado por agentes também aparece. |
| R07 | Perguntas, aprovações, problemas e resultados fazem parte do básico; não ficam disponíveis somente em Avançado. |
| R08 | Indicador global de pendências acessível em qualquer página, inclusive na Home clássica durante a transição. |
| R09 | Adicionar outro harness ao mesmo projeto é obrigatório e não exige o usuário inventar nome de perfil. |
| R10 | Retomar conexão, continuar sessão e recuperar envio pendente são intenções distintas, apresentadas corretamente. |
| R11 | Terminal continua completo; `connect` preserva inicialização/reutilização do serviço e o dashboard continua opcional. |
| R12 | Reconectar não recria identidade, não reaplica defaults, não renova grants nem repete tarefas. |
| R13 | Usar serviços e componentes canônicos; não criar domínio paralelo de trabalho, decisões ou execução. |
| R14 | Simplicidade visual não remove autorização, revisão, limites, auditoria ou tratamento de resultado incerto. |
| R15 | Configurações e links antigos continuam acessíveis; rótulos amigáveis não quebram identificadores internos. |
| R16 | Falhas, dados antigos, partes inacessíveis e suporte ausente são explícitos, nunca apresentados como vazio/ocioso/sucesso. |
| R17 | Mesmo fluxo semântico de retomar/adicionar no Nexus local, no atalho da UI e no Connector remoto, respeitando autoridades distintas. |
| R18 | Entrega final exige navegação simplificada e onboarding múltiplo funcionando; não é concluída com apenas a alteração visual. |

## 2.3 Não objetivos

Não criar novo orquestrador cognitivo, motor de workflow, multiplexer PTY, emulador completo de terminal, gateway de credenciais, servidor MCP no Connector, framework genérico de dashboards ou migração ampla de frontend.

Não redesenhar Graph, editor de políticas ou catálogo de artefatos. Reposicionar e oferecer links contextuais suficientes. Não implementar novas integrações de harnesses nem transformar observação externa em execução nativa.

Não ampliar permissões padrão, instalar serviço sem consentimento, habilitar feature administrativa por navegação ou introduzir cobrança/telemetria externa. Não fazer deploy, release, force-push, reset/clean destrutivo, alteração na instalação pessoal ou testes pagos sem autorização específica.

---

# 3. Arquitetura de informação: básico e Avançado

## 3.1 Estrutura aprovada

```text
NEXUS
  Home
  Conversas
  Grafo
  Artefatos

  Avançado

Cabeçalho: Projeto ▾   Pendências (contador)   Preferências/Ajuda/Conta
Home: Novo pedido    Conectar agente
```

“Conversas” é o nome público da atual Meta-harness. Não é o histórico técnico da página Messages. “Conectar agente” descreve a finalidade; dentro do fluxo usar nomes de harnesses familiares. Não adicionar um quinto destino básico “Agentes” apenas para alcançar o onboarding.

**Padrão linguístico:** o frontend inspecionado usa inglês. Implementar os rótulos `Home`, `Conversations`, `Graph`, `Artifacts`, `Advanced` se esse padrão continuar no checkout. As descrições em português neste plano definem significado, não exigem reescrever a aplicação ou adicionar internacionalização. Havendo i18n posterior, usar o mecanismo existente. Não misturar idiomas na mesma navegação.

## 3.2 Destino exato de cada área atual

| Área atual | Destino | Nome público sugerido | Acesso essencial preservado |
|---|---|---|---|
| Home | Principal | Home | Acompanhamento único, novo pedido e conexão. |
| Meta-harness | Principal | Conversas / Conversations | Conversar, delegar trabalho e continuar contexto. |
| Graph | Principal | Grafo / Graph | Inspecionar fluxos, mensagens e handoffs graficamente. |
| Artifacts | Principal | Artefatos / Artifacts | Buscar e abrir entregas; também links no contexto de execução. |
| Attention | Sem item lateral próprio | Pendências / Needs attention | Sino global e filtro Precisa de você da Home; fila integral sob demanda. |
| Agents | Avançado → Agentes e execução | Administração de agentes | Conectar agente permanece como ação básica; editar configuração fica no contexto/Avançado. |
| Runtimes | Avançado → Agentes e execução | Administração de execução | Acompanhamento normal na Home; diagnósticos de runtime aqui. |
| Registry | Avançado → Agentes e execução | Tags e capacidades | Não exigir cadastro manual desses itens no setup padrão. |
| Communication | Avançado → Agentes e execução | Estilos de comunicação | Não confundir com Conversas ou histórico de mensagens. |
| Policies | Avançado → Políticas e controle | Políticas | Decisões pendentes continuam no básico. |
| Guardrails | Avançado → Políticas e controle | Regras de proteção | Motivo de recusa continua legível no trabalho; edição granular aqui. |
| Approvals | Avançado → Políticas e controle | Histórico e administração de aprovações | Aprovar/negar pedido corrente pelo painel básico, com autoridade válida. |
| Messages | Avançado → Histórico e diagnóstico | Histórico de mensagens | Abrir mensagem específica pelo Graph/Home/Conversas sem buscar de novo. |
| Handoffs | Avançado → Histórico e diagnóstico | Delegações de trabalho | Criar/acompanhar handoff no básico; Kanban e investigação completa aqui. |
| Events | Avançado → Histórico e diagnóstico | Eventos | Timeline contextual no painel; fluxo bruto e filtros completos aqui. |
| Execution log | Avançado → Histórico e diagnóstico | Registros de execução | Motivo resumido no básico, registro técnico aqui. |
| Workspaces | Avançado → Histórico e diagnóstico | Saúde e análise dos projetos | Seleção de projeto continua global; não tornar diagnóstico obrigatório. |
| Memory | Avançado → Sistema e dados | Memória compartilhada | Respeitar feature flag; não ativar pela visibilidade. |
| Settings | Avançado → Sistema e dados | Configurações do sistema | Tema/ajuda/conta simples ficam no cabeçalho; operações sensíveis não. |

Métricas, retenção, reset, transporte, limites globais e configuração de serviço ficam em Sistema e dados, usando as telas existentes quando disponíveis. Não expor tudo como novos itens. Controles de autenticação/saída permanecem acessíveis globalmente; localizar configuração de acesso remoto por atalho para a seção existente quando necessária, sem copiar o formulário.

## 3.3 Página Avançado

Uma única página índice com os quatro grupos acima, descrição de uma linha por destino e links para páginas já existentes. Opcional de implementação apenas quanto ao mecanismo visual: a página é obrigatória; busca local simples de rótulos pode ser incluída se já houver componente reutilizável, mas não bloqueia a entrega.

Ao abrir um destino avançado, a barra lateral principal continua com quatro destinos e Avançado. Destacar Avançado como seção atual e mostrar breadcrumb `Avançado > Grupo > Página`. Não renderizar mais dezessete itens laterais. Voltar à Home é uma ação direta.

Não criar um “modo avançado” persistente que mude permissões ou espalhe todos os controles pela UI. Avançado é organização de navegação. Links diretos a páginas antigas continuam válidos sob a autorização atual; não exigir visitar o índice primeiro.

## 3.4 Registro central de navegação

Separar identificador interno de rótulo público. Exemplo conceitual, não um patch pronto:

```typescript
interface NavigationEntry {
  id: string;                 // ID interno estável; mapear o View atual
  label: string;              // rótulo público, não chave de lógica
  placement: 'primary' | 'advanced' | 'utility';
  advancedGroup?: 'agents' | 'governance' | 'diagnostics' | 'system';
  visibleWhen?: string;       // referência a capacidade/flag já existente
}
```

Preservar inicialmente os identificadores atuais ou criar aliases determinísticos. O rótulo Conversations não deve mudar acidentalmente os comparadores de `OPERATOR_VIEWS`, seleção salva, notificações, callbacks `onNavigate`, testes ou links de ajuda. Não substituir strings globalmente por busca-e-troca.

Centralizar resolução de destino e validação de parâmetros; manter o roteamento atual quando suficiente. Não adicionar um router novo apenas para obter este agrupamento. Se o histórico de browser necessitar extensão, fazê-la de forma localizada e com testes de voltar/avançar.

## 3.5 Divulgação contextual e ponte para configurações

No painel de uma execução pode existir `Mais opções > Configurar esta conexão`, apontando ao registro correto em Avançado. No erro de política pode existir `Ver regra aplicada`, somente para quem pode lê-la. No artefato, abrir o preview existente. Não forçar navegação para o índice e pesquisa manual do objeto.

Ocultar editor não altera enforcement. Desativar a feature de interceptação de novas aprovações não deve esconder solicitações antigas que ainda podem ser decididas, conforme contrato existente. A mesma regra vale para qualquer tela movida.

---

# 4. Home minimalista: uma lista principal, não outro dashboard de listas

## 4.1 Anatomia da página

1. Cabeçalho curto: Home, escopo de projeto, estado de atualização e ações Novo pedido/Conectar agente.
2. Linha compacta de resumo/filtros: Em atividade, Precisa de você, Resultados e Todos. São filtros do mesmo conjunto, não blocos independentes.
3. **Uma região principal `Acompanhamento`**, com agrupamento/expansão conforme necessário.
4. Aviso compacto de infraestrutura apenas quando existir incidente global relevante; abrir detalhes sob demanda.

Remover da composição padrão a exibição simultânea das listas Needs you, Work, Results, Agents, External reports e Recent activity. Não remover suas fontes, endpoints ou regras ainda usados por outras superfícies. Resultados e pendências entram na linha/grupo a que pertencem; histórico/eventos aparecem no painel ou no filtro pertinente.

A faixa de Server introduzida no último commit permanece semanticamente separada do projeto, mas não deve ser um painel vazio permanente. Quando não há incidente global, não ocupa espaço. Quando há, mostrar aviso e contador verdadeiro; a lista completa é aberta pelo mesmo painel global de pendências.

## 4.2 Estrutura textual ilustrativa

```text
Home                         Projeto: Nexus ▾        Pendências 2
                             [Novo pedido] [Conectar agente]

Em atividade 3   Precisa de você 2   Resultados 1   Todos

Codex · Implementador                     Neste computador
  Ajustar navegação   Executando há 3 min              [Abrir]

Claude · Revisor                          Neste computador
  Revisar alterações  Aguardando sua resposta          [Responder]
  “Manter compatibilidade com os links antigos?”

Codex · Testador                          Máquina remota
  2 sessões: uma executando, outra sem trabalho          [Expandir]

Pi · Documentador
  Documentação entregue · 2 arquivos                    [Ver resultado]

Claude · Assistente
  Conectado · nenhuma execução observada                [Conversar]
```

O exemplo não presume que todo agente tem o mesmo tipo de conexão ou que “conectado” significa apto a executar. Rótulos derivam de evidência e do contexto real. Todos os itens vêm de uma única região paginada; expansão não cria outra página.

## 4.3 Modelo de apresentação e unidade de agrupamento

Usar duas camadas, ambas projeções de leitura:

**Grupo de contexto:** conexão gerenciada + agente + workspace + host/harness, quando esses vínculos existem. Um agente no mesmo projeto com dois harnesses/hosts pode formar dois grupos. Um mesmo harness com vários agentes também forma grupos distintos. Nunca agrupar só por nome “Codex”.

**Item dentro do grupo:** atividade lógica canônica; sessão sem atividade representada; conexão sem sessão; observação externa; ou ocorrência sem atividade correlacionada. Quando há um único item, apresentar uma linha compacta sem expansão obrigatória. Quando há vários, mostrar resumo e permitir expandir os itens individualmente.

O usuário sempre consegue chegar à sessão exata. Nenhum grupo pode escolher silenciosamente a sessão mais recente. Para atividade com mais de uma sessão legítima, o painel oferece seletor explícito com projeto, host e estado.

**Trabalho sem conexão definida:** handoff ainda não assumido, fila sem executor escolhido ou mensagem de participante externo permanece como item de trabalho no mesmo acompanhamento. Usar “Aguardando responsável”/“Execução externa”, não fabricar sessão, binding ou host. Trabalho sem agente atribuído pode ter grupo próprio por atividade.

**Cooperação:** um handoff filho delegado a outro agente é atividade distinta e pode aparecer em outro grupo, com referência ao pai. Não colapsar uma cadeia inteira sob o planejador; mostrar quem realmente executa cada parte.

## 4.4 Regras de não duplicação

- Handoff é o item canônico quando existente. Operações, recibos, retries e resultados vinculados são conteúdo desse item.
- Sem handoff, usar a entrega lógica de conversa, ou operação direta quando não houver entrega correspondente.
- Sessão coberta por atividade já exibida não vira outro item irmão “harness executando”. Sua referência continua disponível no item.
- Sessão sem trabalho correspondente aparece como item próprio. Não desaparecer com harness ocioso apenas porque não há task.
- Conexão sem sessões aparece somente quando não estiver representada por um item daquele mesmo contexto e houver razão para mostrá-la.
- Resultado, pergunta e artefato correlacionados enriquecem o item; não geram uma segunda cópia em outro painel. Resultado sem pai retido pode aparecer como item independente com proveniência explícita.
- Observação externa só se une ao contexto nativo mediante associação persistida verificável. Nome, PID, hostname e `agent_id` isolados não provam equivalência.
- Estados parciais não autorizam criar placeholders duplicados para “compensar” fontes ausentes.

Um grupo pode conter vários itens; isso não significa várias tarefas quando os itens forem sessões ociosas. Contagens do resumo continuam baseadas no objeto lógico correspondente, não no número de grupos/linhas.

## 4.5 Cobertura e paginação

Não concatenar as primeiras páginas de work/results/agents e deduplicar em React: isso omite sessões, gera grupos incompletos e totais incorretos. A projeção de grupos precisa conhecer relações e escopo **antes da paginação**.

Retornar grupos com contadores de filhos e pequena prévia. Na expansão, consultar mais filhos com cursor do grupo. Nunca apresentar “2 sessões” quando apenas se conhece o limite retornado; usar contagem exata ou indicação de parcialidade.

Padrão proposto: 10 grupos por página, até 3 itens de prévia por grupo expandido; detalhes de transcript fora do overview. Parâmetros são limites de carga, não truncamento silencioso. Todas as páginas permanecem acessíveis na mesma Home.

## 4.6 Filtros e comportamento padrão

A primeira leitura inclui trabalho não terminal, sessões vivas conhecidas, conexões relevantes e resultados recentes. Resultados terminais dos últimos 24 h são uma janela inicial de apresentação; resultados não vistos rastreados permanecem alcançáveis independentemente dessa janela, dentro da retenção real. Não mudar retenção para atender ao filtro.

Filtros rápidos, mutuamente selecionáveis na mesma lista: **Em atividade**, **Precisa de você**, **Resultados**, **Todos**. “Em atividade” inclui execução e esperas de trabalho, com discriminação de estado. “Todos” inclui conexões sem trabalho; offline sem trabalho pode ficar em filtro detalhado, sem retirar quem tem pendência não resolvida.

No filtro Precisa de você, incluir somente ocorrências destinadas ao operador e atualmente acionáveis ou que exigem sua inspeção. Pergunta dirigida a outro agente pode manter o item aguardando, mas não entra como resposta humana devida. O sino global permite acessar ocorrências adiadas/resolvidas conforme a fila existente.

Filtros adicionais de agente, harness, host e estado ficam em um controle compacto, não como formulário técnico permanente. Aceitar busca por nome/assunto se puder reaproveitar mecanismo local/consulta autorizada; não tornar embeddings um requisito da Home.

## 4.7 Ordenação e estabilidade

Ordenação inicial: ação humana necessária → resultado incerto/problema → executando → aguardando → resultado recente não visto → conectado sem trabalho. Dentro de cada faixa usar timestamp canônico e desempate estável.

Enquanto houver leitura/edição, não mover a linha sob o cursor nem reordenar grupos que o usuário está expandindo. Agregar atualizações e oferecer “Há atualizações” quando a aplicação imediata deslocaria o foco. O estado pode mudar no texto sem trocar o alvo da ação em andamento.

Ao handoff ganhar executor, seu grupo pode mudar, mas seu ID lógico e alvo selecionado permanecem. Fechar o painel deve retornar ao item no novo grupo se ainda estiver visível; caso contrário, a um ponto estável da lista. Não abrir outro trabalho por ocupação da posição antiga.

## 4.8 Estados de evidência e texto

| Fato | Texto admitido | Inferência proibida |
|---|---|---|
| Conexão configurada | Configurado | Sessão ativa, login válido ou tarefa concluída. |
| Executor conectado | Conectado | Capacidade livre ou autorização de execução. |
| Sessão aberta, sem turno | Sem trabalho em andamento | Inativo para sempre ou disponível para qualquer tarefa. |
| Pool aquecido | Instância preparada, em detalhes | Nova tarefa produtiva. |
| Claim sem turno confirmado | Assumido | Executando. |
| Aceitação nativa sem RUNNING | Recebido pelo harness | Trabalho concluído. |
| RUNNING corrente | Executando | Progresso percentual inferido. |
| Pergunta ao operador | Aguardando sua resposta | Qualquer agente/operador pode responder. |
| Turno SUCCEEDED, handoff aberto | Resposta disponível; trabalho pendente | Handoff concluído. |
| COMPLETED canônico | Trabalho concluído | Todas as tarefas dependentes também concluíram. |
| Falha de cleanup após sucesso | Resultado disponível; limpeza pendente | Reexecutar trabalho produtivo. |
| Resultado desconhecido | Resultado não confirmado | Não houve efeitos ou retry é seguro. |
| Telemetria externa | Reportado/inferido, com origem e atualidade | Garantia nativa ou acesso a transcript inexistente. |
| Fonte sem atualização | Informação desatualizada | Ocioso, morto ou erro definitivo. |

Tempo é “há quanto tempo neste estado” somente se houver timestamp da transição. Caso contrário, escrever “iniciado há…” ou “última atualização…”. Não reutilizar `created_at` como se provasse início de inferência.

## 4.9 Vazio, falha e simplicidade proporcional

Sem agente/conexão confirmada: uma chamada `Conectar primeiro agente`. Uma conexão sem trabalho: mostrar seu nome e `Fazer pedido`. Não apresentar seis painéis vazios ou uma parede de indicadores zero.

Erro de leitura não ativa onboarding de “nenhum agente”. Timeout de uma fonte não limpa todas as outras. Dados antigos do mesmo Server/operador/escopo podem permanecer com aviso; 401/403/revogação limpam conteúdo protegido. Sessão histórica removida pela retenção mostra indisponibilidade, sem reconstrução por texto de log.

---

# 5. Painel contextual de execução, sessão e interação

## 5.1 Composição

Uma única camada contextual reutilizável, na Home e nos atalhos autorizados do Graph/Conversas/Artefatos. Desktop em drawer; mobile em camada de tela inteira com retorno ao mesmo lugar. Reutilizar `AgentActionModal`/`HomeInspection` e os corpos de inspeção existentes.

Conteúdo do painel:

- Cabeçalho: agente, harness, projeto, host resumido e estado.
- Pedido/objetivo e autor, quando autorizados.
- **Acompanhamento da sessão:** live tail/histórico existentes, com seleção explícita quando houver várias sessões.
- Perguntas e aprovações pertencentes à sessão/atividade, usando os formulários atuais.
- Resultado e artefatos relacionados.
- Detalhes técnicos recolhidos: IDs, recibos, tentativas, revisão, diagnóstico e links para Avançado.

Essas áreas podem ser abas/seções internas do mesmo painel, sem novos menus laterais. Abertura inicial escolhe a área correspondente à intenção: Acompanhar → saída; Responder → pedido nativo; Ver resultado → entrega. Não trocar a sessão selecionada para outra por conveniência.

## 5.2 Reuso do terminal

`RuntimeTerminal` é apresentação de eventos registrados, somente leitura. `SessionTerminalModal` coordena estado e histórico por sessão. Extrair um corpo `SessionExecutionPanel` ou equivalente sem modal próprio, mantendo wrappers antigos para os consumidores atuais.

Não montar um modal dentro do drawer para cada clique. O maximizar do terminal atual cria outro dialog; adaptá-lo para ampliar o mesmo painel quando embutido na Home, mantendo o comportamento dos consumidores fora dela. Um único gerenciador de foco/cancelamento precisa controlar a camada ativa.

Mostrar “somente leitura” na saída. Continuar a conversa, responder perguntas, aprovar e interromper são controles separados, com efeito explícito. Texto digitado na conversa nunca vira resposta de permissão implicitamente.

O acompanhamento só mostra eventos que o Nexus realmente captura e o operador pode ler. Não prometer acesso integral ao contexto interno, memória do modelo ou TUI nativa de um processo externo.

## 5.3 Novo alvo autônomo de sessão

Estender o contrato existente com `kind: 'session'`, mantendo Server, executor, workspace e session ID. `operation_id` não é obrigatório para inspecionar uma sessão. Também prever alvo de conexão sem sessão, se necessário para o estado conectado/ocioso.

Atualizar juntos: tipo TypeScript, parser/encoder allowlist, validação HTTP, resolver canônico, tradução para inspector e testes de ida/volta. Resposta resolvida inclui o escopo real; conferir igualdade dos identificadores relevantes antes de renderizar dados ou habilitar ação.

Não representar sessão com `operation_id: ''`, `latest`, ID da última operação conhecida ou ID fabricado. Alvo inexistente/retido é indisponível, não redirecionado para a sessão mais nova.

## 5.4 Estado e ações

Ao abrir, revalidar o alvo. Perguntas possuem revisão, destinatário e prazo; decisões revalidam no envio. Idempotência e recuperação após resposta perdida usam os controles canônicos existentes. Decisão registrada, enviada e aplicada pelo harness são fatos separados.

Interromper exige o turno/sessão correto; não interromper irmãos. Cancelar handoff e interromper turno não são sinônimos: apresentar rótulos e avisos distintos. Não oferecer botão genérico “Resolver” que esconda esse efeito.

Enquanto chega output, manter seleção, scrollback e rascunho. Pausar visualização não interrompe agentes. Voltar/fechar respeita alterações não salvas; logout/revogação limpa o sensível. Se a sessão termina com o painel aberto, transitar para histórico do mesmo ID, sem iniciar outra.

## 5.5 Fila global de pendências

Sino global abre o corpo da Attention em um painel/lista sob demanda. Reutilizar controller e ações; não criar segundo contador/fila independente. Quando houver rascunho no painel, respeitar guard antes de trocar alvo. Não empilhar dois drawers.

O badge global é independente do filtro de projeto; o conteúdo informa seu escopo. Ocorrência ligada ao projeto atual pode levar à linha correspondente ou abrir o alvo exato. Ocorrência de outro projeto oferece troca explícita/aviso contextual; não vazar seu conteúdo em um projeto sem autorização.

Pendências do Server não são contadas como trabalho de todos os projetos. Sem incidente global, nenhuma faixa extra. Atenção antiga/resolvida/adiada pode ser consultada sem ocupar o estado inicial da Home.

---

# 6. Resultados, mensagens, artefatos e vistos

Resultado e atividade são partes da mesma linha quando há relação persistida. Ao concluir, a linha muda de estado; ela não é copiada para outro painel. O filtro Resultados seleciona essas linhas/entregas. Artefatos continuam tendo seu catálogo principal porque o usuário explicitamente quer acesso direto a eles.

Agrupar resultado, resposta e arquivos somente por referências comprovadas. Sem relação, apresentar proveniência distinta. Uma entrega com três arquivos não vira quatro tarefas; um handoff pai com três filhos não vira uma só execução.

Preservar `result_unseen` e revisão/preferência da Attention. Uma prévia não marca visto. Abrir a Home não avança o watermark global de mensagens. Onde não existe rastreamento confiável, usar Recentes/`not_tracked`, sem contador exato inventado de novidades.

Marcar visto é ação explícita no escopo da ocorrência. Não é inbox ACK, aceitação de entrega, verificação de handoff ou aprovação nativa. Revisão nova pode voltar a aparecer. A paginação não pode marcar conteúdo não carregado.

Previews e títulos usam campos autorizados com limites; sem LLM para inventar resumos. Payload completo carregado sob demanda, aplicando as regras atuais de privacidade, redação de segredos e segurança de artefatos. HTML não recebe privilégios do dashboard. URLs não carregam chaves, prompts ou respostas.

---

# 7. Modelo de leitura e integração sem reescrever a Home

## 7.1 Fronteiras

Frontend → adapter HTTP atual → aplicação Home → consultas/projeções duráveis atuais. Nenhum GET do overview inicia sessão, faz probe, consome grant, reivindica trabalho ou consulta o provedor. Metadados de autenticação que o sistema já toca são tratados separadamente e não justificam outros efeitos.

Server continua responsável por identidade, autorização, mensagens, handoffs e despacho. Core continua executor. Connector continua host remoto. A Home não possui processos nem usa PID como autoridade.

## 7.2 Projeção unificada

Criar uma projeção `HomeEntryGroup`/`HomeEntry` na fronteira atual da Home, não novas tabelas de tarefas. Reutilizar os modelos existentes de atividade, resultado, Attention e observação por referência.

Contrato conceitual a finalizar na primeira entrega; nomes propostos podem ser adaptados a equivalentes já existentes, com mapa de correspondência:

```typescript
type EntryKind = 'work' | 'session' | 'connection' | 'external' | 'attention';
interface SessionRef {
  server_id: string;
  executor_id: string;
  workspace_id: string;
  session_id: string;
}
interface HomeEntry {
  id: string;                         // estável, derivado da origem
  kind: EntryKind;
  source_ref: HomeSourceRef;           // reutilizar tipo atual
  workspace_id: string | null;
  agent_id: string | null;
  title: string;
  harness_label: string | null;
  host_label: string | null;
  display_state: string;
  evidence: 'confirmed' | 'reported' | 'inferred' | 'unknown';
  sessions: SessionRef[];             // referências limitadas; mais por cursor
  sessions_total: number | null;
  attention_refs: string[];
  result_refs: string[];
  target: HomeTarget | null;           // incluindo o novo kind session
  as_of: string | null;
  next_refresh_at: string | null;
}
interface HomeEntryGroup {
  id: string;
  server_id: string;
  executor_id: string | null;
  workspace_id: string | null;
  agent_id: string | null;
  binding_ref: string | null;
  label: string;
  children: HomeEntry[];
  children_total: number | null;
  has_more_children: boolean;
  children_cursor: string | null;
}
```

Não copiar esse exemplo com campos `any` ou enums livres sem validação. Os DTOs finais devem manter fonte, revisão, atualidade, escopo, limites, relações e capacidades efetivas necessárias. IDs são referências, nunca prova de acesso. Ações são tipos conhecidos resolvidos por handlers, não URLs arbitrárias enviadas por um agente.

## 7.3 Ordem de construção da consulta

1. Autenticar operador e resolver escopo autorizado.
2. Fixar relógio/snapshot local curto para fontes do mesmo SQLite.
3. Obter handoffs, entregas produtivas e operações diretas relevantes, com suas relações canônicas.
4. Relacionar sessões atuais/históricas necessárias, bindings e host/harness sem chamadas por linha.
5. Incorporar pendências e resultados por referências; preservar as evidências do destinatário mesmo quando o filtro visual é por remetente.
6. Acrescentar sessões/conexões ainda não representadas; depois observações externas sob os limites de associação.
7. Calcular grupos, ordenação, totais e cursores depois do escopo e da deduplicação.
8. Serializar prévias pequenas, sem transcript completo nem conteúdo integral de artefato.

Resultados globais/Server são uma partição própria. Não exigir `workspace_id = null` em tabelas que não admitem isso para fabricar caso de teste. Usar as portas/famílias atuais, conforme a correção A08 já entregue.

## 7.4 Endpoints e compatibilidade

Preferência de implementação: acrescentar a projeção de acompanhamento à família Home existente, com uma rota de leitura paginada `GET /api/v1/home/entries` e uma leitura de filhos por grupo, se o contrato atual não puder fornecê-los corretamente. As rotas são **propostas**, não comandos disponíveis.

A rota principal retorna grupos, resumo, aviso global compacto, atualidade e cursor no envelope padrão do projeto. A Home nova consulta essa projeção, não todas as antigas listas para escondê-las no CSS. Reutilizar `HomeSection`/controle de atualização onde apropriado.

Manter `/home/overview` e suas rotas atuais funcionando para a Home clássica e consumidores existentes durante a transição. Não alterar silenciosamente o significado de `work`, `results` ou `agents`. Se uma extensão do endpoint existente já suportar esse contrato no HEAD, reutilizá-la e documentar mapeamento, sem criar endpoint duplicado.

Ações continuam nas APIs canônicas. Não criar `/home/approve`, `/home/retry-all`, `/home/force-resume` ou endpoints que contornem a validação existente. Detalhes de sessão usam a API de sessão/eventos atual após resolução do alvo.

## 7.5 Contadores e ausência de duplicação

Contar atividades produtivas distintas, não sessões, processos, grupos ou joins. Contar pendências como ocorrências acionáveis, com sua unidade explícita. Quantidade de sessões aparece no grupo, não misturada ao total de trabalhos. Não somar contadores de unidades diferentes.

Todos e projeto específico são consultas autorizadas antes de contar. Totais desconhecidos são `null`/parciais, não zero. O tamanho da página não é o total. Atividade reportada externamente é distinguida e não soma como RUNNING nativo confirmado.

## 7.6 Atualização e desempenho

Preservar `useHomeOverview`/controller e o SSE compartilhado, estendendo invalidação para entries/filhos. Não criar stream por linha. Consultar transcript apenas do painel visível; fechar cancela observação local sem parar execução.

Agrupar bursts e limitar refresh; conservar fallback por tempo para prazos/TTL sem evento, como já previsto na Home. Respostas antigas de outro escopo são descartadas por geração/cancelamento. Reconexão, retenção de eventos e retorno de aba exigem releitura.

Não manter transação SQLite aberta entre páginas. Cursor opaco vinculado a filtros, Server, partição e ordenação; mudança de revisão que invalida cursor recebe resposta explícita. Snapshot de banco não significa snapshot simultâneo de todos os hosts: informar timestamps de publicação.

Metas propostas de validação: overview útil em até 2 s em fixture registrada; p95 de leitura de 500 ms como alvo, não resultado já obtido; payload inicial preferencialmente até 200 KiB; número de queries não cresce por agente. O ledger anterior registra alvo não atingido: medir novamente, não afirmar que a refatoração visual o resolveu.

---

# 8. Onboarding obrigatório: retomar ou adicionar outro harness

**Esta frente não é opcional, não é follow-up e não pode ser removida para declarar a UI concluída.** Ela faz parte da definição de pronto deste plano, inclusive no terminal. O objetivo é acabar com a necessidade de conhecer `--profile` para colocar dois harnesses no mesmo projeto.

## 8.1 Glossário para implementação, não para o formulário inicial

| Conceito | Significado | O que não é |
|---|---|---|
| Agente | Identidade canônica persistente com papel e permissões. | Processo, pane ou nome do harness. |
| Harness | Cliente/runtime usado para executar a interação. | Identidade única do agente. |
| Conexão | Associação aprovada de identidade, execução e contexto. | Uma conversa específica. |
| Perfil local | Atalho/checkpoint do CLI para seleção de conexão. | Fonte de autoridade ou histórico da conversa. |
| Sessão | Contexto conversacional/runtime identificado. | Configuração permanente do agente. |
| Operação | Pedido/controle concreto com recibos e intenção identificada. | Sessão inteira ou login no provedor. |
| Workspace | Projeto lógico canônico no Nexus. | O mesmo caminho físico em todas as máquinas. |

Na experiência pública, as escolhas iniciais são **“Voltar a uma conexão existente”** e **“Adicionar outro harness”**. Só depois da primeira escolha faz sentido selecionar qual sessão continuar. Recuperar um envio pendente deve aparecer como recuperação do mesmo pedido, não como nova tarefa.

## 8.2 Comandos existentes e extensão proposta

Na referência consultada existem:

```sh
okto-nexus connect --client codex --project .
okto-nexus connect --profile revisor --client claude --project .
okto-nexus work --profile revisor
okto-nexus work send --session-id SESSION_ID --message "Continuar esta sessão" --json
okto-nexus work send --new-session --message "Começar outro contexto" --json
okto-nexus work resume --json
```

O `work resume` recupera envio/intenção existente; não renomeá-lo mentalmente como escolha genérica da última conversa. `--profile` continua funcionando para usuários e scripts atuais. [S11–S13]

**Extensão proposta obrigatória:** `connect` interativo resolve conexões existentes e oferece retomar/adicionar. Acrescentar uma intenção explícita `--new-connection` para automação e acesso direto, salvo nome equivalente já implementado no HEAD. Esse flag significa criar outra conexão, não substituir a atual nem iniciar uma sessão imediatamente. Para execução não interativa de criação adicional, exigir `--profile NOME` explícito e estável, além da revisão/consentimento atuais. Esse perfil guarda a intenção; não acrescentar outro flag de request ID sem necessidade comprovada. O usuário interativo recebe um perfil gerado, portanto continua sem precisar nomeá-lo. Uma repetição recupera o mesmo setup.

Comando ilustrativo **a implementar**, não disponível por afirmação deste plano:

```sh
okto-nexus connect --project . --client claude --new-connection
```

Combinação `--new-connection --profile NOME`: nome ainda não usado prepara nova conexão; nome já pertencente ao mesmo setup de criação recupera a intenção; perfil legado ou pertencente a outra conexão provoca conflito sem substituição. Registrar a origem/identidade da criação em metadado local versionado, sem mudar a autoridade canônica. Novo conteúdo para uma intenção pendente continua sujeito ao contrato de revisão.

Não adicionar `--yes` genérico que aceite toda autorização. O consentimento atual por revisão e o comportamento `--approve REVIEW_REVISION` permanecem. Não colocar API keys em flags.

## 8.3 Resolução antes de criar estado

Separar escolha de destino do serviço, escolha de conexão e execução do setup. O usuário pode usar o mesmo caminho local como atalho para Servers diferentes: candidatos devem ser isolados por destino/instância/identidade humana, e não apenas pelo diretório.

Ordem obrigatória:

1. Resolver projeto local e Server/instância pretendidos pelas opções existentes. Não criar Server local como fallback de um remoto indisponível.
2. Ler atalhos/checkpoints acessíveis desse destino e projeto. Fazer descoberta passiva de instalação quando já permitida pelo contrato.
3. Identificar pedido incompleto ou resultado incerto que precise recuperação. Não abrir novo setup como fallback de uma falha anterior.
4. Resolver intenção explícita (`--profile`, `--new-connection`, binding específico) ou apresentar as escolhas ao usuário interativo.
5. Selecionar/revalidar conexão canônica, ou reservar um novo atalho/checkpoint antes de efeitos.
6. Reutilizar a gestão de serviço existente quando o comando autorizar inicialização. `--plan`, doctor e status não ganham autostart.
7. Usar o setup canônico atual para revisão, teste consentido e Finish. Não duplicar esse fluxo.
8. Entrar no prompt de trabalho ou retornar estado conforme `--no-chat`/`--json`, sem enviar tarefa automaticamente.

Algumas leituras canônicas só estão disponíveis com o serviço ativo. Nesse caso, separar “atalhos locais encontrados” de “estado confirmado no Server”; o comando normal pode iniciar o serviço conforme seu contrato, mas `--plan` informa o limite sem iniciar nada. Não apresentar metadado salvo como prova de readiness.

## 8.4 Tabela de decisão do CLI

| Situação | Comportamento exigido |
|---|---|
| Nenhuma conexão no projeto | Selecionar harness; se único candidato elegível, sugerir sem pergunta redundante; apresentar revisão. |
| Uma conexão, sem seleção explícita | Mostrar resumo: Retomar / Adicionar outro / Cancelar. Retomar é escolha explícita; não criar agente antes dela. |
| Várias conexões | Listar nomes amigáveis, harness, host e estado conhecido; oferecer Adicionar outro na mesma lista. |
| `--profile` existente e compatível | Reutilizar o perfil explicitamente escolhido, sem picker redundante; preservar semântica de scripts. |
| `--profile` explícito com `--client` incompatível | Recusar substituição e explicar como adicionar outra conexão. Não reinterpretar seleção explícita. |
| Sem `--profile`, `--client claude`, só existe Codex | Explicar que já existe Codex e propor adicionar Claude, usando a revisão do novo setup; não terminar apenas em PROFILE_CONFLICT. |
| `--client` corresponde a exatamente uma conexão | Oferecer retomá-la ou adicionar outra instância; seleção explícita de adicionar vence. |
| Mais de uma conexão do mesmo harness | Escolha por conexão/contexto; não adotar a primeira nem a mais recente. |
| `--new-connection` | Preparar conexão adicional com atalho gerado e nova identidade sugerida, salvo agente existente selecionado explicitamente. |
| Checkpoint pendente/resultado desconhecido | Priorizar recuperar o mesmo pedido. Outra conexão independente exige intenção nova explícita e não substitui o pedido anterior. |
| Perfil ocupado por outro escritor | Mostrar ocupado e instruir observação/uso existente conforme API; não apagar lock nem clonar conexão para contornar. |
| Conexão revogada ou grant expirado | Mostrar motivo; autorização/reconfiguração é revisão separada. Retomar não reautoriza. |
| JSON/noninteractive sem seleção suficiente | Resposta estruturada com escolhas redigidas e motivo de seleção necessária, sem prompt, modelo ou criação de identidade. |

Escolher Adicionar outro com o mesmo harness é válido. “Outro harness” na linguagem cotidiana inclui outra conexão/instância do mesmo produto. A UI deve dizer isso no detalhe: “Adicionar uma nova conexão, inclusive de um harness já utilizado”.

## 8.5 Fluxos interativos concretos

### Primeira conexão

```text
$ okto-nexus connect
Projeto: Nexus
Harnesses encontrados: Codex, Claude
Qual usar?  [1] Codex  [2] Claude

Conectar Codex a este projeto
Agente sugerido: Assistente Nexus
Execução: neste computador; serviço em segundo plano
Permissões e limites: resumo do preset atual
Teste: enviará uma consulta ao provedor; pode consumir uso
[Confirmar configuração e teste]  [Personalizar]  [Cancelar]

Conexão configurada. Nenhuma tarefa do projeto enviada.
Digite seu pedido, ou saia e volte depois.
```

### Segundo harness

```text
$ okto-nexus connect
Já existe uma conexão neste projeto:
  Codex · Assistente Nexus · Neste computador

[1] Voltar a essa conexão
[2] Adicionar outro harness
[0] Cancelar

> 2
Qual harness? Claude
Agente sugerido: Assistente Nexus — Claude
Projeto lógico: o mesmo Nexus, após confirmação/revalidação
[Confirmar configuração e teste]  [Personalizar]  [Cancelar]

Claude conectado; Codex permanece inalterado.
```

Não perguntar “qual nome de profile?” no fluxo padrão. A revisão pode exibir nome amigável editável; o atalho técnico é gerado e informado ao final para scripts. Evitar colisões entre novos nomes sem prometer identidade canônica pelo rótulo.

### Voltar a trabalhar

Depois de selecionar a conexão, recuperar primeiro qualquer envio ainda sem resultado determinado. Se não houver pedido incerto, consultar as sessões autorizadas da conexão:

- Uma sessão compatível: mostrar contexto e oferecer Continuar ou Nova conversa. Não realizar inferência antes do pedido.
- Várias sessões: listar contexto, estado e última atualização; exigir escolha.
- Nenhuma sessão: informar “Uma nova conversa será aberta quando você enviar o pedido”, conforme o mecanismo atual de abertura sob demanda.
- Sessão encerrada ou grant incompatível: histórico continua acessível quando autorizado; novo contexto precisa ser explícito. Não prometer retomada nativa que o adaptador não suporta.

CLI e UI devem distinguir **observar** de **enviar nova mensagem**. Abrir o acompanhamento de uma sessão não precisa adquirir autoridade para enviar trabalho a ela.

## 8.6 Identidade e defaults

Adicionar nova conexão no caminho padrão sugere um novo agente de projeto independente. Isso atende à intenção de ter colaboradores distintos e evita misturar funções/históricos. A identidade só é criada por Finish autorizado, não por descoberta ou seleção de menu.

Oferecer reutilização de agente existente em Personalizar, com seleção canônica e permissões verificadas. Não duplicar identidade por reabertura, e não reutilizar identidade apenas porque tem o mesmo nome ou usa o mesmo harness. Conectar múltiplos canais ao mesmo agente não deve fanoutar uma entrega lógica em múltiplas execuções.

Retomar mantém papel, modelo, instruções, permissões e escolhas posteriores do usuário. Novo setup usa o preset aprovado já existente. Este plano não altera os limites 60 min/20 ações documentados no snapshot nem remove sua revisão; tampouco os considera eternamente vigentes. O checkout e a política atual são autoridade. Alteração de preset exige fluxo explícito existente.

Pasta local e workspace lógico são diferentes. Ao adicionar outra conexão no mesmo host/projeto, sugerir workspace existente somente com associação autorizada e confirmação na revisão. Nome/caminho iguais não concedem acesso. Em hosts diferentes, mapear a pasta local para o workspace escolhido sem copiar path de outra máquina.

## 8.7 Catálogo de atalhos e compatibilidade com perfis antigos

Não reescrever perfis legados só para mudar o nome. Preservar seus arquivos, referências, IDs de intenção, receipts e checkpoints. Introduzir uma consulta/catalogação de conexões do projeto sobre esses registros, com limite, validação e isolamento de destino. Se houver índice local novo, ele é reconstruível e não vira fonte de autoridade.

O perfil implícito antigo `project-<hash>` precisa continuar sendo encontrado. Novos atalhos podem incluir um sufixo aleatório persistido, mas seu ID é definido uma vez antes de efeitos e recuperado em retries. Nome de exibição e nome do arquivo não são IDs do agente.

Uma conexão sem atalho local, mas visível no Server ao operador, pode ser selecionada explicitamente e receber um atalho novo sem recriar binding/agente/grant. Isso exige leitura canônica com escopo; não varrer outros usuários ou importar credenciais de arquivos arbitrários.

Concorrência: lock/compare-and-swap no catálogo e reserva de nome, seguido do lock de perfil já existente. Não manter lock global durante prompts, testes ou rede. Depois da decisão humana, revalidar versão/candidato antes de commit. Dois terminais podem criar conexões independentes, nunca sobrescrever a mesma nem gerar duas identidades para a mesma intenção recuperável.

## 8.8 JSON, scripts e semântica de erro

Preservar contratos existentes e códigos de saída documentados. Novos motivos específicos de escolha pertencem ao envelope apropriado do CLI; não expandir arbitrariamente o catálogo fechado de erros de domínio.

Exemplo conceitual para seleção incompleta, redigido sem segredo:

```json
{
  "state": "selection_required",
  "reason": "connection_selection_required",
  "choices": [
    {"profile": "atalho-existente", "label": "Codex · Assistente", "harness": "codex", "observed_status": "configured"}
  ],
  "supported_actions": ["select_existing_profile", "new_connection"],
  "effects_started": false
}
```

`effects_started` só pode ser false se nenhum efeito do comando ocorreu; se o Server já foi iniciado, reportar esse fato separadamente e não mentir. Não usar exit 0 para declarar tarefa concluída quando só houve seleção/configuração. Log humano no stderr e JSON no stdout conforme padrão atual.

No Connector, os comandos `connect/configure` atuais são interativos e rejeitam JSON. Preservar esse contrato nesta entrega, usando seus comandos de automação existentes para scripts. Não introduzir prompts ocultos em JSON ou alterar globalmente o parser para forçar paridade artificial.

## 8.9 Cancelamento e efeitos parciais

Cancelar no picker não cria agente, binding, grant ou tarefa. O serviço pode já estar ativo pelo contrato do comando; informar que permanece em segundo plano, sem prometer rollback de um autostart permitido.

Cancelar antes de consentir com teste não envia inferência. Se o teste já foi admitido, Ctrl+C encerra observação local e preserva o checkpoint; não inventa cancelamento confirmado. Falha depois de Finish não reexecuta setup. Instalação de serviço no login é efeito separado, com estado recuperável próprio.

Repetir a intenção exata recupera seu resultado. Alterar conteúdo de uma intenção pendente exige as regras de revisão atuais. Nunca apagar um checkpoint incerto para “destravar” o onboarding.

---

# 9. Onboarding pela UI e pelo Connector

## 9.1 Entrada básica na UI

Home possui Conectar agente em estado vazio e com conexões existentes. A mesma ação pode aparecer em Conversas quando não houver destinatário elegível. Ela abre o fluxo curto no painel atual, não Agents com uma grade de formulários avançados.

Primeira decisão, quando houver conexões: **Abrir conexão existente** ou **Adicionar outro harness**. Listar somente conexões autorizadas no escopo. Não iniciar sessão ao selecionar uma linha; mostrar acompanhamento ou próximo passo claro.

Adicionar local reutiliza o setup existente: projeto, harness elegível, identidade sugerida, revisão e teste consentido. Personalizar expande os controles existentes; o padrão deve funcionar sem preenchê-los. Descoberta e versões precisam manter a evidência/qualificação atual, sem declarar instalado/compatível por nome de processo.

## 9.2 A máquina da UI não é necessariamente a máquina de execução

O navegador conectado ao Server não pode descobrir executáveis/pastas de outro computador sozinho. Distinguir:

- **Neste servidor:** executor embedded, pastas e login do host Server.
- **Em outra máquina:** usar Connector no host de execução, com comando/instrução contextual sem credenciais.
- **Cliente que já utilizo:** caminho participante existente, quando exposto como opção secundária; não iniciar runtime gerenciado como efeito oculto.

Não chamar “neste computador” a um executor remoto quando o dashboard está sendo aberto em outro device. Mostrar “Servidor Nexus” ou nome de host conhecido. CLI local pode usar “neste computador” quando o destino for confirmado local.

## 9.3 Descoberta e escolha no Connector

Usar os aliases, registros de identidade e checkpoints existentes. Antes de tentar Replace/Abort do binding atual, oferecer retomar conexão compatível ou adicionar outra. `configure` avançado pode continuar oferecendo substituição explícita; `connect` simples não deve sugerir substituir como única forma de adicionar.

Adicionar outra conexão não substitui silenciosamente a máquina anterior do mesmo agente. Respeitar política de máquina registrada. Para um novo colaborador, usar o bootstrap de identidade de projeto existente ou seleção autorizada de outro agente. Credencial de agente não pode criar sua própria autoridade administrativa.

Servidor, projeto lógico, máquina, harness e pasta local precisam aparecer na revisão. Daemon inicia/reutiliza pelo mecanismo atual depois do consentimento apropriado. Uma requisição aguardando aprovação é retomada pelo mesmo root; não criar um novo root a cada consulta.

## 9.4 Aprovação remota e continuidade

A decisão do operador pode ocorrer pelo seu terminal ou controles básicos da UI, sem obrigatoriedade de abrir Avançado. O Connector não recebe chave de operador e não autoaprova sua máquina. A revisão remota existente, receipt e pedido de autorização continuam válidos.

Durante espera: “Aguardando aprovação do operador”, com ID/correlação para diagnóstico e instrução de retomada. Fechar a CLI não cancela o daemon/pedido conforme contrato atual. Após aprovação, a Home mostra a conexão quando houver evidência publicada; não exige cadastrar outra vez no navegador.

O cliente do operador pode associar um binding remoto aprovado a seu atalho local sem redefinir a pasta do host. Alterar preferências de outra máquina só pelo fluxo autorizado existente; o browser não envia caminhos arbitrários diretamente a um processo.

## 9.5 Critério de equivalência

Equivalência significa mesmas intenções, identidade, efeitos e mensagens compreensíveis, não flags idênticas em CLIs diferentes. Testes devem provar que UI, CLI do Server e Connector convergem para os mesmos registros canônicos e não criam três configurações concorrentes.

---

# 10. Daemon e uso diário: preservar, não reinventar

A conexão gerenciada local já inicia/reutiliza Server. Isso permanece obrigatório. A reestruturação não pode voltar a exigir `serve` manual ou abertura do dashboard para manter trabalho ativo. [S12]

Separar claramente:

| Comportamento | Regra |
|---|---|
| Rodar em segundo plano | Usar lifecycle atual; fechar terminal/UI não encerra trabalho. |
| Retomar conexão | Reusar configuração; não renovar grant automaticamente. |
| Iniciar no login | Opção explícita independente, com revisão dos efeitos e suporte real da plataforma. |
| Reiniciar serviço | Reconciliar; não repetir operações de resultado desconhecido. |
| Status/doctor/plano | Não iniciar processo/modelo como efeito escondido. |
| Parada solicitada | Usar drain/controle canônico; não matar todos os harnesses sem confirmação. |
| Server remoto indisponível | Mostrar indisponibilidade; nunca criar substituto local. |

O instalador novo de início no login descrito no snapshot suporta tarefa de usuário Windows e mantém limites de qualificação. Não anunciar Linux/macOS/reboot/logout como suportados integralmente com base somente em existência de código. A melhoria deste plano apresenta capacidades do host, não amplia plataformas sem campanha própria.

No diálogo simples, explicar de forma curta: “O Nexus continuará em segundo plano. Iniciar ao entrar no computador: disponível/opcional conforme este sistema”. A ação de habilitar/reabilitar precisa estar na revisão e não deve reaparecer como obrigação a cada retomada.

---

# 11. Segurança, privacidade, acessibilidade e estabilidade

## 11.1 Autorização e escopo

Avançado não é ACL. Ocultar um destino não protege uma API e abrir o índice não concede permissão. Continuar autenticando e autorizando todas as leituras e mutações. Contadores e previews seguem a visibilidade da origem; cache precisa ser isolado por Server, identidade e projeto.

Atores de pergunta nativa permanecem os originais. Operador não responde em nome de outro agente. IDs e parâmetros vindos da URL são validados; payload de log não vira ação executável nem link interno privilegiado.

Sessão/eventos exige escopo completo confirmado; descobrir um `session_id` não permite enumerar outro executor. Mudanças de binding, grant, época e revisão podem tornar uma ação indisponível entre clique e submit. Tratar com recusa/recuperação canônica.

## 11.2 Segredos e conteúdo

Não gravar chaves em URL, argumentos, localStorage, screenshots, mocks com segredo real ou documentos de evidência. Perfis locais continuam checkpoints/refs; histórico permanece canônico. Rascunhos sensíveis não entram em bookmark, telemetria ou export genérico.

Preservar sanitização/redação do terminal e artefatos. Modo Avançado não desliga proteção. Conteúdo de outro projeto não pode piscar na tela durante corrida de rede. Logout e 403 removem snapshots, painel e cache protegido.

## 11.3 Navegação e teclado

Navegação normal usa links/botões sem forçar role `menu` em toda a sidebar. Controles de expansão têm estado acessível (`aria-expanded` e alvo coerente); ícones têm rótulo. Painel modal retém/restaura foco; painel não modal não finge ser modal. [W01–W03]

Escape fecha a camada ativa após guard de rascunho. Retornar foco ao elemento que abriu o painel ou um destino estável se ele deixou de existir. Atualizações não roubam foco. Não anunciar cada token ao leitor de tela; agrupar avisos e oferecer controle de scroll/atualização visual. [W03–W04]

Testar largura de 360 px, zoom 200%, tema claro/escuro e navegação só por teclado. Linha inteira pode abrir detalhe, mas seus botões internos não devem disparar a abertura/ação duas vezes. Não depender apenas de cor para estado.

## 11.4 Qualificação e limitações

Teste Node que procura strings não comprova teclado, overlays, browser history ou foco. Usar teste real de navegador. Leitor de tela real e eventos do SO permanecem qualificação específica; quando indisponíveis, registrar bloqueio, não simular resultado PASS.

O ledger atual já registra uma limitação de ponte Windows para leitor de tela. Preservar esse histórico e localizar alternativa de qualificação autorizada, sem dizer que a mudança de UI a resolveu. Testes sintéticos de provedor não certificam harness real; campanha real precisa de consentimento e ambiente descartável.

---

# 12. Organização de código e responsabilidades

## 12.1 Repositórios

| Repositório | Mudança prevista | Não fazer |
|---|---|---|
| Nexus | Shell/navigation, Home unificada, alvos/painel, projeção em lote, onboarding local/UI e seleção de conexão/sessão. | Nova fila de trabalho, scheduler, identidade ou API que contorne controles. |
| Connector | Escolha retomar/adicionar usando os aliases/checkpoints do host e continuidade remota. | Nova autoridade de operador ou duplicação da inbox Server. |
| Core | Regressão/compatibilidade; mudança só se uma lacuna de contrato estiver demonstrada. | Alterar protocolo ou versão apenas para mover telas. |

Se mudar contrato compartilhado, criar ADR curta com impacto de versões/artefatos. Manter pins, manifestos e wheels compatíveis; não ajustar dependency sem reconciliar a campanha conjunta.

## 12.2 Pontos reais de reuso

| Arquivo/área existente | Uso neste plano |
|---|---|
| `frontend/src/App.tsx` | Shell, menu, guard, autenticação, workspace, SSE, fallback e indicador global. |
| `frontend/src/components/home/OperationalHome.tsx` | Substituir composição paralela por acompanhamento único, sem recomeçar controller. |
| `frontend/src/components/home/HomeInspection.tsx` | Reusar inspeção, novo pedido e continuidade contextual. |
| `frontend/src/homeTypes.ts`, `homeNavigation.ts`, `homeApi.ts` | Extensão de alvos de sessão/conexão, contrato de entries e resolução. |
| `frontend/src/hooks/useHomeOverview.ts` e `homeController` | Atualização, escopo, paginação, pausa visual e descarte de requests antigos. |
| `frontend/src/components/AttentionInspection.tsx` | Composição de controles canônicos e fila sob demanda. |
| `frontend/src/components/SessionTerminalModal.tsx` | Extrair corpo reutilizável preservando verificação de escopo. |
| `frontend/src/components/RuntimeTerminal.tsx`, `RuntimeSessionTail`, `RuntimeHistory` | Saída somente leitura, histórico, scroll e ampliação sem dialogs aninhados. |
| `frontend/src/views/MetaHarnessView.tsx`, `MetaHarnessComposer` | Conversations e novo pedido; não duplicar envio. |
| `frontend/src/operatorUnread.ts` | Preservar comparadores/semântica de visto ao mudar rótulos. |
| `src/okto_nexus/adapters/inbound/cli/connect.py` | Resolver intenção/conexão antes do perfil implícito e do setup. |
| `src/okto_nexus/application/terminal_connection.py` | Reusar a transação/setup/recuperação existentes. |
| `docs/terminal-connect.md`, `terminal-work.md` | Atualizar exemplos e diferenças entre conectar, continuar sessão e recuperar envio. |
| `plans/home_evolution/*` | Reconciliar legado, fontes, evidências e bloqueios da Home. |
| Connector: CLI de connect/configure e armazenamento local existente | Aplicar fluxo equivalente sem inventar paridade de flags. |

Os arquivos não inspecionados integralmente devem ser rastreados pelo executor. Nomes novos abaixo são propostas: `navigationRegistry`, `AdvancedView`, `HomeEntries`, `SessionExecutionPanel`, `connection_choices`. Não criar todos por obrigação. Extrair por fronteira testável real, evitando megacomponente e framework desnecessário.

## 12.3 Preservação do trabalho em andamento

Registrar `git status`, HEAD, branch, instruções AGENTS/CONTRIBUTING e mudanças locais. O snapshot é referência de análise, não comando de checkout. Não fazer cherry-pick massivo ou reset para um SHA antigo.

Se outro processo estiver alterando App/OperationalHome/connect simultaneamente, dividir ownership de arquivos ou usar branch/worktree de implementação autorizado. Antes de integrar cada incremento, comparar drift e repetir testes relevantes. Não editar a mesma árvore em paralelo sem coordenação.

Um requisito já atendido no HEAD é registrado como reutilizado e validado, não reimplementado. Um bloco novo da Home ainda não concluído pode ser aproveitado como fonte e ter apenas sua apresentação substituída. Não apagar testes antigos por falharem com rótulos novos sem entender o comportamento protegido.

---

# 13. Contratos de persistência e rollout

## 13.1 Preferências e migração

Preservar tema, projeto, estado da sidebar, vistos e perfis atuais. Mapear nomes antigos de view para destinos novos. Preferência anterior em Policies deve continuar abrindo Policies sob Avançado; nome desconhecido volta à Home com tratamento claro, sem apagar dados.

Preferências de UI não alteram flags de runtime. Novo agrupamento/filtro da Home é estado de apresentação isolado por escopo apropriado. Rascunho não é preferência persistente. Perfil CLI é checkpoint durável e não pode ser descartado junto com reset de layout.

Não criar `home_tasks`, `home_sessions` ou `home_status` como fonte de verdade. Índices necessários e metadados auxiliares usam migração aditiva com número real do checkout. Medir custo de leitura/escrita. Não restaurar banco antigo com executores ativos para reverter UI.

## 13.2 Rollout combinado

1. Implementar/validar read models, alvos e seletor de conexão isoladamente.
2. Disponibilizar navegação simples com sino/atalhos funcionando na Home clássica e operacional.
3. Habilitar Home unificada em instalação isolada; verificar todas as jornadas.
4. Qualificar local, dois harnesses, retomada e remoto conforme matriz.
5. Somente então alterar o padrão da apresentação no candidato de release aprovado.

A flag atual não deve virar um passo manual exigido do usuário final para obter a experiência básica. Durante desenvolvimento, preservar opt-in/fallback; ao cumprir os gates, planejar default da experiência simples. Decisão de publicação/ativação na instalação real exige autorização do responsável.

## 13.3 Reversão

Reverter apresentação não para daemon, não fecha sessões, não revoga grants nem elimina conexões adicionadas. Páginas antigas permanecem alcançáveis. Fallback mantém sino, perguntas e aprovação. Invalidações antigas continuam compatíveis enquanto houver ambos os consumidores.

Rollback da seleção nova de conexão deve preservar novos perfis reconhecíveis pelos comandos explícitos antigos, ou vir acompanhado de procedimento de compatibilidade testado. Não criar formato local que torne impossível voltar a usar `--profile` no código anterior sem aviso e migração revisada.

---

# 14. Marcos, dependências e disciplina de execução

| Marco | Entrega | Condição |
|---|---|---|
| M0 | Baseline, contratos, fontes e cenários reconciliados | Sem modificar produto com suposições sobre o HEAD. |
| M1 | Navegação simples + acesso global às pendências + seletor CLI local retomar/adicionar | Já reduz atrito visual e o obstáculo concreto do segundo harness. |
| M2 | Acompanhamento único + sessão exata + onboarding curto pela UI | Não exige navegar para Runtimes/Agents para operar normalmente. |
| M3 | Connector equivalente + regressão conjunta + pacote/rollout | Entrega completa; onboarding não é dispensado por ser multi-repositório. |

Sequência de incrementos do backlog: **PR-00 baseline → PR-01 navegação → PR-02 seleção de conexão local → PR-03 projeção unificada → PR-04 Home → PR-05 painel → PR-06 onboarding UI/Connector → PR-07 regressão/qualificação → PR-08 documentação/pacote/rollout**.

Após PR-00, navegação e seletor local podem avançar em arquivos independentes. Não colocar o seletor obrigatório no fim do projeto como melhoria eventual. Read model precede Home; alvo de sessão precede abertura contextual; controles globais precedem esconder destinos antigos.

Cada incremento inclui testes focais e atualização do ledger. Segurança, semântica de estado e conflitos de identidade não são postergados para a revisão final. Ao encontrar lacuna, registrar BLOCKED com evidência e avançar nas tarefas independentes, sem inventar implementação ou reduzir requisito silenciosamente.

## 14.1 Formato da evidência por tarefa

Registrar ID, estado, branch/SHA, arquivos alterados, requisitos atendidos, cenários relacionados, comando real, resultado, ambiente e limitações. Estado de tarefa: TODO → IN_PROGRESS → IMPLEMENTED → VERIFIED; BLOCKED quando necessário. Cenário: NOT_RUN/PASS/FAIL/BLOCKED.

Não marcar VERIFIED por documentação, compilação isolada ou contagem agregada de testes sem correlação. Não inventar prazo de engenharia; estimar depois do baseline. Entregas já existentes podem ser VERIFIED_REUSED apenas se o ledger mantiver evidência de testes no corte atual; no arquivo fornecido usar VERIFIED e campo de reaproveitamento, sem criar enum ambígua.


# 15. Backlog executável detalhado

Cada tarefa abaixo é obrigatória no seu escopo. A lista de testes por tarefa é focal, não dispensa regressão das dependências. Alterações equivalentes já implementadas devem ser reaproveitadas com evidência, sem refazer a feature.

## PR-00 — Baseline e contratos (M0)

### UI-001 — Fixar baseline e coordenar trabalho em andamento

**Estado inicial:** TODO. **Dependências:** nenhuma. **Requisitos:** R13, R18.

**Áreas:** `AGENTS.md/CONTRIBUTING/CI atuais`; `git status/branch/HEAD dos repositórios`.

**Passos:**
1. Registrar HEAD real, árvore de trabalho, instruções e versões/pins sem reset/checkout destrutivo.
2. Comparar o SHA do plano e os commits posteriores; localizar quem está editando App, Home e CLI.
3. Definir branch/worktree e ownership de arquivos; registrar o que já existe e não será refeito.

**Aceite:** Baseline reproduzível e mapa de drift; nenhum trabalho local sobrescrito.

**Cenários focais:** T-BASE-01, T-BASE-02.

### UI-002 — Mapear fontes, destinos e invariantes atuais

**Estado inicial:** TODO. **Dependências:** UI-001. **Requisitos:** R06, R07, R13, R14, R15.

**Áreas:** `App.tsx`; `plans/home_evolution/source-map.md`; `APIs de sessão, atenção, setup e conexão`.

**Passos:**
1. Inventariar destinos, links, callbacks, comparadores de view e preferências.
2. Rastrear work/sessions/bindings/attention/results até fontes/autorização/atualidade.
3. Mapear serviços e autoridade distintos no Server e Connector; identificar gates pendentes.

**Aceite:** Matriz origem→escopo→autorização→correlação→evento/fallback e tabela completa de destinos.

**Cenários focais:** T-BASE-03, T-SCOPE-01.

### UI-003 — Congelar contratos de navegação e acompanhamento

**Estado inicial:** TODO. **Dependências:** UI-002. **Requisitos:** R01, R02, R03, R04, R05, R06, R15.

**Áreas:** `homeTypes.ts/homeNavigation.ts`; `contrato de leitura Home`; `registro de navegação proposto`.

**Passos:**
1. Documentar IDs internos versus rótulos públicos, sem troca global de strings.
2. Especificar HomeEntryGroup, deduplicação, itens sem sessão e novo alvo session.
3. Definir paginação por grupo/filhos, contadores e contratos de erro/versionamento.

**Aceite:** Contratos completos, exemplos válidos/inválidos e tabela de compatibilidade; sem any para campos críticos.

**Cenários focais:** T-NAV-01, T-DATA-01, T-DATA-06, T-PANEL-01.

### UI-004 — Congelar a escolha de conexão e sessão

**Estado inicial:** TODO. **Dependências:** UI-002. **Requisitos:** R09, R10, R11, R12, R17.

**Áreas:** `connect.py`; `terminal_connection.py`; `CLI e store do Connector`.

**Passos:**
1. Especificar candidatos por Server/instância/operador/projeto e preservação de perfis legados.
2. Definir separadamente retomar conexão, nova conexão, continuar sessão e recuperar envio.
3. Definir comportamento de --profile, --client, novo flag explícito, JSON e checkpoints incertos.

**Aceite:** Tabela da seção 8 rastreada a handlers atuais; nenhuma dependência de dashboard para o padrão.

**Cenários focais:** T-CLI-01, T-CLI-05, T-CLI-11, T-CONN-01.

### UI-005 — Preparar fixtures e cenários de produto

**Estado inicial:** TODO. **Dependências:** UI-003, UI-004. **Requisitos:** R06, R14, R16, R18.

**Áreas:** `testes/fixtures atuais`; `homes e workspaces temporários`.

**Passos:**
1. Criar fixtures com duas conexões, duas sessões no mesmo agente, A→B→C e tarefa sem executor.
2. Incluir pergunta ao operador/agente, resultado incerto, cleanup após sucesso, observação externa e erro parcial.
3. Registrar baseline de número de consultas, payload e navegação; sem usar dados reais.

**Aceite:** Fixtures determinísticas compartilháveis entre testes e navegador, com relógio controlado.

**Cenários focais:** T-BASE-04, T-DATA-10, T-QUAL-01.

## PR-01 — Navegação simples e pendências globais (M1)

### UI-006 — Implementar registro de navegação com IDs estáveis

**Estado inicial:** TODO. **Dependências:** UI-003. **Requisitos:** R01, R02, R15.

**Áreas:** `frontend/src/App.tsx`; `navigationRegistry proposto`.

**Passos:**
1. Extrair definição dos destinos e seu placement preservando componentes/renderers.
2. Exibir quatro primários e uma entrada Advanced; tratar Settings/Memory/utilitários por regra existente.
3. Adicionar aliases de rótulos antigos quando necessários; nenhuma alteração de ACL.

**Aceite:** Sidebar mínima; todos os destinos antigos resolvem para o mesmo componente e estado.

**Cenários focais:** T-NAV-01, T-NAV-02, T-NAV-04.

### UI-007 — Criar índice Avançado e breadcrumb

**Estado inicial:** TODO. **Dependências:** UI-006. **Requisitos:** R02, R14, R15.

**Áreas:** `AdvancedView proposto`; `shell e renderização de páginas atuais`.

**Passos:**
1. Agrupar os destinos pela matriz aprovada, com descrição curta.
2. Manter sidebar mínima ao abrir destino avançado e breadcrumb navegável.
3. Respeitar feature Memory e acesso; preferências simples ficam globais.

**Aceite:** Não há submenu lateral expandido com todos os destinos; nenhum recurso perdido.

**Cenários focais:** T-NAV-03, T-NAV-05, T-NAV-06.

### UI-008 — Garantir sino e fila de pendências em qualquer Home

**Estado inicial:** TODO. **Dependências:** UI-006. **Requisitos:** R07, R08, R16.

**Áreas:** `useAttention`; `AttentionView/AttentionInspection`; `App.tsx`.

**Passos:**
1. Reutilizar contador/fila/ações canônicos em painel sob demanda.
2. Separar escopo global do filtro da Home e preservar incidente Server.
3. Funcionar na Home clássica/operacional com guard de edição e sem dialogs empilhados.

**Aceite:** Pergunta/aprovação continua alcançável sem item Attention lateral e sem ativar Home nova.

**Cenários focais:** T-NAV-07, T-NAV-08, T-ATTN-01, T-ATTN-06.

### UI-009 — Migrar rótulos, links e preferências sem quebrar fluxos

**Estado inicial:** TODO. **Dependências:** UI-006, UI-007, UI-008. **Requisitos:** R01, R07, R15.

**Áreas:** `App.tsx`; `operatorUnread.ts`; `HelpModal/onboarding`; `links de Graph/MetaHarness`.

**Passos:**
1. Mostrar Conversations no lugar público de Meta-harness sem quebrar OPERATOR_VIEWS.
2. Atualizar atalhos/ajuda/docs visíveis e referências a Settings/Agents.
3. Preservar bookmarks, seleção salva, workspace, guard e retorno por histórico.

**Aceite:** Destino específico abre diretamente; visitante não precisa reaprender identificadores; vistos mantêm semântica.

**Cenários focais:** T-NAV-09, T-NAV-10, T-NAV-11, T-RESULT-04.

### UI-010 — Validar shell simples e acesso operacional

**Estado inicial:** TODO. **Dependências:** UI-009, UI-005. **Requisitos:** R01, R02, R07, R08, R15.

**Áreas:** `testes frontend`; `testes de navegador`.

**Passos:**
1. Testar quatro primários e Advanced com flags ON/OFF.
2. Testar acesso direto antigo, 401/403, preferências, mobile e teclado.
3. Rodar regressão de navegação e visto; atualizar snapshots somente com justificativa semântica.

**Aceite:** Navegação simplificada qualificada independentemente do novo layout da Home.

**Cenários focais:** T-NAV-01, T-NAV-06, T-NAV-07, T-NAV-12, T-A11Y-01.

## PR-02 — Seletor local obrigatório retomar/adicionar (M1)

### UI-011 — Catalogar conexões do projeto sem mudar sua autoridade

**Estado inicial:** TODO. **Dependências:** UI-004, UI-005. **Requisitos:** R09, R10, R12.

**Áreas:** `connect.py/project_profile`; `terminal/profiles e resolução de destino existentes`.

**Passos:**
1. Implementar descoberta limitada de perfis/atalhos do destino/projeto, inclusive hash legado.
2. Separar nome amigável, profile e IDs canônicos; revalidar metadado no Server.
3. Isolar Server/origem/instância/operador; índice novo, se houver, é reconstruível.

**Aceite:** Candidatos corretos sem cruzar servidores/identidades; nenhum perfil/grant refeito por leitura.

**Cenários focais:** T-CLI-02, T-CLI-03, T-CLI-14, T-SCOPE-06.

### UI-012 — Implementar picker retomar/adicionar no connect

**Estado inicial:** TODO. **Dependências:** UI-011. **Requisitos:** R09, R10, R11.

**Áreas:** `connect.py`; `apresentação de terminal atual`.

**Passos:**
1. Executar a tabela de decisão de zero/uma/várias conexões.
2. Permitir novo harness ou segunda conexão do mesmo harness com rótulos claros.
3. Gerar atalho único sem pedir nome técnico e manter --profile explícito compatível.

**Aceite:** Segundo harness no mesmo projeto não depende de --profile inventado nem substitui o primeiro.

**Cenários focais:** T-CLI-01, T-CLI-04, T-CLI-05, T-CLI-06, T-CLI-07.

### UI-013 — Persistir nova intenção e proteger concorrência

**Estado inicial:** TODO. **Dependências:** UI-012. **Requisitos:** R09, R12, R14.

**Áreas:** `checkpoint/atomic_json/ExclusiveFileLock existentes`; `reserva de atalho proposta`.

**Passos:**
1. Definir uma vez o profile/agent candidato e o ID de setup antes dos efeitos.
2. Usar reserva/CAS curta sem lock global durante perguntas ou rede.
3. Recuperar a mesma intenção após crash; conflitos explícitos nunca apagam checkpoints.

**Aceite:** Dois comandos não sobrescrevem atalhos; retry não cria segunda identidade; pedido incerto fica recuperável.

**Cenários focais:** T-CLI-08, T-CLI-09, T-CLI-10, T-CLI-15.

### UI-014 — Separar seleção de sessão de recuperação de envio

**Estado inicial:** TODO. **Dependências:** UI-012, UI-013. **Requisitos:** R05, R10, R12.

**Áreas:** `work.py/terminal work atuais`; `APIs de sessão/intenção existentes`.

**Passos:**
1. Depois da conexão, recuperar envio pendente antes de oferecer nova tarefa.
2. Listar sessões autorizadas e permitir continuar exata ou abrir novo contexto por intenção explícita.
3. Preservar --session-id/--new-session e semântica de work resume; respeitar PROFILE_BUSY.

**Aceite:** Nenhuma sessão mais recente escolhida por heurística; nenhuma inferência ao apenas observar.

**Cenários focais:** T-CLI-16, T-CLI-17, T-CLI-18, T-CLI-19, T-PANEL-03.

### UI-015 — Implementar seleção explícita para scripts sem prompts

**Estado inicial:** TODO. **Dependências:** UI-013, UI-014. **Requisitos:** R09, R10, R11, R14.

**Áreas:** `parser connect`; `envelopes e exit codes do CLI`.

**Passos:**
1. Adicionar --new-connection ou equivalente; em execução não interativa exigir --profile explícito e estável para recuperar o mesmo setup.
2. Retornar selection_required redigido quando faltar seleção; preservar --approve e --plan.
3. Não mudar automaticamente o contrato JSON do Connector; manter stdout estruturado e efeitos reais declarados.

**Aceite:** Scripts antigos continuam; comandos ambíguos não criam agente, binding, grant ou trabalho; eventual autostart permitido é declarado. Plan/doctor não iniciam serviço/modelo.

**Cenários focais:** T-CLI-11, T-CLI-12, T-CLI-13, T-SVC-04.

### UI-016 — Testar o segundo harness e retomada ponta a ponta sintética

**Estado inicial:** TODO. **Dependências:** UI-015, UI-005. **Requisitos:** R09, R10, R11, R12, R18.

**Áreas:** `testes CLI/application/HTTP`; `fixtures de providers sintéticos`.

**Passos:**
1. Configurar A, adicionar B no mesmo projeto e retomar ambos; comparar IDs/permissões antes/depois.
2. Simular resposta perdida antes/depois de Finish, cancelamento, serviço indisponível e grant expirado.
3. Separar resultado de fixture e campanha real posterior; registrar evidências por cenário.

**Aceite:** M1 não depende de usuário entender perfis; A não muda ao criar B; falhas não viram duplicação.

**Cenários focais:** T-CLI-04, T-CLI-08, T-CLI-10, T-CLI-20, T-CLI-21.

## PR-03 — Projeção unificada e alvos de sessão (M2)

### UI-017 — Projetar relações unificadas de trabalho e sessões

**Estado inicial:** TODO. **Dependências:** UI-003, UI-005. **Requisitos:** R03, R06, R13.

**Áreas:** `serviços/portas atuais da Home`; `queries SQLite de work/sessions/bindings`.

**Passos:**
1. Criar relações por handoff/entrega/operação e grupos por contexto comprovado.
2. Cobrir tarefas operador→agente e agente→agente sem expandir o diretório operator-only por acidente.
3. Acrescentar sessões/conexões não cobertas; trabalho sem executor permanece explícito.

**Aceite:** Todos os contextos conhecidos são alcançáveis, sem item técnico duplicando trabalho produtivo.

**Cenários focais:** T-DATA-01, T-DATA-02, T-DATA-03, T-DATA-04, T-DATA-05.

### UI-018 — Unir atenção e resultados por correlação

**Estado inicial:** TODO. **Dependências:** UI-017. **Requisitos:** R03, R07, R13, R16.

**Áreas:** `projeções Attention/resultados`; `Home source-map/famílias atuais`.

**Passos:**
1. Anexar ocorrências e entregas pelos IDs/épocas persistidos, não por texto.
2. Preservar fatos do destinatário ao filtrar remetente e separar Server global.
3. Manter ocorrências/resultados sem pai retido como itens distintos com proveniência.

**Aceite:** Sem segunda lista de duplicatas; pergunta de outro agente não vira decisão do operador; A08 preservada.

**Cenários focais:** T-DATA-06, T-DATA-07, T-SCOPE-04, T-ATTN-02, T-RESULT-01.

### UI-019 — Adicionar sessões sem operação aos alvos tipados

**Estado inicial:** TODO. **Dependências:** UI-003, UI-017. **Requisitos:** R05, R06, R14.

**Áreas:** `homeTypes.ts`; `homeNavigation.ts`; `resolver/backend Home`.

**Passos:**
1. Acrescentar kind session e, se necessário, connection com schema fechado.
2. Atualizar encode/decode, validação HTTP, resolver e inspector conjuntamente.
3. Conferir Server/executor/workspace/session/binding reais; indisponível nunca cai para latest.

**Aceite:** É possível inspecionar sessão ociosa sem inventar operation_id; links legados preservados.

**Cenários focais:** T-PANEL-01, T-PANEL-02, T-PANEL-03, T-SCOPE-02, T-NAV-10.

### UI-020 — Aplicar escopo, contagem e paginação por grupo

**Estado inicial:** TODO. **Dependências:** UI-017, UI-018. **Requisitos:** R03, R06, R14, R16.

**Áreas:** `portas de consulta Home`; `SQLite e cursor atual`.

**Passos:**
1. Filtrar permissões/projeto antes de agrupamento, total e paginação.
2. Produzir total de filhos e paginação de expansão sem usar páginas parciais como inventário.
3. Definir ordenação/cursor estáveis e tratar mudança de revisão sem gaps silenciosos.

**Aceite:** Total não deriva do tamanho da página; grupos grandes expandem corretamente; desconhecido não é zero.

**Cenários focais:** T-DATA-08, T-DATA-09, T-DATA-10, T-SCOPE-01, T-SCOPE-03.

### UI-021 — Expor contrato de entries compatível e limitado

**Estado inicial:** TODO. **Dependências:** UI-019, UI-020. **Requisitos:** R03, R13, R14, R16.

**Áreas:** `adapters HTTP Home`; `homeApi.ts/homeTypes.ts`.

**Passos:**
1. Publicar GET entries e filhos ou equivalente reconciliado sem quebrar overview V1.
2. Retornar resumo, freshness, aviso global, cursor, parcialidade e referências limitadas.
3. Manter efeitos fora da leitura e conteúdo completo lazy; validar caches e parâmetros.

**Aceite:** Home nova precisa de uma projeção principal, não seis listas escondidas; consumidores antigos operam.

**Cenários focais:** T-DATA-11, T-SCOPE-05, T-SCOPE-07, T-SEC-01, T-PERF-01.

### UI-022 — Qualificar consultas e semântica de estados

**Estado inicial:** TODO. **Dependências:** UI-021. **Requisitos:** R06, R14, R16.

**Áreas:** `testes domain/SQLite/HTTP`; `instrumentação query/payload`.

**Passos:**
1. Executar casos CLAIMED/SUBMITTED/RUNNING/incerto/cleanup e duas sessões.
2. Provar ausência de N+1 com 1/10/100 agentes e grupos paginados.
3. Registrar EXPLAIN, p50/p95 e custos; não promover meta não atingida a PASS.

**Aceite:** Estado, contador e plano de consulta corretos com evidência; suporte nativo não é inferido.

**Cenários focais:** T-DATA-12, T-DATA-13, T-DATA-14, T-PERF-01, T-PERF-02, T-PERF-03.

## PR-04 — Home com acompanhamento único (M2)

### UI-023 — Substituir listas paralelas pela região única

**Estado inicial:** TODO. **Dependências:** UI-010, UI-021. **Requisitos:** R03, R04, R07.

**Áreas:** `OperationalHome.tsx`; `HomeCards e componentes de entries`.

**Passos:**
1. Renderizar cabeçalho, filtros compactos e uma lista paginada de grupos.
2. Incorporar pergunta/resultado na linha; remover da composição padrão listas duplicadas e feed independente.
3. Preservar componentes antigos para consumidores/fallback sem carregá-los ocultos por CSS.

**Aceite:** Nenhum novo menu Harnesses/Execuções; usuário vê a mesma atividade uma vez.

**Cenários focais:** T-HOME-01, T-HOME-02, T-HOME-03.

### UI-024 — Implementar expansão de sessões e conexões ociosas

**Estado inicial:** TODO. **Dependências:** UI-023. **Requisitos:** R03, R05, R06.

**Áreas:** `HomeEntryGroup/row propostos`; `carregamento de filhos`.

**Passos:**
1. Grupo com um item não exige expansão extra; múltiplos itens têm nomes e estados individuais.
2. Mostrar conexões/sessões não cobertas pelo trabalho com label correto e ação de observação/conversa.
3. Preservar IDs e anchors quando tarefa recebe executor ou sai da página.

**Aceite:** Duas sessões do mesmo agente abrem individualmente; warm e idle não contam como trabalho.

**Cenários focais:** T-HOME-04, T-HOME-05, T-DATA-03, T-DATA-12, T-PANEL-04.

### UI-025 — Aplicar filtros, ordem e vazio proporcionais

**Estado inicial:** TODO. **Dependências:** UI-023, UI-024. **Requisitos:** R03, R07, R16.

**Áreas:** `OperationalHome/controller`; `preferências de apresentação`.

**Passos:**
1. Filtros rápidos selecionam o mesmo conjunto; janela de recentes não oculta unseen rastreável.
2. Manter item sob interação estável e oferecer aplicação controlada de reordenação.
3. Tratar zero/um agente, erro parcial, projeto sem atividade e acesso revogado.

**Aceite:** Home simples com poucos dados; erro não vira onboarding nem atividade zero.

**Cenários focais:** T-HOME-06, T-HOME-07, T-HOME-08, T-HOME-09, T-RESULT-05.

### UI-026 — Ligar ações básicas e incidentes globais

**Estado inicial:** TODO. **Dependências:** UI-008, UI-025. **Requisitos:** R07, R08, R16.

**Áreas:** `Home rows`; `AttentionInspection`; `shell global`.

**Passos:**
1. Responder/acompanhar/ver resultado abre alvo exato, sem página genérica intermediária.
2. Incidente Server gera aviso compacto somente quando existe, excluído das contagens de projeto.
3. Fila integral é painel do sino; nenhuma lista constante concorrente.

**Aceite:** Toda pendência essencial é alcançável no básico, incluindo o fallback.

**Cenários focais:** T-ATTN-01, T-ATTN-03, T-ATTN-06, T-HOME-10.

### UI-027 — Adaptar atualização compartilhada à lista única

**Estado inicial:** TODO. **Dependências:** UI-021, UI-025. **Requisitos:** R03, R06, R16.

**Áreas:** `useHomeOverview/homeController`; `useSSE/Attention existentes`.

**Passos:**
1. Mapear invalidações de entries/filhos e relógio; agrupar bursts e limitar requisições.
2. Descartar resposta antiga por geração; ressincronizar após reconnect/gap/aba retornada.
3. Não consultar transcript de todas as sessões nem abrir streams por item.

**Aceite:** Atualização não duplica/move indevidamente linhas, não perde eventos finais nem mascara fonte stale.

**Cenários focais:** T-LIVE-01, T-LIVE-02, T-LIVE-03, T-LIVE-04, T-LIVE-05.

### UI-028 — Qualificar comportamento da Home no navegador

**Estado inicial:** TODO. **Dependências:** UI-026, UI-027. **Requisitos:** R03, R04, R05, R06, R16.

**Áreas:** `testes frontend/browser`; `fixtures de UI`.

**Passos:**
1. Abrir Home, filtrar, expandir, paginar, tratar falha e trocar projetos.
2. Conferir uma única região principal de listas no estado padrão e ausência de dados ocultos pesados.
3. Medir acesso à sessão/resultados e estabilidade visual; registrar capturas de fixture.

**Aceite:** M2 parcial: acompanhamento único real, sem substituir comportamento por mock estático.

**Cenários focais:** T-HOME-01, T-HOME-04, T-HOME-08, T-HOME-10, T-LIVE-06.

## PR-05 — Painel contextual e interações (M2)

### UI-029 — Extrair viewer de sessão reutilizável

**Estado inicial:** TODO. **Dependências:** UI-019. **Requisitos:** R05, R06, R13.

**Áreas:** `SessionTerminalModal.tsx`; `RuntimeSessionTail/RuntimeHistory`; `RuntimeTerminal.tsx`.

**Passos:**
1. Separar corpo de sessão e wrapper modal mantendo consumidores existentes.
2. Revalidar scope completo e preservar tail/histórico/erros de refresh.
3. Adaptar maximizar para a camada contextual atual, sem dialog aninhado quando embutido.

**Aceite:** Um viewer compartilhado abre sessão exata com ou sem operação; saída continua read only.

**Cenários focais:** T-PANEL-01, T-PANEL-04, T-PANEL-05, T-PANEL-06.

### UI-030 — Compor painel com contexto, sessão e entrega

**Estado inicial:** TODO. **Dependências:** UI-029, UI-026. **Requisitos:** R05, R07, R13.

**Áreas:** `HomeInspection.tsx`; `CanonicalInspection`; `drawer atual`.

**Passos:**
1. Abrir aba adequada para acompanhar/responder/resultado; manter sessão selecionada.
2. Mostrar pedido/autoria, saída, artefatos e detalhes técnicos sob demanda.
3. Mais de uma sessão exige seleção explícita; ausência de captura externa é explicada.

**Aceite:** Não há navegação para procurar o registro; painel não promete memória/TUI nativa.

**Cenários focais:** T-PANEL-02, T-PANEL-03, T-PANEL-07, T-EXT-03.

### UI-031 — Reutilizar decisões e controles exatos

**Estado inicial:** TODO. **Dependências:** UI-030. **Requisitos:** R07, R10, R14.

**Áreas:** `NativeQuestions/CanonicalNativeDecision`; `RuntimeOperations e recovery existentes`.

**Passos:**
1. Conectar perguntas, permissões, interrupt e close apenas conforme capacidade e autoridade atuais.
2. Preservar revisão/CAS/intenção e distinguir decisão registrada de aplicada.
3. Resultado incerto oferece inspeção; pergunta de agente não aceita personificação.

**Aceite:** Nenhum efeito genérico/duplicado ou interrupção de sessão irmã.

**Cenários focais:** T-ATTN-02, T-ATTN-04, T-ATTN-05, T-PANEL-08, T-PANEL-09.

### UI-032 — Proteger foco, rascunho, histórico e scroll

**Estado inicial:** TODO. **Dependências:** UI-030, UI-031. **Requisitos:** R05, R14, R15, R16.

**Áreas:** `AgentActionModal/home guard`; `home_target/history`; `RuntimeTerminal scrollback`.

**Passos:**
1. Usar uma camada ativa; guard antes de trocar alvo/projeto/sino.
2. Preservar scroll/foco na volta e não remontar formulário em refresh.
3. Limpar em logout/revogação e validar browser history/links antigos.

**Aceite:** Fluxo teclado/voltar/maximizar coerente, sem respostas perdidas ou enviadas ao alvo errado.

**Cenários focais:** T-PANEL-10, T-PANEL-11, T-PANEL-12, T-A11Y-02, T-A11Y-03.

### UI-033 — Integrar vistos, artefatos e continuidade

**Estado inicial:** TODO. **Dependências:** UI-031, UI-032. **Requisitos:** R03, R07, R10, R14.

**Áreas:** `result_unseen/preferences`; `Artifacts preview`; `continuation.ts`.

**Passos:**
1. Marcar visto pela ocorrência/revisão sem watermark em massa ou inbox ACK.
2. Abrir preview/download existente com autorização e sanitização.
3. Continuar só contexto validado; sessão fechada pede intenção nova e não latest.

**Aceite:** Entrega permanece correlacionada, leitura não conclui/autoriza nada e continuidade é explícita.

**Cenários focais:** T-RESULT-01, T-RESULT-02, T-RESULT-03, T-RESULT-04, T-RESULT-06.

### UI-034 — Qualificar inspeção e concorrência no navegador

**Estado inicial:** TODO. **Dependências:** UI-033. **Requisitos:** R05, R07, R14, R16.

**Áreas:** `testes reais browser`; `peers sintéticos controlados`.

**Passos:**
1. Testar output ao vivo e histórico, edição com refresh e duas abas decidindo o mesmo pedido.
2. Testar session end, auth expired, campo modificado e erro após decisão commitada.
3. Distinguir teste de componente e campanha com harness real em evidências.

**Aceite:** M2 tem sessão e decisões utilizáveis; race e retorno visual foram exercitados.

**Cenários focais:** T-PANEL-06, T-PANEL-09, T-PANEL-11, T-ATTN-04, T-SEC-03.

## PR-06 — Onboarding UI e Connector integrado (M3)

### UI-035 — Expor retomar/adicionar no onboarding da UI

**Estado inicial:** TODO. **Dependências:** UI-016, UI-030. **Requisitos:** R09, R10, R17.

**Áreas:** `Home Conectar agente`; `fluxo de conexão existente`; `lookup autorizado de bindings`.

**Passos:**
1. Abrir fluxo curto com conexões do projeto e opção adicionar, sem grade administrativa.
2. Reutilizar seleção/revisão/Finish; personalização apenas como expansão secundária.
3. Distinguir browser, host Server e host Connector; não descobrir binários no browser.

**Aceite:** Usuário conecta outro harness pela Home sem entrar em Avançado nem duplicar identidade existente.

**Cenários focais:** T-ONB-01, T-ONB-02, T-ONB-03, T-ONB-04.

### UI-036 — Implementar retomar/adicionar no Connector

**Estado inicial:** TODO. **Dependências:** UI-004, UI-016. **Requisitos:** R09, R10, R12, R17.

**Áreas:** `Connector CLI connect/configure`; `aliases/checkpoints/drafts existentes`.

**Passos:**
1. Consultar conexões do mesmo destino/projeto/identidade e oferecer retomar/adicionar antes de replace.
2. Preservar bootstrap, workspace e caminhos locais do host; identificar necessidade de novo agente.
3. Manter perfil ocupado, revisões pendentes e contrato interativo/JSON atual.

**Aceite:** Adicionar não revoga máquina anterior por engano e não contorna política de identidade.

**Cenários focais:** T-CONN-01, T-CONN-02, T-CONN-03, T-CONN-04.

### UI-037 — Conectar revisão remota e continuidade sem dashboard obrigatório

**Estado inicial:** TODO. **Dependências:** UI-036, UI-035. **Requisitos:** R11, R12, R14, R17.

**Áreas:** `remote-project-setup/remote terminal`; `proposal/receipt atuais`; `controls básicos de aprovação`.

**Passos:**
1. Operador aprova pelo terminal ou UI básica com sua própria autoridade.
2. Connector recupera mesmo root e daemon após fechar CLI; nunca recebe chave de operador.
3. Publicar estado da conexão na Home sem cadastro manual extra ou segundo Finish.

**Aceite:** Fluxo remoto convergente; await approval não é Ready; perda de resposta não duplica setup.

**Cenários focais:** T-CONN-05, T-CONN-06, T-CONN-07, T-SVC-03.

### UI-038 — Preservar daemon e opção de login no novo fluxo

**Estado inicial:** TODO. **Dependências:** UI-015, UI-036. **Requisitos:** R11, R12, R14, R17.

**Áreas:** `service lifecycle Server/Connector`; `connect_login e startup existentes`.

**Passos:**
1. Reutilizar instância/supervisor único em retomar/adicionar; não iniciar daemon por perfil.
2. Mostrar suporte real de login e pedir consentimento separado quando necessário.
3. Preservar intents de startup pendente, parada explícita e tratamento de Server remoto offline.

**Aceite:** Nova conexão não reinicia os outros trabalhos, renova grants ou instala serviço ocultamente.

**Cenários focais:** T-SVC-01, T-SVC-02, T-SVC-03, T-SVC-05, T-SVC-06.

### UI-039 — Qualificar a jornada multi-harness entre superfícies

**Estado inicial:** TODO. **Dependências:** UI-035, UI-037, UI-038. **Requisitos:** R09, R10, R11, R12, R17, R18.

**Áreas:** `tests CLI/HTTP/browser/Connector`; `fixtures por host`.

**Passos:**
1. Criar Codex e Claude no mesmo projeto, retomar cada conexão e abrir sessões na Home.
2. Comparar IDs, bindings, permissões e history antes/depois nos três caminhos.
3. Testar cancelamento, autoridade revogada, pasta homônima e concorrência de cadastro.

**Aceite:** Jornada completa sem nome técnico de perfil e sem interferência entre conexões; remoto coberto no nível apropriado.

**Cenários focais:** T-ONB-05, T-ONB-06, T-CONN-07, T-CLI-21, T-QUAL-02.

## PR-07 — Regressão e qualificação (M3)

### UI-040 — Executar regressão de segurança e semântica

**Estado inicial:** TODO. **Dependências:** UI-022, UI-028, UI-034, UI-039. **Requisitos:** R06, R12, R13, R14, R16.

**Áreas:** `suite Python/HTTP`; `testes auth/contexto/ações`.

**Passos:**
1. Rodar matrizes de escopo e operador/agent key, 403 e referências forjadas.
2. Verificar consultas sem efeitos, fatos nativos versus externos e nenhuma deduplicação por nome.
3. Verificar receipts/incerteza, grant e claim/epoch após reconexão e UI rollback.

**Aceite:** Todos os cenários críticos passam ou bloqueiam explicitamente a qualificação; nenhum bypass aceito.

**Cenários focais:** T-SCOPE-01, T-SCOPE-02, T-SCOPE-05, T-SEC-01, T-SEC-02, T-EXT-01, T-EXT-02.

### UI-041 — Qualificar acessibilidade, responsividade e desempenho

**Estado inicial:** TODO. **Dependências:** UI-028, UI-034. **Requisitos:** R03, R05, R16, R18.

**Áreas:** `navegador real`; `fixtures de volume`; `medição atualizada`.

**Passos:**
1. Executar teclado, focus restore, zoom 200%, 360px e tema claro/escuro.
2. Conferir live announcements agrupados, pausa visual e scrollback.
3. Medir p50/p95, payload, queries e polling; registrar bloqueio de leitor de tela real sem falso PASS.

**Aceite:** Relatório compara baseline e resultado; limites atuais são explícitos e não dispensados pela aparência.

**Cenários focais:** T-A11Y-01, T-A11Y-02, T-A11Y-03, T-A11Y-04, T-PERF-01, T-PERF-02, T-PERF-04.

### UI-042 — Executar campanha produtiva real isolada

**Estado inicial:** TODO. **Dependências:** UI-039, UI-040. **Requisitos:** R09, R10, R11, R17, R18.

**Áreas:** `artefatos instalados`; `workspace/home descartáveis`; `harnesses qualificados disponíveis`.

**Passos:**
1. Pedir autorização específica para uso de provedor/credenciais e preparar isolamento.
2. Conectar um harness, adicionar outro, pedir trabalho, observar/decidir/obter resultado e retomar.
3. Qualificar remoto e plataforma somente com ambiente real correspondente; registrar NOT_RUN/BLOCKED separado.

**Aceite:** Evidência real de dois harnesses no mesmo projeto e fluxo terminal/UI; teste sintético não substitui campanha.

**Cenários focais:** T-QUAL-02, T-QUAL-03, T-QUAL-04.

### UI-043 — Validar compreensão e objetivo do produto

**Estado inicial:** TODO. **Dependências:** UI-041, UI-042. **Requisitos:** R01, R02, R03, R05, R09, R18.

**Áreas:** `roteiro de usabilidade com fixture`; `relatório sem dados pessoais`.

**Passos:**
1. Pedir a alguém sem conhecimento da arquitetura conectar/retomar, abrir sessão e encontrar resultado.
2. Contar trocas de tela e interações sem coletar prompts; verificar que Avançado não é etapa obrigatória.
3. Registrar falhas de linguagem/descoberta e corrigir as que impedem o ciclo essencial.

**Aceite:** Critério de poucos passos exercitado; números observados separados de metas.

**Cenários focais:** T-QUAL-05, T-QUAL-06.

## PR-08 — Documentação, pacote e rollout (M3)

### UI-044 — Atualizar documentação e compatibilidade pública

**Estado inicial:** TODO. **Dependências:** UI-039, UI-040. **Requisitos:** R01, R02, R09, R10, R11, R15.

**Áreas:** `HelpModal/onboarding`; `README/docs CLI`; `guias de service e conexão`.

**Passos:**
1. Documentar quatro destinos/Advanced e ações no painel, incluindo o terminal read only.
2. Separar comandos existentes de novos, adicionar exemplos retomar/adicionar e semântica de --plan/JSON.
3. Documentar perfil legado, grant expirado, serviço/login e diagnóstico sem revelar segredos.

**Aceite:** Manual corresponde ao produto entregue; nenhum link para página removida ou instrução insegura.

**Cenários focais:** T-NAV-11, T-CLI-13, T-SVC-04, T-REL-01.

### UI-045 — Empacotar e validar o conjunto compatível

**Estado inicial:** TODO. **Dependências:** UI-040, UI-041, UI-044. **Requisitos:** R11, R13, R17, R18.

**Áreas:** `frontend build`; `wheel/sdist/manifests atuais`; `compatibilidade Core/Connector`.

**Passos:**
1. Executar build/tests e empacotamento conforme CI real, sem atualizar dependências incidentalmente.
2. Instalar em ambiente isolado e provar assets/CLI/API no pacote, não só dev server.
3. Conferir pins/artefatos compatíveis; Core sem mudança passa regressão necessária.

**Aceite:** Pacote exato testado identificado por hash; instalação não depende de checkout irmão ou Node de desenvolvimento.

**Cenários focais:** T-REL-01, T-REL-02, T-REL-03.

### UI-046 — Qualificar migração, fallback e rollback

**Estado inicial:** TODO. **Dependências:** UI-045. **Requisitos:** R08, R11, R12, R15, R16.

**Áreas:** `preferências/aliases UI`; `profiles legados/novos`; `flag de apresentação`.

**Passos:**
1. Testar browser e perfil antigos com novas rotas, reabertura e guarda de rascunhos.
2. Desativar UI nova preservando pendências, sessões, daemon e comandos --profile.
3. Verificar que apresentação não muda flags de execução, autorização ou retenção.

**Aceite:** Rollback não destrói configurações nem reexecuta trabalho; ações básicas seguem disponíveis.

**Cenários focais:** T-REL-04, T-REL-05, T-REL-06, T-SVC-02.

### UI-047 — Fechar rastreabilidade e decidir ativação padrão

**Estado inicial:** TODO. **Dependências:** UI-043, UI-045, UI-046. **Requisitos:** R01, R03, R09, R18.

**Áreas:** `execution/test ledger UI-R1`; `release-report e limitações`.

**Passos:**
1. Ligar todo requisito às tarefas/cenários/evidências e preservar bloqueios anteriores relevantes.
2. Conferir que onboarding local/UI/Connector não foi deixado como opcional ou posterior.
3. Propor ativação padrão da experiência simples apenas com gates cumpridos e autorização de release.

**Aceite:** Relatório final distingue implementado/verificado/bloqueado; plano não declara completo um subconjunto visual.

**Cenários focais:** T-REL-07, T-REL-08.


# 16. Matriz de testes e critérios de aceite

Todos começam em **NOT_RUN**. PASS exige execução e evidência no corte correspondente. Dado/Quando/Então define comportamento, não nomes obrigatórios de testes. Casos de concorrência usam barreiras e relógio controlado, não sleeps como prova. Casos de navegador precisam de navegador real; casos de provedor/SO precisam de campanha própria.

## Baseline

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-BASE-01 | processo | Checkout possui alterações locais e HEAD mais novo. | Iniciar PR-00. | Registrar drift e preservar working tree; não resetar para o SHA do plano. |
| T-BASE-02 | processo | Outro Codex edita os mesmos arquivos. | Definir implementação incremental. | Estabelecer ownership/worktree e integração antes de escrita concorrente. |
| T-BASE-03 | contrato | Há páginas com comparadores de nome e flags. | Mapear navegação. | Todos os destinos, controles e dependências de nomes possuem destino preservado. |
| T-BASE-04 | fixture | Sem credenciais/dados pessoais. | Criar casos de UI e backend. | Reproduzir multi-harness, A→B e falhas com relógio e barreiras determinísticos. |

## Navegação

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-NAV-01 | browser | Dashboard autenticado padrão. | Abrir sidebar. | Exibir somente Home/Conversations/Graph/Artifacts como destinos principais e Advanced secundário. |
| T-NAV-02 | browser | Lista antiga contém Runtimes/Agents/Handoffs. | Abrir novo shell. | Não criar novos destinos Harnesses/Execuções/Sessões ou duplicar atalhos como menus. |
| T-NAV-03 | browser | Índice Advanced aberto. | Acessar cada grupo. | Todos os destinos da matriz estão acessíveis, sem sidebar expandir para dezenas de itens. |
| T-NAV-04 | contrato/browser | Bookmark/seleção salva de Meta-harness ou Policies. | Carregar aplicação nova. | Resolver o componente correto e novo rótulo sem alterar identidade lógica ou permissões. |
| T-NAV-05 | browser | Memory desabilitada. | Abrir Advanced e tentar link direto. | Visibilidade/recusa seguem contratos atuais; navegação não habilita a feature. |
| T-NAV-06 | HTTP/browser | Usuário sem autoridade para ação avançada. | Abrir índice/link direto e chamar API. | API mantém autorização; o índice não concede acesso. |
| T-NAV-07 | browser | Home operacional OFF e aprovação pendente. | Usar shell simples. | Sino/fila básica e controle canônico permanecem disponíveis. |
| T-NAV-08 | browser | Em Graph ou Artifacts surge pergunta. | Abrir sino. | Fila abre no contexto global, sem exigir rota Advanced ou outra Home. |
| T-NAV-09 | browser | Conversations renomeada e mensagens novas. | Entrar/sair e abrir Home. | Comportamento de OPERATOR_VIEWS/vistos preservado; Home não marca tudo visto. |
| T-NAV-10 | contrato/browser | Link antigo home_target e novo alvo session. | Validar ida/volta, voltar/avançar. | Alvo exato preservado; parâmetros inválidos não abrem outro registro. |
| T-NAV-11 | documentação | Guias e introdução antigos. | Pesquisar nomes/caminhos visíveis. | Orientações apontam para acessos reais e diferenciam Conversations de Messages. |
| T-NAV-12 | browser | 360px e menu móvel. | Navegar pelos destinos básicos e Advanced. | Menu fecha corretamente, foco e rótulos acessíveis; sem overflow obrigatório. |

## Projeção e dados

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-DATA-01 | SQLite/HTTP | Handoff possui abertura, submissão, steer e retries. | Projetar Home. | Uma atividade produtiva com tentativas em detalhe, não múltiplas tarefas. |
| T-DATA-02 | SQLite/HTTP | Agente A delega a B sem mensagem do operador. | Ler projeto. | Trabalho de B aparece, com autoria/parentesco corretos. |
| T-DATA-03 | SQLite/HTTP | Sessão viva sem operação ativa. | Listar acompanhamento. | Sessão é alcançável como ociosa/conectada, sem operation_id fictício. |
| T-DATA-04 | SQLite/HTTP | Mesmo agente tem duas conexões/hosts no projeto. | Agrupar. | Contextos distintos; nenhum estado único esconde a sessão bloqueada. |
| T-DATA-05 | SQLite/HTTP | Handoff broadcast ainda OPEN sem claim. | Listar. | Mostrar aguardando responsável; não atribuir ao primeiro candidato/harness. |
| T-DATA-06 | SQLite/HTTP | Resultado, pergunta e arquivos vinculados à atividade. | Compor entries. | Enriquecer a mesma linha; nenhuma segunda lista duplicada. |
| T-DATA-07 | SQLite/HTTP | Resultado retido perdeu o pai por retenção. | Listar Resultados. | Item independente com proveniência e limitação; não fabricar correlação. |
| T-DATA-08 | SQLite/HTTP | Grupo com mais filhos que o limite e vários grupos. | Paginar/expandir. | Todos alcançáveis com total/has_more corretos, sem juntar apenas primeiras páginas. |
| T-DATA-09 | SQLite/HTTP | 20 grupos, primeira página de 10. | Obter resumo. | Total completo autorizado; quantidade de grupos não é quantidade de tarefas. |
| T-DATA-10 | SQLite/HTTP | Join de mensagens/recibos gera multiplicidade. | Contar e paginar. | IDs lógicos únicos e desempate determinístico; nenhum salto silencioso. |
| T-DATA-11 | HTTP | Clientes antigos usam overview V1. | Ativar entries na Home nova. | Contrato antigo continua; endpoint novo segue envelope/limites/revisão. |
| T-DATA-12 | unitário/SQLite | Sessões READY, OPENING, warm e cleanup sem turno. | Classificar atividade. | Não contar como RUNNING produtivo; tipos técnicos disponíveis só como contexto. |
| T-DATA-13 | unitário/SQLite | Claim ou SUBMITTED sem RUNNING. | Apresentar estado. | Mostrar assumido/recebido, não executando ou concluído. |
| T-DATA-14 | unitário/SQLite | Turno SUCCEEDED mas handoff aberto ou cleanup pendente. | Projetar resultado. | Sucesso do turno separado de handoff/limpeza; nenhum convite automático a repetir. |

## Escopo e identidade

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-SCOPE-01 | HTTP/SQLite | Agente global atua em A e B. | Filtrar A antes de total/paginação. | Nenhum dado/contador de B; agentes globais não viram participantes de A sem vínculo. |
| T-SCOPE-02 | HTTP/SQLite | Alvo session pertence a outro executor/projeto. | Forjar URL e resolver. | Recusar sob contrato atual; não vazar existência/conteúdo nem selecionar latest. |
| T-SCOPE-03 | HTTP/SQLite | Visão Todos e vários vínculos por agente. | Ler/paginar. | União autorizada sem duplicar trabalho por vínculo. |
| T-SCOPE-04 | HTTP/SQLite | A envia trabalho a B; filtro visual em A. | Compor estado com fatos de B. | Manter evidência necessária de B e escopo da pendência; não perder classificação de espera. |
| T-SCOPE-05 | HTTP/SQLite | Credencial de agente/monitor em vez de operador. | Consultar Home privilegiada. | Sem herdar trust de operador; comportamento conforme autenticação canônica. |
| T-SCOPE-06 | HTTP/SQLite | Mesmo path local aponta a Servers distintos. | Catalogar candidatos de connect. | Isolar destinos e humanos; não reusar configuração do Server errado. |
| T-SCOPE-07 | HTTP/SQLite | Ocorrência global de Server autorizada. | Filtrar projeto/estado/agente. | Aviso global separado, não multiplicado nos totais de projeto. |

## Home única

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-HOME-01 | browser | Vários trabalhos, pendências e resultados. | Abrir Home padrão. | Uma única região principal de acompanhamento, sem seis listas paralelas. |
| T-HOME-02 | browser | Uma atividade produz resultado e pergunta. | Atualizar Home. | Mesma linha muda/enriquece estado; não reaparece em outro bloco. |
| T-HOME-03 | browser | Sem agentes e dados carregados com sucesso. | Abrir Home. | Uma ação conectar primeiro agente; sem grade de zeros. |
| T-HOME-04 | browser | Duas sessões do mesmo Codex. | Expandir e abrir cada sessão. | Contextos distintos identificados, sem navegação para novo menu. |
| T-HOME-05 | browser | Uma conexão sem sessão e outra com tarefa. | Abrir Todos. | Ambas alcançáveis; conexão sem tarefa não soma execução. |
| T-HOME-06 | browser | Usuário lê grupo expandido enquanto há mudança de prioridade. | Receber atualização. | Não deslocar foco/linha sob interação; atualização controlada. |
| T-HOME-07 | browser | Fonte falha mas outras respondem. | Atualizar. | Mostrar parcialidade e dados válidos; não fingir ausência de agentes. |
| T-HOME-08 | browser | Troca A→B com resposta lenta de A. | Resolver requests fora de ordem. | Descartar A e preservar somente escopo B. |
| T-HOME-09 | browser | Filtro Resultados e resultado unseen antigo dentro da retenção. | Aplicar janela padrão. | Unseen continua alcançável; janela de recentes não apaga novidade. |
| T-HOME-10 | browser | Nenhuma ocorrência global ou de atenção. | Renderizar. | Sem painel vazio Server/Needs you; recursos continuam no sino/filtro. |

## Painel e sessão

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-PANEL-01 | contrato/HTTP | Sessão sem operação. | Codificar/resolver alvo session. | Abertura sem operation_id e escopo canônico conferido. |
| T-PANEL-02 | browser | Uma linha de execução. | Clicar Abrir. | Painel do registro correto, não página genérica para pesquisar. |
| T-PANEL-03 | HTTP/browser | Sessão selecionada fechou/revogou. | Tentar continuar. | Histórico/recusa explícitos; não substituir por última sessão. |
| T-PANEL-04 | browser | Atividade com mais de uma sessão vinculada. | Acompanhar. | Seletor explícito de contexto/host; nenhum primeiro item automático ambíguo. |
| T-PANEL-05 | browser | Drawer contém terminal. | Maximizar/restaurar. | Uma camada gerenciada, sem dois dialogs modais/foco concorrente. |
| T-PANEL-06 | browser | Output cresce durante scrollback antigo. | Receber eventos e carregar anteriores. | Preservar âncora; auto-scroll somente quando ativado; gaps explícitos. |
| T-PANEL-07 | browser | Pedido, decisões e arquivos da atividade. | Inspecionar. | Conteúdo autorizado reunido; detalhes técnicos recolhidos e lazy. |
| T-PANEL-08 | HTTP/integrado | Dois turnos/sessões do mesmo agente. | Interromper um alvo específico. | Outro turno/sessão intacto; efeito e resultado corretamente correlacionados. |
| T-PANEL-09 | HTTP/browser | Decisão commitada com resposta perdida. | Reabrir/repetir recuperação. | Mesma decisão/operação; não duplicar nem assumir aplicação nativa. |
| T-PANEL-10 | browser | Rascunho de resposta ativo. | Mudar projeto/sino/alvo ou pressionar Escape. | Guard funciona e não transporta resposta a outro pedido. |
| T-PANEL-11 | browser | Formulário em edição recebe refresh/reauth. | Atualizar/revogar. | Refresh preserva; revogação limpa e bloqueia envio. |
| T-PANEL-12 | browser | Item mudou grupo/saiu do filtro. | Fechar drawer ou usar Voltar. | Restaurar foco/scroll em âncora válida, sem abrir a linha que tomou sua posição. |

## Atenção e decisões

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-ATTN-01 | HTTP/browser | Pergunta ao operador em sessão ativa. | Clicar Responder. | Abrir formulário canônico exato com opções/tipos originais. |
| T-ATTN-02 | HTTP/browser | Pergunta destinada a outro agente. | Abrir a mesma atividade como operador. | Acompanhar sem personificar destinatário ou ganhar direito de resposta. |
| T-ATTN-03 | HTTP/browser | Aprovação expira ou é decidida em outra aba. | Confirmar de tela antiga. | Revalidar revisão/prazo e mostrar resolução/conflito, sem segunda decisão. |
| T-ATTN-04 | HTTP/browser | Duas abas/duplo clique para mesma decisão. | Enviar simultaneamente. | CAS/idempotência atuais preservam uma decisão efetiva. |
| T-ATTN-05 | HTTP/browser | Permissão e pergunta textual coexistem. | Enviar conversa ao modelo. | Texto comum não conta como aprovação/resposta canônica. |
| T-ATTN-06 | HTTP/browser | Home nova OFF ou função de interceptar novas aprovações OFF. | Abrir pendência antiga ainda decidível. | Acesso básico/canônico permanece; não esconder somente por flag. |

## Resultados e vistos

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-RESULT-01 | HTTP/browser | Entrega correlacionada com três arquivos. | Renderizar Resultados. | Um item com arquivos, não quatro tarefas. |
| T-RESULT-02 | HTTP/browser | Resultado em VERIFYING. | Abrir. | Aguardando verificação; não concluir/aceitar ao visualizar. |
| T-RESULT-03 | HTTP/browser | Preferência result_unseen revisionada. | Marcar visto e publicar revisão nova. | A primeira preferência não oculta o novo episódio e não gera ACK. |
| T-RESULT-04 | HTTP/browser | Resultados fora da página/projeto. | Abrir Home ou prévia. | Nenhum watermark em massa nem marcação invisível. |
| T-RESULT-05 | HTTP/browser | Fonte sem contrato de visto. | Mostrar resumo. | Usar Recentes/not_tracked, sem número inventado de novos. |
| T-RESULT-06 | HTTP/browser | Artefato HTML/conteúdo não autorizado. | Preview/download. | Sanitização/isolamento/autorização preservados; sem privilégios novos. |

## Atualização

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-LIVE-01 | controller/browser | Commit entre snapshot e assinatura/reconnect. | Atualizar Home. | Releitura cobre janela; resultado final não é perdido. |
| T-LIVE-02 | controller/browser | Eventos duplicados/fora de ordem e burst de tokens. | Processar invalidações. | Sem cartões duplicados/regressão de estado; requests agrupados/limitados. |
| T-LIVE-03 | controller/browser | Fonte externa expira com SSE conectado. | Avançar relógio. | Fonte permanece stale; conexão ao stream não revalida seu conteúdo. |
| T-LIVE-04 | controller/browser | Navegador vai background e retorna. | Retomar interação. | Reduz carga e revalida snapshot/ações; não usa estado antigo como consentimento. |
| T-LIVE-05 | controller/browser | Muitas sessões aparecem na lista. | Deixar só um painel aberto. | Uma observação de detalhe ativa; não abrir tail/SSE por linha. |
| T-LIVE-06 | controller/browser | Pausa visual e trabalho real prossegue. | Pausar e aplicar atualizações. | Agentes não são pausados; rascunhos/decisões mantêm validação. |

## Onboarding local e scripts

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-CLI-01 | CLI/integrado | Projeto novo com único harness qualificado. | connect interativo. | Sugerir seleção/revisão curta; nenhum nome de profile obrigatório. |
| T-CLI-02 | unitário/CLI | Perfil legado project-hash e novo perfil. | Descobrir conexões. | Ambos encontrados sem renomear nem alterar seus checkpoints. |
| T-CLI-03 | unitário/CLI | Nomes/path iguais em contextos diferentes. | Resolver candidatos. | Não deduplicar identidades ou destinos por string amigável. |
| T-CLI-04 | CLI/integrado | Codex configurado no projeto. | Adicionar Claude pelo picker. | Novo profile/identidade sugeridos e persistidos; Codex inalterado. |
| T-CLI-05 | CLI | Há uma conexão e nenhum seletor explícito. | connect. | Oferecer Retomar/Adicionar/Cancelar em vez de adoção ou criação silenciosa. |
| T-CLI-06 | CLI | Há várias conexões, duas de Codex. | Escolher retomar. | Exigir identificação da conexão correta; nunca a primeira/latest. |
| T-CLI-07 | CLI | --profile existente e --client incompatível. | Invocar connect. | Recusar substituição explícita com orientação; sem criar outra conexão inesperada. |
| T-CLI-08 | CLI/HTTP | Resposta de Finish foi perdida. | Retomar a mesma solicitação. | Mesmo receipt, agent_id e binding; sem novo teste ou grant. |
| T-CLI-09 | CLI/concorrência | Dois terminais adicionam conexões simultaneamente. | Reservar perfis/commitar setup. | Sem overwrite; intents independentes ou conflito honesto; locks curtos. |
| T-CLI-10 | CLI/HTTP | Checkpoint com efeito incerto anterior. | connect sem nova intenção. | Recuperar o mesmo pedido; não criar substituto para escapar do estado. |
| T-CLI-11 | CLI | JSON/noninteractive com várias conexões e sem seletor. | connect --json. | Retornar seleção necessária estruturada, sem perguntar nem criar modelo/identidade. |
| T-CLI-12 | CLI | Nova conexão scriptada com --new-connection e --profile explícito e estável. | Repetir comando após falha de resposta. | Recuperar a mesma criação; conteúdo diferente conflita. |
| T-CLI-13 | CLI | Server ausente. | connect --plan, status ou doctor. | Não autostart nem probe/inferência; limite relatado corretamente. |
| T-CLI-14 | CLI | Mesmo diretório usado com operator profiles remotos diferentes. | Escolher/retomar. | Contextos isolados; metadado local não vira autoridade sobre outro Server. |
| T-CLI-15 | CLI | Perfil com escritor ativo. | Tentar retomar em outro terminal. | PROFILE_BUSY/caminho canônico; não remover lock ou clonar como workaround. |
| T-CLI-16 | CLI/HTTP | Envio pendente de resolução. | work resume ou retomada no connect. | Recuperar intenção exata antes de pedir sessão nova. |
| T-CLI-17 | CLI/HTTP | Uma sessão compatível lembrada. | Selecionar continuar. | Apresentar contexto correto; nada produtivo enviado antes do pedido. |
| T-CLI-18 | CLI/HTTP | Várias sessões autorizadas na conexão. | Continuar contexto. | Escolha explícita; --session-id é respeitado e verificado. |
| T-CLI-19 | CLI/HTTP | Sessão fechada/grant incompatível. | Retomar. | Histórico ou recusa; nova sessão/autoridade requer intenção e revisão próprias. |
| T-CLI-20 | CLI | Usuário cancela picker/revisão antes do teste. | Cancelar. | Nenhum agente/binding/grant/trabalho novo; declarar se serviço já permaneceu ativo. |
| T-CLI-21 | CLI/HTTP | Agente teve papel/modelo/permissões customizados. | Reconectar e adicionar outro agente. | O primeiro mantém suas escolhas; o novo usa apenas o preset consentido. |

## Onboarding pela UI

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-ONB-01 | browser/HTTP | Home com uma conexão. | Conectar agente. | Oferecer abrir existente/adicionar sem abrir administração avançada. |
| T-ONB-02 | browser/HTTP | Novo harness local selecionado. | Revisar/confirmar. | Mesmos serviços de setup/Finish do CLI, sem segunda implementação de autoridade. |
| T-ONB-03 | browser/HTTP | Dashboard aberto em device diferente do Server. | Escolher execução local/remota. | Explicar host real; navegador não detecta executáveis da máquina do usuário por suposição. |
| T-ONB-04 | browser/HTTP | Usuário escolhe Personalizar. | Editar configuração. | Expandir controles existentes sem trocar identidade/preset já salvo ou tornar personalização obrigatória. |
| T-ONB-05 | browser/HTTP | Conexão criada no CLI e UI aberta depois. | Listar/retomar. | Mesmo agente/binding/sessão; sem novo cadastro manual na UI. |
| T-ONB-06 | browser/HTTP | Pasta/nome iguais mas workspace sem permissão. | Adicionar conexão no projeto. | Não conceder acesso por semelhança; seleção/autorização canônicas. |

## Connector remoto

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-CONN-01 | Connector/integração | Connector tem alias/conexão compatível. | connect no projeto. | Retomar/adicionar vem antes de tratar criação como Replace/Abort obrigatório. |
| T-CONN-02 | Connector/integração | Outro harness no mesmo host/projeto. | Adicionar nova conexão. | Alias/checkpoint próprio e configuração anterior preservada. |
| T-CONN-03 | Connector/integração | Mesmo agente já vinculado a outra máquina. | Solicitar nova conexão. | Política de máquina respeitada; nenhum revoke/replacement oculto. |
| T-CONN-04 | Connector/integração | Wizard Connector atual rejeita --json. | Invocar com JSON/noninteractive. | Contrato antigo preservado; sem pergunta de credencial ou prompt escondido. |
| T-CONN-05 | Connector/integração | Host aguarda aprovação remota. | Fechar CLI e aprovar como operador pelo terminal. | Daemon/mesmo root continuam; sem credencial de operador no host. |
| T-CONN-06 | Connector/integração | Workspace compartilhado e pastas distintas nos hosts. | Retomar/bootstrap. | Workspace lógico preservado e cada pasta local mantida; sem copiar path do Server. |
| T-CONN-07 | Connector/integração | Perda de resposta durante aprovação/Finish/reconnect. | Retomar mesmo root. | Receipts/child IDs recuperados; não renovar grant ou duplicar identidade/proposta. |

## Daemon e lifecycle

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-SVC-01 | integração/lifecycle | Server já ativo e nova conexão no mesmo projeto. | connect adicionar. | Reutilizar a instância/supervisor; não daemon por profile. |
| T-SVC-02 | integração/lifecycle | Trabalho admitido e painel/CLI fechados. | Fechar UI, /quit, Ctrl+C do observador. | Não interromper trabalho nem encerrar serviço. |
| T-SVC-03 | integração/lifecycle | Destino é Server remoto indisponível. | Conectar/reconectar. | Erro/espera remota; nenhum Server local substituto. |
| T-SVC-04 | integração/lifecycle | Comando de leitura/plano e serviço ausente. | status/doctor/plan. | Sem autostart/inferência; checkpoints declarados somente nos comandos que os admitem. |
| T-SVC-05 | integração/lifecycle | Tarefa de login instalada/desabilitada ou startup pendente. | Retomar/adicionar. | Não reinstalar/habilitar silenciosamente; usar operação já revisada. |
| T-SVC-06 | integração/lifecycle | Grant expirado/resultado incerto e serviço reinicia. | Reconnect. | Não renovar orçamento nem reexecutar; reconciliar pela identidade original. |

## Observação externa

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-EXT-01 | projeção/browser | Herdr reporta working ou done. | Projetar Home. | Rótulo de observação; não RUNNING gerenciado, sucesso canônico, ACK ou claim release. |
| T-EXT-02 | projeção/browser | Mesmo nome/agente aparece em telemetria e runtime sem associação comprovada. | Agrupar. | Não fundir por nome/PID; preservar origens e contagens. |
| T-EXT-03 | projeção/browser | Harness externo sem captura de output. | Abrir contexto. | Mostrar somente evidências disponíveis e limitação; não inventar terminal/histórico. |

## Segurança

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-SEC-01 | HTTP/browser | Snapshot/expansão/detail GET repetidos. | Ler Home e abrir painel. | Não criar session, grant, mensagem, claim, ACK, teste ou decisão; auth metadata existente separada. |
| T-SEC-02 | HTTP/browser | URL/log/output contém dado malicioso ou segredo. | Renderizar/abrir link. | Sem ação arbitrária, segredo em URL, HTML privilegiado ou ampliacão de escopo. |
| T-SEC-03 | HTTP/browser | Logout/403 enquanto há snapshot/rascunho. | Atualizar e usar Voltar. | Limpar protegido e bloquear submit; histórico não restaura payload autorizado anteriormente. |

## Acessibilidade

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-A11Y-01 | browser/assistivo | Sem mouse. | Navegar sidebar/filtros/expansão/Advanced. | Controles operáveis e rótulos/estado acessíveis sem role menu artificial. |
| T-A11Y-02 | browser/assistivo | Drawer/modal aberto. | Tab/Escape/fechar/maximizar. | Foco conforme modalidade, guard e retorno estável; nenhuma armadilha em dialogs aninhados. |
| T-A11Y-03 | browser/assistivo | Output ao vivo, zoom 200% e 360px. | Ler/pausar/scrollback. | Ações alcançáveis, avisos agrupados, estado com texto e sem perda de leitura. |
| T-A11Y-04 | browser/assistivo | Leitor de tela real/ponte do SO indisponível. | Qualificar acessibilidade. | Registrar bloqueio; resultado Node/DOM não é promovido a campanha assistiva real. |

## Desempenho

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-PERF-01 | carga/instrumentação | Fixtures de 1/10/100 agentes. | Medir entries e expansão. | Queries não crescem por agente; overview não traz transcripts ou consulta provedores. |
| T-PERF-02 | carga/instrumentação | 1.000 atividades e 100.000 eventos. | Paginar e medir p50/p95. | Limites/cursors funcionam; registrar hardware/volume/meta atingida ou não. |
| T-PERF-03 | carga/instrumentação | Novo índice proposto. | Comparar EXPLAIN e escrita. | Justificar ganho e custo; migração aditiva com próxima revisão real. |
| T-PERF-04 | carga/instrumentação | Burst de stream e painel único. | Medir requests/streams/payload. | Sem N streams, loops por token ou listas ocultas carregadas; payload inicial com limite. |

## Qualificação real e compreensão

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-QUAL-01 | campanha/usuário | Fixture reproduzível de jornada. | Executar sem produção. | Trabalhos, perguntas e resultados controlados com evidência por cenário. |
| T-QUAL-02 | campanha/usuário | Dois harnesses reais qualificados e consentimento. | Conectar A, adicionar B, pedir e retomar. | IDs/permissões preservados; resultados e sessão na Home; nenhuma exigência de nome de profile. |
| T-QUAL-03 | campanha/usuário | Host remoto real e consentimento. | Usar Connector, aprovar e observar. | Publicação, sessão, perguntas e resultado comprovados na topologia; sem inferir de peers sintéticos. |
| T-QUAL-04 | campanha/usuário | Sistema operacional/plataforma não exercitado. | Preparar relatório. | Não anunciar qualificação universal de login/reboot ou harness. |
| T-QUAL-05 | campanha/usuário | Pessoa sem conhecer a arquitetura do Nexus. | Conectar/retomar, pedir, acompanhar, responder e achar entrega. | Concluir sem Advanced; registrar atritos e tempo observados, sem inventar métricas. |
| T-QUAL-06 | campanha/usuário | Conjunto conhecido com execução, bloqueio e resultado. | Abrir Home. | Conseguir identificar os três e abrir a sessão em uma ação quando não ambígua; medir e registrar. |

## Pacote, migração e entrega

| ID | Nível | Dado | Quando | Então |
|---|---|---|---|---|
| T-REL-01 | integração/processo | Checkout atualizado. | Executar scripts/documentação/build. | Comandos existentes conferidos; front empacotado corresponde aos contratos novos. |
| T-REL-02 | integração/processo | Wheel/sdist construídos. | Instalar em ambiente isolado sem checkout irmão. | Assets, APIs e CLI funcionam no pacote real; hashes e comando registrados. |
| T-REL-03 | integração/processo | Server/Connector/Core com pins/manifestos. | Rodar integração. | Tuple compatível; não downgrade incidental nem alteração de Core desnecessária. |
| T-REL-04 | integração/processo | Browser e perfis anteriores. | Atualizar e reabrir. | Aliases, seleção e checkpoints preservados; IDs de setup não mudam. |
| T-REL-05 | integração/processo | Home simples ativada e trabalho em andamento. | Voltar à apresentação anterior. | Daemon/sessões/grants intactos; sino e ações básicas acessíveis. |
| T-REL-06 | integração/processo | Novos perfis gerados pelo picker. | Usar comando explícito --profile ou fallback qualificado. | Conexões continuam utilizáveis; reversão não apaga atalhos/identidades. |
| T-REL-07 | integração/processo | UI visual concluída, onboarding de segundo harness não. | Avaliar entrega. | Plano permanece incompleto; R09/R17/R18 são gates obrigatórios. |
| T-REL-08 | integração/processo | Testes/campanhas pendentes e flag atual OFF. | Decidir release/default. | Registrar limites e aprovação; não marcar pronto/ativar em produção automaticamente. |

---

# 17. Execução dos testes, evidências e comandos

## 17.1 Preparação

Ler instruções locais e scripts reais no HEAD. No snapshot, `frontend/package.json` define `npm test` por Node e `npm run build` por TypeScript/Vite. Esses comandos não equivalem a uma campanha real de navegador. [S17]

```sh
# No diretório frontend, depois de conferir dependências e lock do checkout:
npm ci
npm test
npm run build
```

No Python, usar o ambiente/extras e wheels selecionados pelo repositório. A inspeção observou uma dependência Core fixada e o ledger registra uso de artefatos em `vendor/wheels`; não resolver ambiente com downgrade silencioso nem regenerar lock para “fazer passar”. Conferir CI/CONTRIBUTING antes de executar o bootstrap.

```sh
# Dentro do ambiente de teste preparado conforme o repositório:
python -m pytest
```

Durante desenvolvimento rodar as suites focais reais de cada PR, depois a regressão relevante e a suite completa exigida pelo projeto. Não publicar nomes fictícios de testes como comandos validados. O executor pode criar arquivos novos de teste, mas deve registrar seu caminho efetivo.

Localizar e reaproveitar a infraestrutura de navegador que já qualificou Home. Não introduzir Playwright/Cypress ou outro stack duplicado sem verificar o existente. Para CLI interativa, usar processo/PTY de teste quando necessário; unit test de função do picker não comprova stdout, Ctrl+C e comportamento TTY.

## 17.2 Camadas de comprovação

| Camada | Comprova | Não comprova sozinha |
|---|---|---|
| Funções puras | Estados, chaves, ordem, aliases, escolha de intenção. | UI real, persistência concorrente, provedores. |
| SQLite/repositório | Agrupamento, filtro, total, cursor, índice, transação. | Autorização HTTP/UI, foco ou terminal real. |
| HTTP/API | Auth, schema, CAS, ações e erros canônicos. | Uso em navegador/TTY. |
| Componentes/Node | Renderização/controle sob ambiente de teste. | Leitor de tela ou interações reais do browser. |
| Navegador | Foco, guard, drawer, history, scroll, DOM, mobile e chamadas reais do cenário. | Provedor nativo, reboot/login real. |
| CLI em processo | Argumentos, TTY/JSON, cancelamento, checkpoints, locks e seleção. | Topologia remota real quando peers são sintéticos. |
| Harness/host reais | Integração concreta da versão/plataforma/topologia exercitada. | Todas as versões/plataformas futuras. |
| Usuário observando a jornada | Compreensão e quantidade real de interações. | Correção de todos os contratos de concorrência. |

## 17.3 Campanha final demonstrável

Preparar home e projeto descartáveis, orçamento limitado e consentimento específico para provedores. Não usar o banco pessoal ou interromper agentes do usuário.

1. Instalar o conjunto empacotado em ambiente isolado.
2. Rodar `connect` a partir de projeto novo e configurar um harness qualificado.
3. Repetir `connect`, escolher Adicionar outro e configurar um segundo colaborador, sem inventar `--profile` manualmente.
4. Conferir que Server/daemon foram reutilizados e a primeira configuração/identidade permaneceu igual.
5. Pedir trabalho pelo terminal e abrir a Home; mostrar quatro destinos e Avançado.
6. Observar uma execução, uma espera/pergunta e uma entrega na lista única, incluindo ao menos uma colaboração agente→agente.
7. Abrir o contexto de cada sessão no painel; exercer live tail e histórico; responder/decidir quando autorizado.
8. Conferir resultado, artefato e visto; continuar a sessão correta sem misturar contextos.
9. Fechar terminal/UI, voltar e escolher conexão existente; recuperar o mesmo contexto/pedido conforme os contratos reais.
10. Exercitar Connector/host remoto numa campanha separada quando disponível, com revisão do operador pelo terminal e sem chave administrativa no host.
11. Testar fallback da UI sem parar trabalho e sem esconder pendências.

Se não houver consentimento/ambiente para alguma etapa real, executar as camadas não produtivas, registrar o bloqueio e não marcar essa qualificação como pronta. A implementação pode ser entregue para revisão com essa limitação; o relatório não pode chamar o produto inteiro de validado.

## 17.4 Formato mínimo de relatório por PR

```text
PR/etapa:
HEAD inicial / HEAD final:
Requisitos e tarefas:
Código reutilizado:
Arquivos modificados:
Mudanças públicas / compatibilidade:
Migrações / efeitos locais:
Comandos executados e códigos de saída:
Cenários PASS / FAIL / NOT_RUN / BLOCKED:
Evidências de browser / CLI / HTTP / provedor:
Riscos ou desvios justificados:
Como reverter sem afetar agentes:
Próxima tarefa elegível:
```

Evidências podem ficar em `plans/ui_simplification/` ou pasta equivalente aprovada. Nome sugerido: baseline, navigation-map, unified-home-contract, connection-selection-contract, execution-ledger, test-evidence, performance e release-report. Não criar documentação duplicada se o projeto já tiver um local apropriado; apontar com referência inequívoca.

---

# 18. Definição de pronto e decisões que não podem ser reinterpretadas

## 18.1 Gate funcional

A entrega só está completa quando:

- O menu principal apresenta os quatro destinos acordados e Advanced organizado, sem perda de páginas/links.
- A Home tem um acompanhamento principal único; não há lista nova de harnesses paralela à de trabalho.
- Todas as sessões relevantes, inclusive ociosas e iniciadas por agentes, são alcançáveis no escopo autorizado.
- Uma execução abre seu contexto/sessão exatos sem buscar em outra tela; o terminal visual permanece leitura de eventos.
- Perguntas, aprovações, erros e resultados estão disponíveis no básico, inclusive durante fallback da Home.
- O usuário consegue adicionar um segundo harness ao mesmo projeto sem precisar escolher nome técnico de perfil, e consegue retomar qualquer conexão/sessão correta.
- Terminal e Connector preservam daemon, identidade, grants, checkpoints e permissões; o dashboard não se torna obrigatório.
- Migração, concorrência, perda de resposta, scoping, pacote e regressão têm evidência adequada ao que se afirma.

## 18.2 Gate de qualificação

Todas as tarefas obrigatórias estão VERIFIED ou explicitamente bloqueadas com decisão de entrega que não as apresente como concluídas. Testes obrigatórios não são descartados por estética ou pressa. Limitação de ambiente pode bloquear uma campanha real, mas não converte fixture em prova real.

Um único harness real não comprova o requisito do segundo harness. UI web sem teste de CLI não comprova onboarding completo. Shell novo sem sino global não pode substituir o menu antigo. Projeção que continua operator-only não comprova visão de todas as execuções. Métrica de latência não medida não é aceita como “rápido”.

## 18.3 Proibições explícitas de interpretação

Não concluir “basta mover os menus”: a Home e o onboarding fazem parte do mandato.

Não concluir “basta acrescentar uma aba Harnesses”: o usuário pediu evitar nova tela/menu e listas paralelas.

Não concluir “basta esconder com CSS”: evitar carregar/renderizar consultas e coleções redundantes.

Não concluir “Avançado pode conter tudo”: decisões e acompanhamento cotidianos permanecem no básico.

Não concluir “retomar é a sessão mais recente”: usuário escolhe contexto exato; operação incerta tem recuperação própria.

Não concluir “adicionar é substituir”: a conexão anterior deve permanecer intacta.

Não concluir “conexão pronta é trabalho pronto”: serviço, configuração, sessão, turno e entrega continuam diferentes.

Não concluir “simples é sem segurança”: simplificar a apresentação, não os contratos.

## 18.4 Metas de experiência a medir

Quando o host/provedor já está preparado, o caso feliz deve pedir somente escolhas indispensáveis: conexão existente versus nova, harness quando ambíguo e uma revisão clara dos efeitos necessários. Não impor quantidade fixa de cliques que elimine consentimento obrigatório, login faltante ou conflito real.

No cenário simples, abrir uma sessão conhecida deve ser uma ação a partir de sua linha. Múltiplas sessões exigem expansão/seleção explícita e isso não é falha. A pessoa deve reconhecer execução, pendência e entrega em poucos segundos no conjunto de demonstração; registrar tempos reais e linguagem que causou dúvida.

O básico deve levar ao objetivo sem entrar em Advanced. O avançado precisa ser descobrível e manter o mesmo agente/histórico/configuração, não criar uma modalidade isolada do produto.

---

# 19. Prompt de arranque para o Codex

O mesmo conteúdo está em `PROMPT_CODEX_NEXUS_UI_R1.md`. Usar o documento completo como fonte de requisitos; o prompt abaixo não o substitui.

```text
Implemente o plano PLANO_CODEX_NEXUS_UI_SIMPLIFICADA_HOME_ONBOARDING_R1.md,
com o ledger NEXUS_UI_EXECUTION_LEDGER_R1.json. Comece pela PR-00 e avance
por tarefas pequenas e testáveis. A inspeção foi feita na branch
feature/v0.3.4 do OktoLabsAI/okto-nexus, SHA
3d95aad8c1b5d2e6354cd872512586fd7a02aec9. O Connector de referência é
feature/v0.0.12, SHA a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b.
Esses SHAs são baseline de análise, não autorização para retroceder o checkout.

Antes de editar, leia AGENTS/CONTRIBUTING/CI atuais, registre branch/HEAD,
working tree, pins e drift. Há implementação de Home em andamento: preserve-a,
reaproveite os serviços, controllers, testes, alvos e controles já entregues.
Não faça reset/clean destrutivo, force-push, release, deploy ou campanhas pagas
sem autorização específica. Não altere a instalação pessoal do usuário.

REQUISITOS NÃO OPCIONAIS:
1. Quatro destinos principais: Home, Conversations, Graph e Artifacts.
   Advanced é entrada secundária, com grupos e acesso às páginas atuais.
2. Home tem uma única região principal de acompanhamento. Trabalho, harness,
   sessão, pergunta e resultado correlacionados ficam juntos. Não criar menu,
   tela ou lista paralela de Harnesses/Execuções/Sessões.
3. Abrir a linha mostra o contexto/sessão exatos num painel contextual,
   reutilizando o terminal de eventos somente leitura e controles canônicos.
   Incluir sessões sem operação e atividades iniciadas por outros agentes.
4. Perguntas/aprovações/erros/resultados ficam no básico e no sino global,
   inclusive com fallback da Home antiga. Advanced não é controle de acesso.
5. Onboarding obrigatório: retomar conexão existente OU adicionar outro
   harness ao mesmo projeto, sem o usuário precisar inventar --profile.
   Preservar scripts explícitos, IDs, checkpoints, revisões e permissões.
   Implementar no CLI local, no onboarding da UI e no Connector respeitando
   a autoridade de cada superfície. Não deixar isso como follow-up opcional.
6. Retomar conexão, continuar sessão, abrir nova sessão e recuperar envio
   pendente são intenções diferentes. Não usar a sessão mais recente por
   heurística; resultado incerto não autoriza nova execução.
7. Preservar daemon/serviço e ciclo pelo terminal; UI não vira obrigatória.
   Nova conexão não recria o serviço, renova grant ou altera outra conexão.

O layout multi-listas do plano HOME-R1 é substituído por esta composição única,
mas seus invariantes e evidências continuam. Não refaça Core/protocolos ou
Attention/setup/receipt. Não una primeiras páginas de várias fontes em React
para fingir inventário completo: correlação e paginação são escopadas no backend.
Mantenha identidade interna de views e URLs ao trocar rótulos públicos.

Siga PR-00..PR-08 e dependências do ledger. Ao terminar cada tarefa, execute
seus cenários e atualize evidências/limitações. IMPLEMENTED não é VERIFIED;
fixture não é harness real; teste Node não é navegador nem leitor de tela.
Preserve bloqueios de qualificação anteriores aplicáveis. Ao fim de cada etapa,
informe mudanças, testes, regressões, efeitos/migrações, rollback e próximo passo.
Não encerre a entrega apenas com o menu ou com a Home: o requisito obrigatório
de adicionar/retomar múltiplas conexões faz parte do gate final.
```

---

# 20. Fontes e rastreabilidade da inspeção

As fontes abaixo documentam o que foi observado. Requisitos propostos estão separados de comportamentos existentes. Arquivos do repositório são fixados em SHA para tornar a análise reproduzível. O executor deve reler o HEAD atual e registrar divergências.

## Repositório Nexus

- **[S01] Branches e último commit observado.** `feature/v0.3.4`, SHA `3d95aad8c1b5d2e6354cd872512586fd7a02aec9`, mensagem `feat(home): isolate Server attention and preserve scoped source reads`. Fonte: https://github.com/OktoLabsAI/okto-nexus/commit/3d95aad8c1b5d2e6354cd872512586fd7a02aec9
- **[S02] Versão e dependência do Core.** `pyproject.toml`, Nexus 0.3.4 e Core 0.0.14. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/pyproject.toml
- **[S03] Plano anterior de Home fornecido na conversa.** `PLANO_CODEX_NEXUS_HOME_OPERACIONAL_R1.md`, referência original `feature/v0.3.3` / `4ba6fa4...`. Usado para preservar invariantes e explicitar a substituição do layout de listas paralelas; não representa o estado atual do código.
- **[S04] Shell, destinos, guards e ativação da Home.** `frontend/src/App.tsx`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/App.tsx
- **[S05] Composição operacional atual e listas independentes.** `frontend/src/components/home/OperationalHome.tsx`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/components/home/OperationalHome.tsx
- **[S06] Fontes, escopo e correção de Attention Server/remetente-destinatário.** `plans/home_evolution/source-map.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/plans/home_evolution/source-map.md
- **[S07] Modelos da Home e ausência de alvo de sessão autônomo no snapshot.** `frontend/src/homeTypes.ts`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/homeTypes.ts
- **[S08] Validação/resolução de alvos e inspeção contextual.** `frontend/src/homeNavigation.ts` e `frontend/src/components/home/HomeInspection.tsx`. Fontes: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/homeNavigation.ts e https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/components/home/HomeInspection.tsx
- **[S09] Sessão com live tail/histórico e verificação de scope.** `frontend/src/components/SessionTerminalModal.tsx`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/components/SessionTerminalModal.tsx
- **[S10] Terminal de eventos somente leitura e maximização por dialog.** `frontend/src/components/RuntimeTerminal.tsx`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/src/components/RuntimeTerminal.tsx
- **[S11] Resolução de perfil implícito, conflito de seleção e setup por checkpoint.** `src/okto_nexus/adapters/inbound/cli/connect.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/src/okto_nexus/adapters/inbound/cli/connect.py
- **[S12] Conexão local, preset, serviço sob demanda, revisão e login opcional.** `docs/terminal-connect.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/docs/terminal-connect.md
- **[S13] Trabalho pelo terminal, sessão, recuperação de envio e autorização.** `docs/terminal-work.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/docs/terminal-work.md
- **[S16] Ledger de implementação e limites de qualificação da Home.** `LEDGER_CODEX_NEXUS_HOME_OPERACIONAL_R1.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/LEDGER_CODEX_NEXUS_HOME_OPERACIONAL_R1.md
- **[S17] Scripts frontend existentes.** `frontend/package.json`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/3d95aad8c1b5d2e6354cd872512586fd7a02aec9/frontend/package.json

## Connector

- **[S14] Branch de compatibilidade consultada.** `feature/v0.0.12`, SHA `a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b`. Fonte: https://github.com/OktoLabsAI/okto-nexus-connector/tree/a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b
- **[S15] Wizard, retomada, bootstrap remoto, diretórios e decisão do operador.** `docs/connection-configuration.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus-connector/blob/a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b/docs/connection-configuration.md

## Acessibilidade — referências primárias W3C/WAI

- **[W01] Disclosure Pattern:** expansão com estado acessível. https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- **[W02] Disclosure Navigation:** navegação com links não exige role menu. https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
- **[W03] Dialog Modal Pattern:** modalidade, foco inicial/retorno e teclado coerentes. https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- **[W04] Conteúdo autoatualizado e mensagens de estado:** controle visual e avisos que não roubam foco. https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide e https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html

---

**Resultado esperado:** o usuário conecta um harness, adiciona outros quando precisar, volta a qualquer contexto e acompanha o trabalho numa Home simples. Toda a profundidade administrativa continua acessível, sem dominar a navegação cotidiana. O plano descreve como implementar e comprovar essa experiência; não afirma que ela já foi entregue.
