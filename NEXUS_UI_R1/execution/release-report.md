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
- O frontend completo tem 300 testes Node aprovados no corte BGONNtiX e
  TypeScript/Vite aprovados. Node/SSR não são navegador nem leitor de tela.
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
- O inventário HTTP/SQLite paginado de Todos manteve dois bindings do mesmo
  agente separados, incluindo pergunta bloqueada e resultado do outro contexto.
  Um segundo projeto autorizado acrescentou um trabalho sem multiplicá-lo pelos
  bindings; a filtragem de projeto preservou os totais anteriores.
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

A proposta real foi vinculada a esse pacote, teve 21 testes offline e um smoke
de lifecycle real com zero admissões. A revisão independente e a conferência de
1.047 pins passaram. O candidato `3ea51229…fafb88e` foi apresentado ao usuário
para uma autorização específica; o usuário autorizou depois somente Codex.
O template original permanece falso, com derivado estreito em preparação.
Nenhuma aprovação de release/default é inferida da autorização da campanha.

## Limites que impedem qualificação completa

Além dos gates abaixo, há cenários completos de navegador, escopo, serviço e
rollback ainda NOT_RUN, mesmo quando partes passaram. Incluem scrollback ao
receber output, maximizar/restaurar, revogação com rascunho/Voltar, recuperação de
decisões em outros contextos e reversão de apresentação com
trabalho admitido. Esses são trabalhos de qualificação executáveis; não são
classificados automaticamente como bloqueios externos. O ledger distingue cada
cenário e mantém a entrega em andamento.

1. O usuário autorizou a campanha UI-R1 somente com Codex e permitiu múltiplas
   instâncias. O derivado em preparação usa duas conexões Codex, preserva o teto
   de seis admissões/500mil tokens observados e exclui Claude. A proposta
   original está preservada; nenhuma execução real ocorreu neste corte. Dois
   Codex não qualificam um segundo tipo de harness. Claude foi adiado por falta
   de limite disponível; não se reutiliza autorização histórica para executá-lo.
2. Uma máquina remota real com Connector e pastas diferentes não foi qualificada
   por peers locais. Não há declaração de suporte universal de plataforma/harness.
3. O usuário confirmou um participante disponível nesta máquina para UI-043.
   O ambiente humano está em preparação; navegação automática não mede
   compreensão humana nem fornece tempos ou taxas de sucesso do participante.
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
   interrupção exata, rollback com trabalho vivo e
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

Os testes criaram apenas dados, pacotes e processos temporários próprios.
Nenhuma instalação pessoal ou tarefa de login pessoal foi alterada. Credenciais
reais não foram acessadas e não houve release, deploy ou campanha paga.

Rollback de apresentação: voltar à Home clássica preservando sino e controles
básicos. Rollback de código: reverter os commits da feature por commits novos e
reconstruir assets; não resetar dados. Manter aliases, checkpoints, receipts,
sessões e intenções incertas. Usar `--profile` explícito para os atalhos já
confirmados. A reversão não é justificativa para apagar uma intenção desconhecida
ou repetir trabalho. A qualificação de rollback com trabalho vivo permanece gate
próprio, sem confundir este procedimento com teste executado.

## Próximo gate

Concluir as verificações isoladas pendentes e registrar a conclusão da CI no SHA
correspondente. Executar o derivado Codex autorizado após seu preflight técnico,
sem alterar o ambiente pessoal. Executar a avaliação humana preparada e
qualificações assistivas/topológicas disponíveis. A aprovação de release/default
continua `false` até os gates serem atendidos e existir autorização específica.
