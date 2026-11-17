# Home R3: harnesses, solicitações e entregas

A implementação atual substitui os cards variados de trabalho/sessão da Home
por uma composição orientada ao usuário. Active mostra harnesses registrados.
Needs you mostra o harness quando há bloqueio confirmado aguardando o usuário;
se ele continua executando, mostra somente o pedido, identificado pela origem.
Results mostra entregas com término reportado, independentemente de outra
execução do mesmo harness. Reporte não equivale a sucesso nativo ou aceite.

As regras e a confirmação do usuário estão em `HARNESS_CARD_R3_AMENDMENT.md` e
`HOME_ACTION_NOTIFICATIONS_R3.md`. A quarta simulação foi encerrada como
incompleta por incompatibilidade de conceito; isso não foi convertido em PASS.

## Mudanças

- Inventário completo de conexões registradas e provas de associação são
  reutilizados na mesma UoW de leitura. Duas conexões do mesmo agente/Codex
  continuam distintas por identidade completa. Referências compartilhadas
  preservam o ID lógico, o grupo original e o alvo exato.
- Metadados seguros de operação/pedido permitem distinguir bloqueio confirmado,
  execução paralela, confirmação pendente e desconhecido. Não se lê prompt,
  segredo ou transcript no carregamento inicial. A pergunta de A não bloqueia
  B nem aparece como pergunta de B na prévia do card.
- As novas rotas `home/harness-board`, coluna, contexto do card e sem vínculo
  agregam/contam antes de paginar. Os endpoints anteriores permanecem. A revisão
  global inclui os metadados ordenados; `entry_revision` continua reproduzível
  pelos detalhes e cursores anteriores.
- O overview tem nomes públicos, eventos curtos e ações específicas. A inspeção
  preserva a sessão exata; ambiguidades exigem escolha. Foram retirados os
  inputs de IDs técnicos e os controles vistos/adiados do overview compacto;
  estes últimos continuam no painel canônico e no sino existente.
- Add harness é separado da observação dos cards. O modo Add respeita catálogo
  e diretório autorizados, conserva checkpoints incertos e não renova grants.
  Um Server sem projetos oferece uma intenção explícita de criar o primeiro;
  nenhuma identidade/projeto nasce antes de Finish. O chooser antigo permanece.
- Pedidos/relatos sem vínculo comprovado não invalidam a Home nem inventam um
  harness. Eles mantêm origem desconhecida e abrem a ocorrência canônica exata.

## Validação deste corte

O frontend final `Bljabqt3`/`Ds-MK2FR` passou **350/350 testes Node** e
TypeScript/Vite. São 224 pins de frontend/assets no relatório
`pr26c-harness-frontend-complete/qualification.json`. Os cortes de 345 e 347
testes são antecedentes separados: primeiro projeto e origem sem vínculo
receberam negativos específicos antes do corte final.

O backend está congelado no `pr22-harness-board-backend.json`. Há cortes finais
de contrato e SQLite/HTTP, incluindo pergunta bloqueante, snooze sem falsa
retomada, execução paralela, outra conexão, identidade de detalhe e revisão
ordenada. Os erros de enum/oráculo/fixture intermediários estão preservados;
não são uma única execução verde inventada.

A medição comparativa de 1/10/100 registros usa uma query batch adicional:
58 SQLs contra 57 no Board anterior da mesma fixture, uma UoW e zero writes,
sem journal/transcript. A amostra única de 100 registros levou cerca de 715 ms;
não é p95, não qualifica SLO e não dispensa a meta de 500 ms nem o benchmark
anterior maior. O número antigo de 55 SQLs pertence a outro corte/instrumentação.

O pacote instalado final PR27 passou **42/42 casos**, incluindo todos os 25
casos R3 de contrato/SQLite e 17 regressões do Board anterior, aplicação,
relações e arquivos por workspace. Wheel `0ecc87a6…5c2b490`, sdist
`b9b8f1da…9a6fbca`; smoke, console helps e Twine aprovados. Os 718 payloads
Nexus conferem com fonte/wheel, os 168 Core e 127 Connector com os wheels
exatos. Prefixos anteriores e os 1.035 pins BXP permanecem intactos.

O browser técnico PR25 comprovou **14 verificações funcionais** em duas fases:
harness bloqueado em Needs you e, após outra execução RUNNING comprovada,
harness em Active com pergunta independente em Needs you e entrega em Results.
Inclui handoff público verificável pelo operador atual, alvo exato, origens
sem vínculo, inspeção somente leitura, paginação contextual, 360 px, Add apenas
com GETs e reconexão indisponível explícita. Zero POST ou provedor.

Foram preservados os antecedentes de oráculo/expiração e uma falha de guarda
de console da origem anterior. As verificações funcionais passaram; isso não
é uma alegação de que todo comando intermediário foi verde. A fase final
comprovou snapshot pareado HTTP/DOM ainda antes do prazo nativo original,
sem nova publicação ou extensão de TTL. Navegador, Chrome, Node, fixture e
porta próprios encerraram e sua ausência física foi comprovada. Root revisou
visualmente as duas fases e as evidências têm 57 pins conferidos.
Nenhuma aprovação humana, leitor de tela real, harness real ou campanha paga é
inferida de Node, metadados sintéticos ou fixture local.

## Limitações e gates preservados

Reconexão individual não é uma capacidade atual da UI/HTTP. Abrir contexto é
leitura. O reconnect do Connector reinicia o daemon inteiro, portanto o card
não o executa como ação de um único harness; a indisponibilidade é explícita.
Não foi adicionado `runtime.start`, Test, nova sessão, grant ou comando presumido
para imitar reconexão.

A prova de bloqueio exige metadados correntes e completos; métodos sem prova
de bloqueio permanecem desconhecidos. Uma decisão recebida pelo Nexus não prova
aplicação nativa ou retomada. Visto/snooze não alteram execução. Pedidos humanos
e handoffs só oferecem as ações canônicas do destinatário atual.

O aceite humano da composição R3 continua pendente. O usuário informou que
ficará indisponível por algumas horas; nenhuma nova rodada manual será aberta
neste período. UI-043/T-QUAL-05 e os bloqueios globais anteriores permanecem,
inclusive campanha real com uso desconhecido, topologia remota, AT, desempenho
e cenários ainda não qualificados. O plano UI-R1 não é declarado integralmente
VERIFIED por esta implementação.

## Efeitos e reversão

Sem migração SQLite, alteração de Core/protocolo/Attention/setup/receipt ou
instalação pessoal. Os testes usam homes, perfis e processos próprios e peers
inertes. Não houve release, deploy ou ativação padrão. O sino, os controles e o
fallback existente continuam acessíveis.

Reversão de apresentação pela preferência existente ou de código por novos
commits/rebuild, preservando dados, aliases, checkpoints, sessões e pedidos
incertos. Nunca limpar dados ou repetir um envio como mecanismo de reversão.

## Sequência solicitada

A implementação e a qualificação automatizada desta composição estão concluídas,
com cleanup comprovado. Código em `ae1809f8`; a evidência final e o ledger serão
enviados no fechamento deste milestone, antes de iniciar o pacote Quick Connect
indicado pelo usuário. Até este corte o pacote novo não foi inspecionado ou
iniciado. A indisponibilidade humana não é tratada como aceite; a qualificação
global UI-R1 continua explicitamente separada, sem release/default aprovados.
