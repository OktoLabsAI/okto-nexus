# Ajuste de composição: card por harness registrado

Na quarta simulação humana, o participante não entendeu a instrução de abrir
uma conexão para acompanhar trabalho e explicitou o modelo esperado:

> Do ponto de vista de usuário, eu deveria ver APENAS harnesses registrados com os status active, Needs you, results. DENTRO do card de cada harness deveriam ter os eventos. Nao entendi a variedade de cards em active.

O pedido substitui a unidade visual do quadro R2: o card passa a representar
uma instância registrada de harness, identificada pela conexão canônica
completa. Trabalho, sessão, pergunta, erro e entrega são eventos/contextos
dentro desse card. Não se exige onboarding ou uma ação de conectar para
acompanhar um harness já exibido. Adicionar outro harness é uma ação separada.

Em seguida, o usuário esclareceu a estrutura das notificações:

> Active devem ser apenas hanesses com opcao de inspecionar a execucao/reconectar. Needs you: deve aparecer com solicitacoes de acao para o usuário, como pedidos de aprovacao ou handoffs. Results: Resultados de harnesses que tenham reportado fim.

E definiu o caso de execução simultânea a uma solicitação:

> se o harness estiver parado esperando o usuário, deve ir para needs you, se nao, somente a acao vai para needs you e o harness continua Active.

As três colunas continuam visíveis na mesma região, com unidades explícitas:

- Active contém somente instâncias registradas de harness, com estado e acesso
  à inspeção da execução ou ao fluxo canônico de reconexão quando aplicável.
- Needs you contém o harness quando há prova de que ele está parado aguardando
  o usuário. Seus pedidos ficam dentro do card. Se o harness segue executando,
  permanece em Active e somente a solicitação aparece em Needs you, identificada
  por sua origem e ação esperada. Uma sessão bloqueada não paralisa outras
  sessões produtivas do mesmo harness. Pedido sem vínculo comprovado continua
  alcançável, sem inventar um harness ou um bloqueio.
- Results contém entregas com término reportado, mesmo quando o harness tem
  outro trabalho em andamento. Reporte, sucesso de execução, limpeza, verificação
  e aceite são estados distintos. Reporte externo não prova sucesso nativo.

Ausência de prova de bloqueio é desconhecida, não prova de paralisação nem de
execução em andamento. Contexto ocioso/configurado continua alcançável com seu
estado explícito, sem alegação de RUNNING. Perguntas e entregas mantêm IDs
estáveis e não são duplicadas em outro tipo de card apenas para notificar.

Abrir, visualizar ou marcar visto não aprova um pedido. Aprovações e handoffs
só oferecem as ações admitidas pela autoridade canônica para o destinatário
atual. Resolução, expiração, revogação ou resposta perdida exigem revalidação;
um resultado incerto não autoriza replay ou nova execução. O sino global usa
as mesmas ocorrências/IDs e não é outra fila independente.

Duas conexões do mesmo agente ou do mesmo Codex não são fundidas por nome,
host, PID ou sessão mais recente. A correlação usa apenas identidades completas
comprovadas. Se um trabalho tem vínculos comprovados com duas instâncias,
ambas podem exibir a referência compartilhada ao mesmo ID lógico; o resumo
deduplica o trabalho. Não se escolhe um vínculo mais recente para esconder o
outro. O alvo e a revisão do detalhe original permanecem preservados.

Atividades externas ou sem vínculo comprovado não viram harnesses fictícios.
Sua cobertura e contagem continuam no básico, com aviso compacto na mesma
região e acesso ao painel contextual paginado, além do sino global existente.
Isso não cria outro destino ou inventário de Harnesses/Execuções/Sessões.
Ausência de correlação ou fonte parcial não significa ausência de atividade.

Agrupamento, classificação, contagens, prévias e paginação são calculados no
backend sobre a relação autorizada completa e na mesma UoW de leitura. A UI
não agrupa primeiras páginas para aparentar um catálogo completo. Os cursores
vinculam principal, Server, projeto/filtros, card/coluna e revisão. Detalhes e
eventos mantêm suas próprias identidades/revisões. Mudança de revisão invalida
as páginas incompatíveis, sem misturar estados ou duplicar cards.

O overview mostra nomes públicos e eventos úteis, preservando IDs e controles
nos detalhes. Cada evento abre seu contexto/sessão exatos. Havendo várias
sessões sem seleção inequívoca, o usuário escolhe explicitamente no painel.
As ações canônicas de pergunta, aprovação, continuação, interrupção e recuperação
continuam sob suas autoridades atuais; observar ou abrir não inicia execução.

Os endpoints anteriores, URLs, preferência e defaultOFF permanecem. Core,
protocolos, Attention, setup e receipts não são refeitos. Não há nova campanha
paga, instalação pessoal alterada, release ou deploy. O plano e ledger de
entrada mantêm seus SHAs/IDs/especificações; execução e limitações registram
este ajuste. As evidências R2 continuam como cortes anteriores, sem certificação
retroativa do R3. A quarta tentativa humana é incompleta por incompatibilidade
de conceito, sem PASS inferido ou descarte das observações anteriores.
