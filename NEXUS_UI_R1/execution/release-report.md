# UI-R1: implementação e qualificação

O plano permanece **IN_PROGRESS**, sem aprovação de release ou ativação padrão.
Navegação, acompanhamento único, painel exato e onboarding múltiplo foram
implementados. A qualificação completa de PR-00..PR-08 exige os cenários do
ledger, inclusive campanha real e avaliação humana; não se encerra com a UI.

## Entrega implementada

| Etapa | Resultado | Evidência principal |
|---|---|---|
| PR-00 | Baseline atual, drift, contratos e fixture determinística; arquivos de entrada preservados | `baseline.json`, contratos e `pr00-fixture-qualification.json` |
| PR-01 | Home, Conversations, Graph, Artifacts; Advanced secundário agrupado; IDs/URLs e sino global preservados | `pr01-shell-qualification.json` |
| PR-02 | Retomar/adicionar/cancelar no CLI, alias gerado, reserva durável, workspace canônico compartilhado e intenções de sessão separadas | `pr02-local-connection-qualification.json`, `pr02-session-intent-qualification.json` |
| PR-03 | Correlação completa e paginação escopada no backend, sessões sem operação, alvos exatos e fontes parciais explícitas | `pr03-entries-qualification.json`, `pr03-session-viewer-qualification.json` |
| PR-04 | Uma região Follow-up, expansão de contexto, filtros, atualização compartilhada e onboarding apenas com inventário vazio comprovado | `pr04-unified-home-qualification.json`, `evidence/pr04-browser/` |
| PR-05 | Um painel contextual com terminal somente leitura, perguntas, resultados, artefatos e controles canônicos vinculados à sessão | `pr05-panel-onboarding-source-qualification.json`, browser humano/CAS |
| PR-06 | Retomar/adicionar na UI e Connector, revisão e Finish canônicos, defaults/permissões existentes preservados, recuperação sem replay | `pr06-catalog-convergence-qualification.json`, `pr06-connector-qualification.json`, `pr06-final-client-qualification.json` |
| PR-07 | Regressões focalizadas, navegador real, medições e proposta isolada de campanha; gates externos continuam abertos | Ledger, `pr03-performance/`, `pr07-native-proposal/` |
| PR-08 | Guias, artefatos identificados por hash, instalação isolada, smoke MCP HTTP e rastreabilidade | `pr08-installed-*.json`, este relatório e ledger |

Nexus usa `feature/v0.3.5`/0.3.5; Connector usa
`feature/v0.0.13`/0.0.13. Core permanece em 0.0.14, sem alteração de código ou
protocolo. Os SHAs fornecidos para análise não foram usados para retroceder os
checkouts. Os detalhes de main, working tree e pins iniciais estão no baseline.

## Evidências e fronteiras

- O ledger é a fonte de status por cenário. Testes parcialmente cobertos mantêm
  NOT_RUN ou BLOCKED; ter arquivos de implementação não os transforma em PASS.
- O corte DXslPEEE/Ds-MK2FR tem 328 testes Node e TypeScript/Vite aprovados.
  Substitui a apresentação CKl/BP1 (316 testes), sem substituir suas evidências
  históricas. O quadro por colunas usa a mesma fila de atualização; mudança de
  revisão invalida todas as páginas e mantém os detalhes na revisão de entrada.
  Node/SSR não são navegador nem leitor de tela.
- A Home teve 19 checks de navegador no corte dfy1, mais oito checks humanos de
  formulário/guard/CAS no corte vmh. Duas abas enviaram decisões reais à API,
  retornaram 202/409 e produziram uma decisão, uma operação `input.provide` e um
  outbox. A aplicação nativa dessa decisão não foi executada.
- O focal posterior de resposta perdida enviou uma decisão real, recebeu202 no
  interceptor e perdeu somente a resposta ao browser. Recuperação por GET e
  reabertura mantiveram a decisão original DISPATCH_PENDING e um único outbox;
  não houve segunda operação ou aplicação nativa. Ver T-PANEL-09.
- O corte BGONN corrige o falso aviso de rascunho ao alternar Auto-scroll no
  terminal somente leitura. Quatro checks no navegador comprovam fechamento
  direto e preservação do guard para um formulário canônico realmente editado.
- A primeira avaliação humana falhou ao retomar uma conexão. O participante
  relatou confusão entre Home clássica/operacional, projeto e objetivo. Foram13
  cliques no primeiro corte e20 no total, incluindo exploração posterior, sem
  POST. A expiração técnica da fixture foi registrada separadamente. A correção
  removeu a alternância da Home básica, destacou Project e nome do projeto e
  mudou a entrada para Connect or resume. Mesma preferência/defaultOFF/guardas,
  IDs e URLs; escolha de apresentação agora em Settings. Três checks técnicos
  de navegador passaram. Isso não transforma a tentativa humana falha em PASS;
  o segundo percurso usa participante já exposto à interface.
- O segundo percurso confirmou Add tecnicamente, mas o participante relatou
  demora, configuração excessiva e dúvida sobre a conclusão. O terceiro usou
  projeto dentro da Home, quatro resumos familiares e confirmação persistente.
  Teve 22 cliques no corte funcional, dois POSTs simulados Test/Finish e 47 cliques
  no log final incluindo exploração posterior. O participante conseguiu avançar,
  mas ainda relatou ruído, dúvida com Open context e ausência de confirmação
  suficientemente clara. Os três percursos estão encerrados e preservados;
  UI-043 continua IN_PROGRESS e T-QUAL-05 FAIL. Não há aprovação humana inferida.
- O usuário pediu substituir Active/Needs you/Results por três colunas sempre
  visíveis, com cards na mesma região. O ajuste está em `BOARD_R2_AMENDMENT.md`.
  O backend aditivo usa a mesma relação autorizada e uma UoW de leitura, faz
  classificação exclusiva e paginação por coluna, com revisão global separada
  da revisão dos detalhes. Nove focais Board passaram no corte final; 17
  regressões relacionadas passaram antes das duas correções finais de resumo
  e atenção órfã. Totais/resumos seguem escopo e retenção, estados desconhecidos
  não viram zero, e atenção resolvida não permanece em Active. Os testes de
  controller cobrem movimentação entre colunas, 409, cursor antigo, 403 tardio,
  pausa/foco e rejeição de duplicatas. Navegador e pacote instalado desse ajuste
  estão em qualificação, sem promover cenários por inferência.
- Os focais ATTN-02/06 comprovaram autoridade humana e fallback clássico no
  navegador, sem aplicação nativa. PANEL-08 passou em HTTP/Core com dois peers
  Python inertes: interrupção exata e replay da mesma operação, irmão preservado,
  cleanup físico comprovado. Isso não equivale a uma interrupção de Codex real.
- O inventário HTTP/SQLite paginado de Todos manteve dois bindings do mesmo
  agente separados, incluindo pergunta bloqueada e resultado do outro contexto.
  Um segundo projeto autorizado acrescentou um trabalho sem multiplicá-lo pelos
  bindings; a filtragem de projeto preservou os totais anteriores.
- A projeção de resultado passou a reunir arquivos distintos de todas as
  operações terminais autorizadas do mesmo handoff/claim/workspace, incluindo
  links históricos e outros executores. Um resultado VERIFYING não é aceito ao
  abrir; leitura não marca visto, não cria ACK nem watermark. O corte anterior
  passou37 regressões; um fence posterior de workspace passou um focal e seis
  relacionados. São cortes separados. O teste novo passou Ruff; o leitor legado
  conserva17 achados idênticos ao HEAD, sem achados novos ou formatação ampla.
- A instrumentação instalada adicional de 1/10/100 agentes manteve55SQL em
  entries/children/sessions, uma UoW somente leitura e zero writes/transcripts.
  Esse corte tem três amostras quentes e apenas dois eventos; não substitui o
  benchmark anterior de100.002 eventos nem aprova SLO. Fixtures persistidas
  também comprovaram sessões técnicas sem atividade produtiva e resultado
  SUCCEEDED separado do handoff aberto/cleanup pendente.
- O onboarding usou HTTP/SQLite reais com Test peer sintético. Codex e Claude
  compartilharam o workspace, com duas identidades distintas e configuração da
  primeira intacta. Respostas perdidas foram recuperadas pelos mesmos IDs.
  Os cortes finais corrigem recusa definitiva, inputs controlados e restauração
  de projeto/host. Esses peers não criam sessões runtime: não são harnesses reais.
- A campanha Python instalada antecedente teve 187 PASS e duas falhas de oráculo
  que misturavam principais de autenticação no cursor. Os dois focais corrigidos
  passaram separadamente. Isso **não** é uma execução única 189/189. Connector
  teve 52 focais instalados aprovados. O relatório de pacote conserva hashes,
  versões, origens de importação e os deltas posteriores.
- O smoke MCP HTTP real usou duas identidades, SDK oficial e 54 ferramentas em
  Server foreground temporário. Mensagens/eventos, handoff, artefato e shared.md
  passaram; parada canônica e saída física foram comprovadas. Não houve modelo.
- Uma faixa posterior de serviço teve 13 PASS e três falhas de fixtures antigas
  de login, em quatro execuções separadas. Processos reais comprovaram
  inicialização/reuso/saída do launcher e restart do Server com grants
  válido/expirado/revogado e peer inerte. As fixtures de login não fornecem o
  receipt atual de supervisor; as falhas UNKNOWN permanecem registradas. Não é
  qualificação de tarefa nativa do Windows, trabalho ativo sobrevivendo ou
  rollback de UI. Ver `evidence/pr07-service/scenario-audit.md`.
- As fixtures do wizard foram depois atualizadas para modelar explicitamente a
  observação do parent na mesma fronteira nativa já simulada. Wizard/supervisor
  tiveram 36 PASS e uma falha do novo oráculo; o focal corrigido passou. O novo
  negativo comprova recusa quando falta a prova do parent, sem enfraquecer o
  guard de produção. O teste instalado de doctor ausente também passou, sem
  criar home, executar provider ou autoiniciar o Server.
- Ruff focal passou. Ruff global falhou com 23.912 erros, incluindo código
  legado, cópias geradas e drivers de evidência. Não há alegação de lint global
  limpo nem classificação automática de todos esses erros como preexistentes.
- A CI remota é independente da validação local. Consultas anteriores retornaram
  runs em fila; ausência de conclusão não significa aprovação.

Cada relatório preserva seu corte e seus antecedentes. Assets posteriores não
mudam retroativamente a qualificação de browser ou os tempos medidos antes deles.

O pacote BXP congelado para a proposta de campanha tem wheel SHA256
`544c48099db0793c66af54a48c70585e620fb0e56e02b145ab1bb38e5e743a64`.
Os 708 payloads não estáticos do módulo são byte a byte iguais ao corte dos22
focais:538 arquivos Python,167 migrações SQL e três outros recursos. A prosa
anterior chamou esse conjunto imprecisamente de708 módulos Python.
Esses payloads são iguais ao corte que passou pelos22 focais
instalados da Home. A comparação com o antecedente de 189 casos isola quatro
arquivos de metadados do inventário e mantém 704 idênticos. Smoke, entrypoints,
Twine e pins do pacote final passaram; nenhuma instalação pessoal foi alterada.
O delta de apresentação BGONN é posterior e foi qualificado separadamente; não
substitui retroativamente esse wheel nem altera a proposta original congelada.
O wheel BGONN `070e10fc…f8d0b31` foi construído, instalado em outro prefix próprio,
validado com Twine e smoke do console;538 Python/708 payloads não estáticos
permaneceram iguais ao BXP. Correções backend posteriores requerem novo corte.

O pacote PR16 `3374b69e…2b35576` inclui a correção do leitor de resultados:
707 dos 708 payloads não estáticos iguais ao BXP e apenas `sqlite/home.py`
diferente. Sete focais instalados, smoke, entrypoints, Twine e origens isoladas
passaram. A instrumentação quente adicional de 100 agentes teve p95 de
655,84 ms (entries) e 646,50 ms (children), ainda acima de 500 ms; três amostras
com dois eventos não substituem o benchmark maior. O pacote PR18
`bfcd3a56…41b116` preserva os 708 payloads não estáticos do PR16 e altera somente
os assets CKl/BP1. Ambos são antecedentes imutáveis do novo quadro, que altera
backend e frontend.

O pacote Board PR21 `7f488a55…0da9769`/sdist `03c76acb…5515280` passou
17 focais instalados, smoke, Twine e console helps em novo prefixo temporário.
Os 716 payloads Nexus, 168 Core e 127 Connector conferem com os wheels. Contra
PR18, são 706 payloads não estáticos iguais, dois `home_entries.py` alterados e
`home_board.py` aditivo. Fontes e fixtures sem drift, imports somente do prefixo
novo e ambientes anteriores preservados. Não é uma campanha de harness ou SLO.

As preferências Seen/Snooze do overview consultam o snapshot Board fresco.
No painel, a tentativa usa as revisões capturadas e o endpoint canônico valida
principal, origem e CAS; conflito ou recusa não causam replay. Não há alegação
de lookup Board fresco para essa preferência no painel pausado. Comandos de
execução e decisões continuam sob os inspectores e autoridades canônicos.

A proposta real foi vinculada ao pacote BXP, teve 21 testes offline e um smoke
de lifecycle real com zero admissões. A revisão independente e a conferência de
1.047 pins passaram. O candidato `3ea51229…fafb88e` foi apresentado ao usuário
para uma autorização específica; o usuário autorizou depois somente Codex.
O template original permanece falso. Os derivados Codex tiveram24/28 testes
offline e foram executados sob consentimentos genuínos vinculados à resposta;
as duas tentativas e seus bloqueios estão preservados, sem campanha concluída.
Nenhuma aprovação de release/default é inferida da autorização da campanha.

## Limites que impedem qualificação completa

Além dos gates abaixo, há cenários completos de navegador, escopo, serviço e
rollback ainda NOT_RUN, mesmo quando partes passaram. Incluem scrollback ao
receber output, maximizar/restaurar, revogação com rascunho/Voltar, recuperação de
decisões em outros contextos e reversão de apresentação com
trabalho admitido. Esses são trabalhos de qualificação executáveis; não são
classificados automaticamente como bloqueios externos. O ledger distingue cada
cenário e mantém a entrega em andamento.

1. O usuário autorizou a campanha UI-R1 somente com Codex. A primeira tentativa
   parou antes do Test por inventário ainda indisponível, com zero efeitos
   comprovados e cleanup DRAINED/saída física. O derivado conservou75mil tokens
   provisionados e limitou a cinco novos slots, dentro do mesmo teto global.
   Após a espera canônica de inventário, o Test real recusou gpt-5.3-codex para
   a conta atual (modelNotFound). Não houve Finish, binding, grant, agente ou
   trabalho útil. Não apareceu relatório de uso: consumo UNKNOWN, nunca zero;
   as duas reservas150mil permanecem e novas admissões estão bloqueadas. Não
   houve fallback/replay. Server e descendentes próprios encerraram: DRAINED,
   launcher0, WindowsJob STOPPED confirmado por consulta RO. Um stop_proof
   durável ausente não foi fabricado. Os oito modelos observados nos eventos
   preservados não substituem nova seleção explícita nem contabilidade válida.
   Claude permanece adiado por limite indisponível; nenhum acesso ou execução
   de Claude ocorreu nesta campanha.
2. Uma máquina remota real com Connector e pastas diferentes não foi qualificada
   por peers locais. Não há declaração de suporte universal de plataforma/harness.
3. UI-043 conserva três percursos documentados, o primeiro sem conclusão e os
   dois posteriores com avanço técnico e clareza insuficiente. Os últimos
   pedidos motivaram colunas, rótulos específicos e indicadores de estado.
   Esses ajustes não receberam novo aceite humano. Não há duração de sucesso
   ou compreensão inferida; a autoridade de decisão da fixture tem prazo
   independente da janela de leitura.
4. Leitor de tela real não foi comprovado. O zoom nativo de 200% foi exercitado
   depois por `chrome.tabs.setZoom/getZoom=2`, em extensão/perfil temporários
   próprios: mesma janela, innerWidth 1424→712 e DPR 1→2, sem overflow geométrico
   da Home e com fechamento do painel alcançável. Capturas CLI recortam o
   viewport físico nesse modo; inspeção visual completa e scrollback ao vivo não
   foram certificados por essa captura. Viewport de 360 px também foi exercitado.
5. A medição de 100 agentes/1.000 atividades/100.002 eventos registrou p95 de
   1.225,94 ms para a leitura inicial, acima da meta proposta de 500 ms; expansão
   teve p95 de 1.031,41 ms. Foram 55 SQLs/uma UoW/zero writes na leitura inicial.
   A projeção é O(N + relações), limitada por orçamento, não O(página).
6. Cenários de scrollback, maximizar/restaurar, revogação com rascunho/Voltar,
   rollback com trabalho vivo e
   lifecycle específico só podem fechar com suas evidências literais. As coberturas
   parciais estão separadas no ledger.

Suspensão, logout/login e reinicialização do Windows foram descartados do escopo
de execução desta sessão pelo usuário. Não foram executados nem declarados PASS.
Os bloqueios anteriores HOME-R1/R3 aplicáveis permanecem; esta implementação não
é uma dispensa desses gates.

## Efeitos, migrações e rollback

Não há migração SQLite nova. Foram adicionados endpoints/metadados de leitura,
projeção de apresentação e sidecar local de intenção de conexão formato 1;
perfis legados continuam formato 1. Novas identidades só nascem no Finish
canônico, com revisão e permissões explícitas. Retomar não testa modelo nem
renova grant. Leitura/abertura não autoriza executar.

Os testes criaram dados, pacotes e processos temporários próprios. Nenhuma
instalação pessoal ou tarefa de login pessoal foi alterada. Na campanha
autorizada, o Codex usou a conta autenticada por seu fluxo nativo; credenciais
não foram lidas manualmente ou copiadas para evidência. O CLI pode manter seus
caches normais, conforme autorizado. O Test foi recusado e seu uso não foi
informado; não se declara consumo zero. Não houve release, deploy ou ativação
padrão.

Rollback de apresentação: voltar à Home clássica preservando sino e controles
básicos. Rollback de código: reverter os commits da feature por commits novos e
reconstruir assets; não resetar dados. Manter aliases, checkpoints, receipts,
sessões e intenções incertas. Usar `--profile` explícito para os atalhos já
confirmados. A reversão não é justificativa para apagar uma intenção desconhecida
ou repetir trabalho. A qualificação de rollback com trabalho vivo permanece gate
próprio, sem confundir este procedimento com teste executado.

## Próximo gate

Concluir as verificações isoladas pendentes, o artefato instalado posterior aos
deltas e a avaliação humana, registrando a conclusão da CI no SHA correspondente.
A campanha permanece bloqueada por modelo recusado e uso desconhecido; não
executar outra admissão por inferência. Qualificar as fronteiras assistivas e
topológicas disponíveis. A aprovação de release/default
continua `false` até os gates serem atendidos e existir autorização específica.
