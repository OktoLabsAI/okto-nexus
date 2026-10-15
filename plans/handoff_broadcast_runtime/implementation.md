# Implementação do plano de handoff broadcast

Documento de acompanhamento. O plano normativo é
`PLANO_HANDOFF_BROADCAST_RUNTIME_MCP_v0.3.0.md`; nenhum requisito foi removido.
O ledger contém os 40 cenários de aceite e os 10 invariantes, com evidências
por etapa. Itens ainda sem evidência continuam pendentes.

## Contratos e fronteiras

- `RuntimeAffinity` é uma regra pura do domínio Nexus. A seleção de sessões e
  a futura avaliação contextual usam a mesma função de contexto. A origem
  vazia é explícita; a função não transforma um ID declarado em prova de sessão.
- `RuntimeCapacity` é uma porta pública do Core. Os DTOs imutáveis de
  `capacity.py` não incluem payload, handoff, remetente, credenciais ou caminhos.
  O Nexus calcula a afinidade; o Core recebe somente seu digest opaco.
- A tentativa inclui escopo, revisões, geração da conexão, geração do owner e
  boot do owner de capacidade. Esse boot identifica o relógio da instalação;
  o boot independente da lease R4 de cada sessão é validado pelo próprio Core.
  Repetir a tentativa não altera esse vínculo nem renova seu prazo.
- A reserva de abertura cobre também o primeiro turno. Seu consumo vincula os
  IDs e hashes da abertura e do turno canônicos; terminar a abertura não pode
  deixar uma mensagem concorrente tomar o primeiro turno.
- `nexus-execution-capacity-v1` é uma extensão de controle independente.
  A lista extensível `control_capabilities` do hello/welcome R4 é o ponto de
  negociação. O codec R4 e seus schemas/manifestos imutáveis permanecem intactos.
  Os novos frames somente poderão circular depois da negociação explícita.
  Nenhum host anuncia esse suporte enquanto H2/H3 não estiverem completos.
- `capacity.consume` vincula a reserva antes dos `operation.submit` normais;
  não cria outro intent produtivo. Consultas e liberação podem referenciar a
  tentativa antiga após reconexão, mas aquisição/consumo recusam geração antiga.
  Os hashes consumidos são canônicos R4; o vínculo existente produzido por
  `prepare_r4_receipt_binding` associa esses hashes à semântica local preparada,
  incluindo o epoch e os fingerprints da abertura, antes do efeito.
  A autenticação do link e a autoridade corrente continuam sendo verificadas
  pelos hosts; possuir um ticket não concede autoridade de execução.
- Prazos transmitidos são durações/observações. Somente o host impõe seu prazo
  local; nenhuma comparação de relógios monotônicos entre máquinas é válida.

## Pool Nexus

`ResourcePool.admit(immediate_only=True)` recusa sem criar chamada, resultado ou
posição em fila quando não existe recurso imediato. Uma instância warm compatível
é reivindicada sem novo slot. Uma abertura fria ganha um slot STARTING associado
à chamada e prazo de admissão limitado a 60 segundos. STARTING/CLOSING continuam
ocupando capacidade, inclusive com `max_parallel=0`. A fila de consumidores
anteriores tem precedência. A modalidade antiga permanece o padrão.

Essa modalidade ainda precisa ser ligada à transação canônica do vencedor,
depois da reserva técnica. Por si só, ela **não implementa auto-claim**.

## Reserva física e gate de turno no Core

O adaptador `SQLiteOwnedSlotLedger` agora implementa a porta adicional
`CapacitySlotLedger`. Tentativas, ocupação de turno e slots físicos são alterados
na mesma transação SQLite; a abertura reservada transfere o slot existente ao
operation ID, sem incrementar um contador paralelo. A transferência não libera
a reserva do primeiro turno.

A admissão normal de turno, quando o gate está habilitado, consulta esse mesmo
ledger antes de admitir a operação no journal. A abertura também adquire o slot
antes do claim da identidade da sessão no journal: uma abertura concorrente
recusada não pode deixar uma identidade que impeça a abertura do vencedor.
O retorno do transporte mantém o turno ocupado. Somente um terminal correlacionado,
recusa comprovadamente anterior ao efeito ou contenção confirmada libera o recurso.

Retries preservam tentativa, prazo e consumo. A expiração é paginada e restrita
ao boot que gerou o prazo monotônico. Reservas consumidas e liberações pendentes
continuam ocupadas após timeout/reinício. Outro boot pode consultar a tentativa,
mas não reinterpretar seu prazo como capacidade livre.

`capacity_enabled` é um gate de integração do Core, ainda desligado nos hosts.
Ele requer a porta durável; não equivale ao opt-in de automação por agente.
A fachada pública `ExecutionCapacity` já é composta por ambos os hosts sobre
o ledger compartilhado, sem criar harness para reservar uma abertura. O Core
por sessão publica prontidão contextual pela API `capacity_readiness` e valida
o escopo e a lease instalada. Probes lentos têm orçamento de observação e tarefas
retidas/coalescidas; um callback que ignora cancelamento não bloqueia o chamador
nem provoca criação ilimitada de retries.

A implementação concreta da autoridade de cada owner, o canal de controle e a
reconciliação dos intervalos entre commits ainda precisam ser conectados. Em
especial, os scans antigos de recursos devem reconhecer reservas sem processo
antes da ativação. Nenhum contrato novo está sendo anunciado em produção.

O bundle `contracts/capacity/v1` inclui schema fechado, manifesto com hashes e
14 fixtures válidas/10 inválidas. O codec verifica o bundle e as relações entre
os campos. Um smoke sobre o wheel extraído confirmou esses recursos, sem
substituir a campanha de instalação e execução conjunta requerida em H6.

## Próximas integrações obrigatórias

1. Conectar a recuperação das janelas entre o ledger e o journal; finalizar os
   testes de falha e contenção sobre o gate e a transferência já implementados.
2. Conectar autoridade e controle nos owners embedded/Connector: negociação,
   journal de tentativas, observação por mudança, fencing na reconexão e
   preservação da fila normal durante contenção transitória de capacidade.
3. Origem autenticada do criador persistida em handoffs/aprovações, principal
   interno de automação limitado por política/grant e composição do claim na
   mesma UoW da reserva lógica e admissão imediata.
4. Agenda durável, classificação estrutural de avisos broadcast, migração,
   desfechos/compensação, UI e todos os cenários T01–T40.
5. Reconstruir lockfile e wheels; testar instalações usando exatamente o mesmo
   Core 0.0.11 nos dois consumidores. Executar a campanha em host independente.

Versões de trabalho: Nexus 0.3.0, Core 0.0.11, Connector 0.0.9.
O usuário autorizou commit e push do estado atual nas branches de desenvolvimento.
A implementação permanece em andamento; merge, tags e publicação não fazem parte
dessa autorização.
O usuário autorizou um novo checkpoint de commit e push das alterações atuais
nos três repositórios. As etapas e validações pendentes continuam no ledger.
Esse checkpoint foi enviado. O usuário autorizou novamente commit e push
do estado atual do canal de capacidade nas branches de desenvolvimento.

## Controle de capacidade sobre o canal existente

O roteador compartilhado exige negociação explícita da revisão de capacidade e
mantém intacto o codec R4. No Connector, o mesmo owner/leitor R4 admite pedidos
de capacidade em tarefas limitadas, com orçamento separado para consulta e
liberação. A fila de respostas também é limitada; cancelamentos, heartbeats e
outros comandos não aguardam uma consulta lenta. Fechar o socket não abandona
uma mutação já admitida.

O adaptador de saída do Nexus correlaciona cada resultado à conexão e ao hash
da tentativa original. Timeout, falha de armazenamento e revogação após envio
preservam a necessidade de reconciliação. O próximo owner consulta a tentativa
original; não infere ausência da reserva nem renova seu prazo.

A negociação está disponível como integração explícita, ainda não anunciada
pelos owners de produção. Faltam a composição da autoridade real, registro no
link autenticado do Server, publicação por mudança e recuperação dos recursos
antes da ativação. Os testes atuais do canal não substituem a campanha remota.

Os owners de recuperação local e remoto agora cancelam, antes do scan legado,
reservas `HELD` de gerações de conexão estritamente anteriores. O ledger prova
atomicamente a ausência de consumo e transferência; essa operação não depende
do relógio do boot anterior. Consultas paginadas preservam o escopo e o limite
superior da leitura. Reservas consumidas ou incertas não são liberadas por esse
procedimento e ainda exigem a integração das provas de ciclo de vida.

## Checkpoint de autoridade e transporte

Os owners agora compõem autoridade real de escopo, identidade, consentimento,
inventário e lease. O Nexus inclui o registro de disponibilidade e o roteamento
de capacidade no WebSocket autenticado, ainda desabilitados por padrão.
A publicação de mudanças, a validação ponta a ponta desse caminho habilitado
e a integração das operações produtivas continuam pendentes.

Validação deste checkpoint com o Core local 0.0.11: Core 51, Connector 144
e Nexus 17 testes passaram (212 no total). Os relatórios estão em
`build/capacity-checkpoint.xml` de Core/Connector e
`build/handoff-broadcast/capacity-checkpoint.xml` do Nexus.
A implementação continua em andamento; este envio não é merge ou release.

## Publicação limitada de capacidade

O ledger do Core expõe um cursor durável de mudanças, atualizado também por
aberturas e liberações comuns. `CapacityChangePublisher` mantém um produtor
por host, publica páginas com prioridade para observações mais antigas e renova
a validade periodicamente. Observação lenta não cria tarefas por agente nem
bloqueia o despacho. Nenhum probe de provider ou payload privado é necessário.

Os owners embedded e Connector compõem esse publicador sobre seus ciclos de
manutenção. O Connector usa o writer e as lanes autenticadas existentes; o
embedded usa a mesma fachada de aplicação. O aviso `STALE_OBSERVATION` pede
reavaliação contextual e não afirma que todas as sessões estão ociosas.
A perda do owner invalida a rota; uma resposta tardia de mutação exige consulta
da tentativa original. O fechamento impede registro tardio pelo produtor retido.

Passaram 205 testes focados: Core 34 + 27, Connector 48 + 67 e Nexus 10 + 18 + 1,
nos relatórios de publicação/regressão e corrida de encerramento registrados no
ledger. O teste do WebSocket utiliza autenticação e ledger reais com um host
sintético no mesmo processo; não substitui os testes em processos independentes
nem a campanha remota.

A ativação continua desligada até a integração produtiva e a preservação da
fila normal. H4, H5 e H6 seguem pendentes. Este avanço permanece local, sem novo
commit ou push depois do checkpoint autorizado.

## Vínculo da reserva com o despacho produtivo

`ExecutionCapacity.bind_admitted_capacity_operation` encontra a tentativa pela
operação canônica e reaproveita a associação R4/Core que cada host já persiste
antes do efeito. O Connector e o embedded chamam essa porta em aberturas e
turnos; trabalho comum sem reserva conserva seu caminho. O ledger recusa
atribuir uma operação a duas reservas, inclusive colisões entre abertura e turno.

A associação histórica permite recuperar um receipt existente após liberar a
reserva, sem executar novamente. Um ID reservado não pode reaparecer como
trabalho comum de outra sessão. Abertura e primeiro turno no daemon remoto e
próximo turno no embedded foram exercitados com o Core real e peers sintéticos.
Os relatórios de binding registram 36 testes do Core, 55 do Connector e 11 do
Nexus nos conjuntos de follow-up.

A fila normal continua sendo gate de ativação: esperar capacidade segurando o
lock da sessão ou os workers globais bloquearia controles, renovação ou outros
agentes. O fluxo deve reter a identidade/preparação da operação e aguardar fora
desses gates. Na transação canônica do Server, trabalho normal que chegou antes
do claim precisa impedir a disputa ou continuar protegido por sua ordem; após
o claim, a reserva lógica deve impedir que ele ocupe o caminho do vencedor.
Essa integração, as janelas de crash e H4/H5/H6 permanecem pendentes.

## Checkpoint de publicação e controle de espera

Novo commit e push autorizados explicitamente pelo usuário. Inclui os avanços
de publicação e vínculo de reservas, além da implementação ainda parcial do
contrato capacity-v2, recusa tipada antes de efeitos, observador compartilhado
e retomada embedded. O contrato v1 permanece intacto. A validação detectou
hashes antigos nos exemplos v2; foram recalculados com o manifesto correspondente.

Passaram 83 testes focados: Core 31, Connector 32 e Nexus 20. Relatórios:
`build/capacity-push-checkpoint.xml` nos dois componentes e
`build/handoff-broadcast/capacity-push-checkpoint.xml` no Nexus.

A espera ainda requer integração do retry produtivo no Connector, testes
dedicados de deferral/flow e shutdown, e ajuste/validação do limite de 24
esperas para preservar créditos de progresso sob saturação. Os testes deste
checkpoint não qualificam esse caminho ponta a ponta. H4/H5/H6 continuam
pendentes e a ativação produtiva permanece desligada. Nenhuma alteração foi
aplicada à instalação em execução; este envio não é merge ou release.

## Espera produtiva sem ocupar workers

O Connector retém o produtor e a mesma operação durante a recusa transitória
do Core, mas adquire o worker somente para cada tentativa. A espera ocorre fora
do gate de renovação; a abertura conserva preparação, stream e lease inicial.
Um observador compartilhado acompanha a revisão do ledger e faz revalidação
periódica. O encerramento publica uma recusa vinculada comprovadamente sem
efeito apenas quando ainda retém a recusa anterior do Core.

O aviso negociado WAITING/RUNNING não cria receipt nem devolve o crédito de
transporte. No Server, foram corrigidos o bloqueio prematuro em 24 esperas e
a preservação do limite conjunto de 32 itens/bytes. Foram testados escopo,
sequência repetida/divergente, troca de owner e o WebSocket autenticado.

Evidências desta etapa: Core 8 testes; Connector 48 regressões, 1 teste do
transporte e 1 abertura bloqueada com renovação real; Nexus 17 + 14 casos
aprovados nos conjuntos iniciais, 7 no follow-up das fixtures e 1 no WebSocket.
As três falhas iniciais do Nexus eram fixtures incompletas ou que usavam a
geração atual como se fosse antiga; os casos afetados passaram após correção.
Os relatórios e limites de cobertura estão registrados no ledger.

O claim automático ainda não está habilitado. A reserva lógica do Server deve
proteger o vencedor e a ordem anterior da fila, inclusive afinidades diferentes
do mesmo agente. Essa composição, as janelas de crash, H4/H5/H6 e a campanha
remota independente permanecem pendentes. Tudo desta etapa permanece local.

## Origem do criador e checkpoint autorizado

A origem autenticada do criador agora acompanha o handoff e a mensagem de
execução na mesma transação do claim. Sessões runtime usam o principal corrente;
sessões MCP fornecem prova verificada. IDs informativos e dados históricos
continuam no contexto padrão. Aprovações conservam a origem sem armazenar
credenciais e revalidam a autorização no replay.

Validações concluídas: 14 testes de origem, 15 regressões de workspace/mensagens,
74 regressões de handoffs/epochs, dois casos de afinidade/rollback, três checks
de arquitetura e um teste de permissão após ajuste da fixture. Connector: 80
testes de lançamento MCP e boundaries. As falhas iniciais das fixtures e seus
follow-ups estão registrados no ledger.

O usuário autorizou commit e push de todas as alterações atuais nos três
repositórios. H4 permanece em andamento: principal de automação, reserva lógica
com claim/admissão e scheduler ainda faltam, assim como as etapas posteriores.
Este checkpoint não altera a instalação em execução nem constitui release.

## Composição transacional e autorização da automação

`handoff_claim` e `claim_managed_in_transaction` usam o mesmo núcleo transacional:
permissões, audiência, dependências, CAS, epoch, grant, origem e admissão continuam
juntos. A entrada interna aceita a UoW do chamador e não faz commit nem wake.
Isso permite compor a reserva lógica sem transação aninhada. O chamador deve
desfazer a transação em caso de recusa e só acordar o dispatcher após commit.

A admissão `immediate_only` chega ao pool pelo caminho canônico existente.
Pool cheio recusa sem persistir chamada, outcome, posição na fila ou claim;
abertura fria com vaga recebe slot próprio e deadline limitado. Pedido explícito
continua podendo enfileirar. Retorno vazio da admissão não é sucesso imediato.
Essa integração não substitui a reserva técnica do host nem sua futura
vinculação à identidade exata da sessão/operação.

A migração 130 acrescenta `broadcast_handoff_auto_claim`, desligado por padrão,
com herança global e override por agente. A opção não deriva de `conversation`.
Seu epoch independente impede reativar tentativas antigas após desligar/religar,
sem revogar sessões comuns. Edições antigas que omitem o campo o preservam.

O principal interno de automação vincula agente, workspace, endpoint, handoff,
tentativa, grant e revisões. Ele usa as verificações existentes de grants e
permissões, sem chave fictícia ou identidade de operador. A prova persistida não
autentica HTTP/MCP; só restaura a autoridade do mesmo trabalho gerenciado, com
revalidação antes do efeito. Criador, executor e emissor do grant ficam distintos.

Os relatórios de transação, política, principal e regressões estão no ledger.
A integração ainda não ativa aquisições automáticas: faltam vínculo durável das
reservas, proteção FIFO/afinidade, scheduler, bypass estrutural das notificações
e as etapas posteriores. Alterações locais após o checkpoint autorizado;
nenhuma modificação na instalação em execução.

## Vínculo da reserva à admissão canônica

`CapacityAdmissionService` consome uma reserva por uma porta de capacidade,
fora da UoW. O adaptador SQLite implementa a porta de persistência e a migração
131 conserva pedido, reserva, identidades/hashes das operações e estado de
transferência. Esses registros nascem na mesma transação do claim, da mensagem,
do consumo do grant e da admissão. Eles não estabelecem outra posse do handoff.

A abertura fria conserva o ID de sessão proposto antes da reserva, usando um
parâmetro interno que não faz parte da gramática HTTP. O resolvedor inclui essa
seleção em sua identidade imutável; a admissão confere todas as dimensões do
escopo. Na modalidade warm, a sessão selecionada deve ser exatamente a reservada.

Antes do claim, o adaptador verifica a afinidade original e recusa trabalho
anterior admitido ou aguardando reconciliação. O pool continua responsável pela
ordem e contagem one-shot. Após commit, o dispatcher bloqueia efeitos até a
transferência confirmada; a reserva protege abertura e primeiro turno contra
turnos comuns posteriores. Comandos de controle continuam disponíveis.
O isolamento dos produtores agora é por sessão, permitindo progresso de outras
afinidades do mesmo agente. O terminal nativo libera a ordem física sem concluir
automaticamente o handoff.

Testes com Core real e peers sintéticos cobrem abertura fria, resposta de consumo
perdida, repetição das mesmas operações, rollback, prioridade anterior, controle
durante espera e warm sem dupla contagem física. Resultados e correções de fixtures
estão no ledger. Ainda faltam o journal antes da reserva, scheduler e compensação
de falhas/expiração: esta composição não está ativada como aquisição automática.

## Tentativa durável antes da reserva

O checkpoint autorizado `971e540` publicou a composição anterior na branch
`feature/v0.3.0`. Os avanços descritos a seguir permanecem locais.

A migração 132 registra o principal de automação, a geração do handoff, o pedido
técnico completo e a intenção de reservar antes da chamada ao host. Uma restrição
parcial permite somente uma tentativa ativa por agente/handoff, mesmo que outro
worker escolha outro binding ou outra sessão. As identidades e o escopo original
não podem ser substituídos em um retry.

O serviço de aplicação depende de uma porta de persistência e da porta técnica
de capacidade. O adaptador SQLite mantém as transições; a composição injeta o
mesmo núcleo de autorização e claim já utilizado pelos demais consumidores.
Nenhuma chamada ao host ocorre dentro da transação do Server.

Uma resposta de reserva perdida é recuperada primeiro por consulta ao pedido
original. O claim grava sua operação no journal na mesma UoW que altera o
handoff, consome o grant e admite a execução. Se o commit ocorreu mas a resposta
foi perdida, uma nova leitura conserva a operação vencedora e impede que ela
seja tratada como uma reserva perdedora. Falhas antes do commit deixam uma
obrigação durável de liberação. O consumo produtivo continua usando
`CapacityAdmissionService` e os IDs já admitidos.

Falha de pré-avaliação é diferente de uma reserva possivelmente enviada:
`reserve_started` é persistido antes do primeiro envio possível. Uma tentativa
nunca enviada pode ser cancelada sem RPC de liberação. Depois desse marco,
timeout, cancelamento ou consulta sem resultado conservam a identidade e a
obrigação de recuperação. Apenas uma resposta terminal comprovadamente sem
consumo permite retirar a tentativa. Respostas antigas não reativam uma reserva
já encerrada, e a intenção de liberar sobrevive a erros e respostas atrasadas.

Testes com SQLite e Core reais, usando peers nativos sintéticos, cobrem perda de
respostas de reserva/claim/liberação, cancelamento, concorrência, MCP vencedor,
rollback e tentativa atrasada após consulta vazia. Os resultados estão no ledger.
Reinstanciar o serviço nesses testes exercita recuperação a partir da persistência;
isso não substitui a campanha de reinício de processos e hosts independentes.

Uma consulta vazia não impede que um pedido atrasado crie a reserva depois dela.
Sem uma confirmação durável do host que impeça esse pedido, o serviço mantém
`NEEDS_RECONCILIATION`. A proteção descrita abaixo implementa essa confirmação.
O scheduler limitado, a descoberta dos candidatos e a compensação após consumo
continuam pendentes. A aquisição automática permanece desligada.

## Cancelamento anterior à chegada da reserva

O Core fornece `capacity_reservation_id(request)`, identidade proposta derivada
do pedido imutável completo. A liberação de um pedido ainda ausente, usando essa
identidade, grava um registro `RELEASED` sem consumo na mesma transação e no mesmo
journal consultado pela reserva. Assim, uma requisição atrasada somente encontra
o registro terminal, sem recriar capacidade. O formato das mensagens e os bundles
de contrato existentes não foram alterados.

Registros anteriores continuam usando sua identidade persistida, inclusive IDs
opacos das versões anteriores. Cancelar uma tentativa ausente não altera um
processo ou turno de outra tentativa. Se o consumo venceu a corrida, a liberação
permanece pendente de prova de encerramento. A autorização histórica para consulta
e liberação usa o owner autenticado atual, inclusive após revogar a seleção ou
política do agente; ela não concede execução nativa.

O Server solicita essa confirmação somente quando nunca observou uma reserva
para a tentativa. Se um registro já conhecido desaparecer, mantém a incerteza.
O mesmo vale para hosts que recusam o novo comportamento de cancelamento: uma
recusa não permite criar outra candidatura. Com confirmação persistida, uma nova
tentativa pode prosseguir mesmo enquanto o pedido anterior ainda está em trânsito.

Foram exercitados o ledger compartilhado entre processos distintos, reinício do
objeto de armazenamento, concorrência com consumo, IDs históricos, autoridade
revogada e o leitor real do Connector com reserva atrasada. O teste de processos
distintos cobre o ledger do Core; não qualifica sozinho o canal completo nem o
host remoto independente exigidos por T39/T40. Resultados estão no ledger.

## Agenda durável e processamento limitado

A migração 133 cria um índice por handoff e geração, com prazo de nova tentativa,
motivo, cursor dos candidatos e token temporário de processamento. Esse token
limita a repetição de varreduras; não autoriza execução nem substitui o claim.
Um worker antigo não pode sobrescrever o cursor ou o resultado de outro que
retomou a agenda após a expiração do token.

`HandoffRuntimeScheduler` conserva um único planejador e uma quantidade limitada
de processadores em andamento. Os acessos síncronos ao banco ficam fora do loop
de eventos. Um processador lento ocupa sua própria vaga; outros handoffs continuam
progredindo. Encerrar a espera pelo shutdown não descarta o produtor nem libera
capacidade com base no tempo decorrido.

Notificações repetidas são reunidas em um sinal compartilhado. Uma geração
persistida de notificação permite reavaliar trabalho que estava em backoff, sem
criar tarefas por agente ou atualizar toda a agenda a cada evento. Notificações
específicas recebidas durante o processamento também não são perdidas no commit
do resultado. O backoff considera o motivo e sobrevive à reconstrução do serviço.

A varredura de recuperação usa cursores duráveis e páginas limitadas, com índices
para broadcasts abertos e tentativas ativas. Handoffs concluídos e direcionados
não atrasam a descoberta de trabalho elegível. Tentativas ainda não consumidas
voltam à agenda mesmo se o handoff já foi adquirido. O reset preserva o registro
inicial do scanner e zera seus cursores, permitindo descobrir trabalho novo.

O processador recebe uma página limitada de tentativas por uma porta de descoberta
e as conduz pelo journal, claim e consumo existentes. Perder a resposta de um
commit não cria outra operação; a recuperação lê a identidade persistida. A
listagem pública e a futura descoberta paginada compartilham o método
`filter_available_handoffs`, que preserva visibilidade, alvo, comunicação e
dependências. O consumo continua sem concluir automaticamente o handoff.

Testes de integração retomaram candidaturas já persistidas antes e depois do
claim, incluindo perda da resposta de consumo, com SQLite e Core reais e peers
nativos sintéticos. A composição usa por padrão a descoberta descrita abaixo e
permite substituir sua porta em testes. O vínculo dos eventos produtivos,
a classificação estrutural dos avisos e a recuperação após consumo continuam
pendentes. Não houve ativação automática nem alteração da instalação.

## Identidade da instância one-shot

A chave de capacidade de uma sessão one-shot passa a incluir a identidade exata
da instância. As políticas que reutilizam conversas mantêm a chave de afinidade
existente. A admissão imediata pode selecionar a sessão aquecida reservada ou
exigir uma nova instância, aplicando os mesmos limites e regras de fila do pool.
Uma consulta prévia compartilha essas regras sem reservar capacidade; o adaptador
SQLite permite excluir sessões já selecionadas por outras candidaturas.

Essas mudanças são usadas pela descoberta descrita abaixo. A qualificação do
ciclo completo entre processos e hosts continua necessária antes da ativação.

## Descoberta paginada de candidatos

A composição do scheduler passa a fornecer uma implementação de descoberta,
com uma porta de aplicação e um adaptador SQLite. Cada página contém no máximo
uma candidatura por agente, independentemente de sua quantidade de endpoints,
grants ou instâncias. O cursor circular persiste o ponto de continuação e avança
o primeiro agente entre rodadas. A seleção inicial varia por handoff e geração.
Tentativas pendentes continuam aparecendo mesmo se o endpoint for desativado;
elas são recuperadas pela identidade original antes de permitir outra tentativa.

A descoberta aplica os predicados compartilhados de visibilidade, audiência e
dependências e exige opt-in e autorização atual de `execute_work`. A escolha de
endpoint usa a mesma regra de afinidade existente, prioridade e grupo não
ambíguo do fluxo conversacional, mas não exige a permissão de conversar para
executar um handoff. A capacidade não serve para desviar uma afinidade ocupada
para outro binding.

O pedido técnico preserva a origem autenticada do criador, binding, revisões e
gerações atuais. Para one-shot, a escolha exclui sessões já vinculadas a outras
candidaturas ainda não resolvidas e usa a admissão imediata do pool. Instâncias
distintas possuem chaves de capacidade distintas. Descobrir e persistir uma
candidatura não cria sessão, turno, chamada one-shot produtiva nem consumo de
grant. O processamento posterior obtém a reserva fora da UoW e passa pelo claim
e consumo canônicos já existentes.

Os testes exercitam descoberta e execução reais com SQLite e Core embutido,
incluindo duas sessões aquecidas em uso independente, bloqueio da mesma
afinidade e abertura de contexto distinto apenas nas políticas que o permitem.
O teste de paginação usa 100 agentes e endpoints repetidos e verifica retomada,
rotação e recuperação de candidatos revogados. Resultados e limitações estão
no ledger. Permanecem pendentes a ligação aos eventos e ao ciclo produtivo,
a classificação estrutural dos avisos competitivos, a compensação pós-consumo
e a qualificação entre processos e hosts. A instalação em execução não mudou.

## Avisos competitivos e sinais da agenda

A migração 134 acrescenta uma rota persistida ao registro de aviso criado pelo
Server. Novos avisos de handoffs broadcast usam `competitive`: mantêm mensagens
e entregas lógicas na inbox, inclusive para agentes MCP-only elegíveis, mas não
criam `runtime_pending_deliveries` nem passam pelo planejador conversacional.
Essa regra vale com auto-claim desabilitado ou host incompatível. O texto de uma
mensagem comum não estabelece essa classificação; imitar o JSON ou o assunto
de um aviso não muda seu roteamento. Handoffs diretos conservam o fluxo anterior.

Na atualização, relações estruturais existentes identificam os avisos antigos.
Os que ainda não possuem operação em `delivery_outbox` passam para a rota de
controle, recebem registro na agenda quando o handoff está aberto e deixam de
esperar na fila conversacional. A migração não lê nem reconhece a inbox em nome
de MCP. Avisos com operação já admitida ficam identificados como
`legacy_admitted`, com o histórico e o estado da operação intactos. A retirada
segura de operações admitidas mas ainda não enviadas e a reconciliação das que
possuem efeito incerto continuam pendentes antes da ativação produtiva.

Criação e desbloqueio registram a agenda na mesma UoW do handoff, sem disputar
antes do commit. Claim e encerramento acordam a limpeza da geração anterior
quando ainda existem tentativas sem consumo confirmado. A migração 135 grava
uma geração compartilhada de sinalização para mudanças de política, grants,
autoridade do agente, endpoints, perfis e bindings. Heartbeats e atualizações de
`last_seen` não reiniciam o backoff. Não são criadas tarefas por destinatário.

A composição do scheduler conecta o sinal de capacidade do runtime ao despertar
coalescido. Uma prova com o ledger físico do Core manteve o relógio da agenda e
a varredura de fallback parados: a publicação da liberação do slot foi suficiente
para reavaliar o handoff, confirmar o claim e consumir a reserva sem nova mensagem.
O motivo técnico da recusa, como `HOST_FULL`, é preservado no resultado da rodada
e determina o backoff. A inicialização e o desligamento desse consumidor no ciclo
produtivo do Server ainda dependem da recuperação pós-consumo e da qualificação
final. Nenhuma instalação ou processo em execução foi alterado.

### Retirada de avisos antigos antes do envio

Após o checkpoint `2f81022`, a migração 136 acrescenta auditoria própria para
retiradas internas e cursor persistido. A composição da agenda usa uma porta
de manutenção com páginas limitadas; registros incertos não impedem que o
cursor alcance os seguintes. A implementação SQLite compartilha a mesma
barreira de cancelamento antes do envio usada pela manutenção do operador,
agora extraída para um adaptador injetado. A decisão interna não personifica
um operador nem fabrica receipt do Core.

Somente a relação estrutural `legacy_admitted` permite examinar uma operação.
Estados posteriores ao envio, receipts de turno, resultados, histórico de
tentativas anteriores e execuções produtivas continuam preservados. Um ACK
`NONE` sozinho não comprova ausência de efeito. A transação registra a
auditoria, cancela os turnos ainda não enviados, libera apenas a propriedade
push correspondente e converte o aviso para a agenda, sem ACK de MCP.

Uma abertura já iniciada permanece intacta: retirar o prompt pendente não
equivale a encerrar o provider. Uma abertura comprovadamente não enviada pode
ser cancelada junto com o turno, encerrando sua lease ainda não criada. Para
one-shot, o cancelamento encerra a chamada lógica; o pool continua responsável
por fechar e confirmar a disposição de qualquer instância existente. A
retirada de um aviso de controle não publica uma falha de atendimento ao
criador. Mensagens e handoffs produtivos comuns mantêm suas notificações.

As provas incluem corrida com o lock real de envio, manutenção da conexão
saudável, sessão já aberta reutilizada sem enviar o aviso antigo, one-shot com
abertura independente seguida de fechamento confirmado e nova chamada,
rollback integral, cursor retomado, preservação do ACK de pull e estados
`SENDING`/`RECONCILING` ainda sem receipt. Os resultados detalhados, incluindo
correções de fixtures, estão no ledger. O bloqueio do despacho durante a
conversão e sua integração ao startup estão descritos na seção seguinte.
A recuperação pós-consumo e a qualificação completa do plano continuam
pendentes. Estas alterações permanecem locais.

### Conversão no ciclo de vida do Server e isolamento do despacho

O Server agora inicia um único consumidor de manutenção de avisos, com páginas
limitadas e produtor retido. Ele também funciona quando novas integrações
runtime estão desabilitadas. A classificação estrutural bloqueia o aviso nas
seleções de despacho legado e canônico antes do envio, sem depender de terminar
a varredura de todo o backlog. Avisos incertos continuam no histórico e não
voltam a ser prompts competitivos. Trabalho comum em outras sessões continua
elegível enquanto a conversão avança.

No shutdown, a manutenção deixa de iniciar páginas e aguarda seu writer atual.
Uma resposta HTTP pendente ou um observador cancelado não descarta esse
produtor. A contenção nativa ocorre em paralelo; a liberação do owner do banco
e o reset aguardam ambos. Falhas transacionais preservam o cursor e são
reavaliadas; não criam um segundo produtor. Startup parcialmente concluído
também encerra a manutenção antes de liberar os recursos.

A regressão de múltiplas sessões encontrou ocupação integral dos quatro
workers regulares por aberturas lentas de um único agente. O mesmo problema
foi reproduzido substituindo somente o módulo de despacho pelo checkpoint
`2f81022`. A contabilidade agora permite paralelismo por sessão, mas mantém um
crédito de worker para outro agente: três por agente em uma lane com quatro
workers; o limite equivalente vale para a lane separada de aberturas do pool.
Uma configuração explícita com um único worker não oferece essa folga.
Produtores ainda retornando após receipt continuam contando. O teto de bytes,
os créditos de transporte e a lane de controles continuam sendo aplicados.

As validações cobrem reinícios sucessivos em stores descartáveis, shutdown
pendente com HTTP disponível, continuidade de outro agente, retomada da quarta
abertura e regressões de reset. O subprocesso isolado do teste de CLI usa os
mesmos caminhos explícitos de Nexus, Core e dependências do teste principal;
isso é evidência de execução entre processos, não qualificação de wheels.
O ciclo produtivo de aquisição/consumo da agenda continua aguardando H5:
ligar a manutenção de avisos não habilita auto-claim nem a capacidade técnica.

## Compensação antes do consumo da reserva

O checkpoint `8a743a0` foi enviado por solicitação explícita do usuário. As
alterações desta etapa são posteriores a ele e permanecem locais.

A admissão consulta a identidade original da reserva antes de consumir. Quando
o host confirma `EXPIRED_UNCONSUMED` ou `RELEASED` sem consumo, uma única UoW
registra a prova, cancela as operações ainda não enviadas, encerra a tentativa e
reabre o claim canônico no mesmo epoch. O próximo claim incrementa esse epoch;
repetir a compensação antiga não reabre a nova execução. A migração 137 preserva
os IDs e referências das tentativas encerradas, liberando apenas a restrição de
candidatura ativa. A recuperação canônica usa ator de sistema, sem simular
credenciais ou autoridade de operador.

A prova deve corresponder ao request, reservation ID, revisão e operações
canônicas originais, incluindo hashes e sessão. Ausência de registro, timeout,
consumo anterior, troca de claim ou travessia da barreira de envio não autoriza
reabertura. Se a autorização de automação foi revogada enquanto a reserva ainda
estava HELD, a aplicação usa a autoridade de limpeza para liberá-la e exige a
mesma confirmação sem consumo. Todo I/O do host ocorre fora da transação SQLite.

Em one-shot, o encerramento da chamada passa pelo pool. Recursos aquecidos
continuam ocupados durante o fechamento e só desaparecem após confirmação do
owner existente. O envelope interno cancelado conserva sua reserva de inbox
para não ressurgir como trabalho MCP; nenhum ACK é inventado. O aviso original
do broadcast permanece independente. Essa compensação não gera uma segunda
resposta de erro conversacional e conserva o histórico de consumo do grant.

Os testes locais usam SQLite e o Core real com peers nativos sintéticos. Cobrem
expiração antes e durante consumo, liberação sem consumo, revogação, rollback
da transação, repetição tardia, operação incerta, isolamento one-shot e retomada
da descoberta automática após reconstrução do scheduler. As evidências e as
correções de fixtures estão no ledger. Ainda faltam compensação após consumo,
cancelamento de handoff já encerrado, integração produtiva do ciclo de vida,
readmodels/UI e qualificação completa entre processos/host remoto.

## Decisões canônicas e consumo sem início nativo

O cancelamento público continua restrito a handoffs OPEN e ao criador. Uma
reserva pendente desse handoff é limpa pela tentativa original, inclusive após
perda da resposta de reserve, sem claim nem consumo de orçamento.

Uma decisão autenticada pode ocorrer depois do claim e antes do início do
trabalho reservado. A limpeza agora conserva COMPLETED, REJECTED, VERIFYING e
epochs posteriores de retrabalho. O comprovante libera somente a admissão
antiga; não desfaz a decisão, não gera outro evento de reabertura e não torna
o trabalho elegível à disputa automática. A regressão de mudança de epoch
foi substituída por decisões públicas de verificação/retrabalho: o histórico
antigo pode ser limpo sem tocar a posse da geração nova.

Há também um intervalo entre consumir a reserva e iniciar a operação nativa.
O Core agora pode liberar explicitamente esse consumo ainda sem início. A
transação SQLite é a mesma usada pelas barreiras de abertura e turno: exige
opening_started=0 e ausência do registro de aquisição do turno; para abertura
fria, libera exclusivamente o placeholder pertencente ao ticket. A sessão
física existente de next_turn permanece ocupada. Identidades de consumo e
bindings continuam no journal e impedem uma execução tardia. Isso não é
expiração por prazo de capacidade consumida.

RELEASED com consumo registrado não basta para o Server presumir ausência de
efeito. A compensação exige também as operações canônicas exatas ainda antes
da barreira de envio, sem receipts ou início da chamada one-shot. Se a decisão
canônica muda durante o RPC de consumo, o Server solicita a liberação e aplica
essas duas provas na mesma UoW da limpeza. Se abertura ou turno já começou,
o Core mantém RELEASE_PENDING até a prova de encerramento aplicável.

Os testes exercitam ambas as barreiras com ledgers independentes, decisões
antes/depois do consumo, resposta perdida, verificação/retrabalho, pool frio e
aquecido e o leitor R4 do Connector. O formato capacity-v2 não mudou. Evidências
e correções de fixtures constam em capacity_terminal_cleanup_validation no
ledger. Contenção de execução nativa já iniciada e a ativação produtiva do
ciclo completo ainda estão pendentes; esta etapa permanece local.

### Pi: contrato de claim e diagnóstico de permissão

A investigação somente de leitura da instância em execução encontrou, em
2026-10-14T02:48:32Z, uma chamada `nexus_handoff_claim` com `claim_epoch=1`
para um handoff OPEN, ainda na epoch zero. A capability da sessão incluía
`handoff.claim` e `handoff.complete`; o agente não tinha override que negasse
trabalho. O campo opcional acionou a recuperação de um claim já existente,
cuja posse de sessão naturalmente não existia. O retorno foi PERMISSION_DENIED.

O Server agora distingue esse argumento inválido em um handoff OPEN e retorna
VALIDATION_ERROR com orientação para omitir a epoch. A checagem continua depois
da autorização de trabalho e elegibilidade. Claims existentes continuam exigindo
a mesma sessão e geração; nenhuma permissão foi ampliada. A extensão Pi do Core
explica como reivindicar, preservar a epoch retornada e completar, e informa que
o payload pode ser omitido na leitura anterior ao claim. Na ocorrência analisada,
o payload estava presente no banco; a ausência na consulta era a proteção esperada.

Validação e evidências estão registradas em pi_handoff_claim_validation no ledger.
Esta correção permanece local e não altera a instância em execução.

### Vínculo do claim automático às ferramentas da sessão vencedora

A revisão do ciclo completo encontrou uma lacuna distinta do argumento inválido
enviado pelo Pi: o claim feito pelo scheduler não possuía ExecutionPrincipal e,
portanto, não gravava execution_tool_claims. A sessão vencedora recebia o trabalho,
mas não tinha a prova de posse exigida por handoff_complete. A persistência desse
vínculo agora pertence a uma porta de aplicação, ExecutionClaimRepository, com
adaptador SQLite composto no bootstrap e nos serviços MCP/native.

A admissão canônica grava o vínculo depois de selecionar a sessão e persistir
as operações, ainda na mesma UoW. O adaptador confere o handoff/epoch/claimant,
workspace e o escopo exato do turno admitido. Um vínculo existente não pode ser
transferido para outra sessão ou geração. Mensagens normais não criam autoridade
de handoff. Uma chamada one-shot enfileirada só recebe esse vínculo quando o pool
admite sua sessão real; não existe sessão fictícia para a fila.

MCP e native podem retomar o claim já adquirido informando a epoch original,
sem novo CAS nem dispatch. O payload no handoff_get e no replay nativo permanece
restrito à sessão dona quando o chamador usa uma capability gerenciada. Credenciais
canônicas conservam suas regras anteriores. A conclusão de negócio não libera
um turno nativo ainda em execução; a confirmação física continua independente.

Os cenários usam reserva, admissão, lease e endpoints públicos reais com peers
nativos de teste. Qualificação com providers instalados, contenção após efeitos
iniciados, ativação do scheduler produtivo e os demais gates do plano permanecem
pendentes. Nenhum serviço em execução foi modificado nesta etapa.

### Isolamento das gerações da agenda após compensação

O teste de recuperação revelou que a descoberta consultava tentativas ativas
apenas por handoff/agente, sem restringir claim_generation à geração da agenda.
Uma página atrasada da geração anterior encontrava a tentativa recém-criada da
geração seguinte, considerava-a inválida e a cancelava antes da reserva. O CAS
canônico impedia dois vencedores, mas não impedia esse cancelamento indevido e
a recriação de tentativas. A consulta da página e a busca da tentativa ativa
agora incluem a geração da agenda. O teste determinístico prepara a nova
tentativa antes de executar a página antiga e exige que ela permaneça intacta.
O teste de reinício mantém a exigência original de exatamente duas tentativas:
a compensada e a nova vencedora; a asserção não foi relaxada.

### Autorização do trabalho durante a renovação local

A lease técnica da sessão era renovada com base no grant de abertura/envio,
sem revalidar o grant distinto de execute_work ou a autorização de automação
do handoff em andamento. A porta RunningHandoffRepository agora seleciona o
trabalho nativo ainda não encerrado no escopo exato da sessão. O adaptador
SQLite usa as operações e receipts canônicos; histórico terminal e mensagens
comuns não passam a depender do grant de um handoff antigo.

ExecutionWorkLeaseAuthority reutiliza a autorização canônica de RuntimeWork
para claims em andamento, sem consumir novamente o orçamento. Rejeição ou
troca de epoch exige contenção da execução antiga. COMPLETED e VERIFYING na
mesma epoch permitem finalizar a resposta nativa; a decisão de negócio não
libera capacidade física nem reabre o handoff.

Na execução embedded, a recusa da renovação é entregue ao owner de recuperação
da sessão já existente. Esse owner conserva a tarefa de encerramento e tenta
novamente se a prova de parada ainda não estiver disponível. Antes, uma falha
nesse encerramento podia escalar para recuperação de todas as sessões do agente.
Os testes retêm uma parada, forçam uma falha, executam trabalho numa sessão irmã
e só observam RELEASED depois da confirmação real do Core. O claim, a epoch e
o orçamento original são preservados; não se aplica compensação sem efeito a
uma execução que já iniciou.

Esta checagem adicional está habilitada apenas para embedded. A revisão do
Connector encontrou que a recusa de lease no R4 atual é um frame error sem
request_id/sessão: o leitor fecha o link, pois não pode atribuí-lo a uma das
renovações concorrentes. Além disso, o owner remoto escala falhas de renovação
para fechamento da conexão. É necessário negociar uma resposta correlacionada,
conter a sessão original e publicar a prova de liberação sem perder o canal
das demais sessões antes de habilitar a mesma checagem remota. O contrato R4
imutável não foi alterado nem foi adicionada uma credencial de operador.

A checagem local ocorre na renovação existente, não é um novo agendador de
revogação imediata. Continuam pendentes o ciclo produtivo completo, a contenção
remota, a recuperação após reinício nesse corte e a qualificação com providers
reais. Evidências desta etapa constam em running_work_lease_validation no ledger.
Tudo permanece local, sem reinstalação, reinício, commit ou push.

### Recusa de lease correlacionada e contenção no Connector

O Core agora fornece a extensão negociada `nexus-lease-denial-v1`, com schema,
manifesto com hashes e fixtures próprios. O frame `lease.denied` carrega a
requisição `lease.renew` original completa, sem bearer material. Sua identidade
inclui request_id, sessão, owner generation, grant, serial e conexão. O codec
R4 imutável continua recusando esse frame; somente o roteador de extensões o
aceita após negociação explícita. Recusa não é recibo de execução nem prova
de encerramento.

O Nexus oferece a extensão somente quando o peer a solicita. Uma falha de
lease.renew sob link autenticado pode então ser respondida sem perder sua
correlação. lease.applied não recebe ACK inventado: se sua transação falhar,
o replay da requisição usado como barreira de confirmação revalida a autoridade
e devolve a recusa correlacionada. Peers antigos conservam o frame error antigo.
Falha na autenticação do link não é convertida em recusa de uma sessão.

O leitor único do Connector valida a requisição inteira contra a tentativa
retida, inclusive durante a barreira de confirmação. Outra sessão ou geração,
grant, serial ou request_id não pode receber esse erro. Uma recusa válida gera
LeaseRequestDenied para o produtor correspondente, sem fechar o transporte das
demais requisições. Cancelar o observador não remove a correlação do produtor.

Quando a recusa corresponde à renovação de uma sessão em execução, seu owner
fenceia novos ingressos produtivos e conserva a tarefa de renovação como dona
da contenção. O mesmo runtime é encerrado pelas APIs públicas do Core; falha
ou prova incompleta mantém o recurso e gera nova tentativa apenas dessa sessão.
O teste usa dois peers distintos, trabalho nativo já submetido, uma parada que
falha e uma sessão irmã que continua executando. Capacidade física só deixa o
ledger após a confirmação do Core. O journal e as publicações originais ficam
retidos; nenhum runtime.close ou sucesso de negócio é fabricado.

A extensão ainda não é anunciada automaticamente pelo Connector, e a nova
checagem de autorização de trabalho continua embedded-only. Antes da ativação
remota faltam a obrigação durável no Server, publicação/aceitação da prova de
liberação por sessão no canal ativo e tratamento de operações que já estavam
enfileiradas quando a renovação falhou. Hoje elas são impedidas de executar,
mas a exceção ainda pode entrar no fallback que fecha o link; a recusa da lease
inicial também precisa do caminho correlacionado de operação sem efeito. Esses
cortes não estão qualificados e não foram tratados como concluídos.

O wheel local Core 0.0.11 inclui explicitamente os recursos capacity/v2 e
lease_denial/v1. A verificação isolada importou o Core do próprio wheel usando
somente uma raiz explícita das dependências já instaladas; isso valida os
recursos empacotados, não substitui a campanha de instalação final dos três
artefatos. Evidências, ajustes de fixtures e pendências estão em
remote_lease_denial_validation. Branches/versões continuam Nexus 0.3.0,
Core 0.0.11 e Connector 0.0.9. Todas as alterações permanecem locais.

### Obrigação durável de contenção por sessão

A migração 138 acrescenta `execution_session_containment`. Uma recusa de
renovação autenticada e negociada registra a obrigação antes de responder ao
Connector. O registro conserva a operação/hash de abertura, a geração do owner
e a requisição original. A correlação usa a autoridade histórica aplicada,
inclusive quando a nova lease foi emitida mas recusada na confirmação; não
exige que o grant revogado volte a ser válido para permitir a contenção.
Pedidos iniciais, inventados ou de outra sessão/conexão não criam esse registro.

`ExecutionSessionContainment` define a porta de aplicação e o DTO de destino;
o adaptador SQLite implementa a persistência. A obrigação não significa que o
processo já parou. Enquanto estiver pendente, bloqueia renovação, despacho
produtivo e autoridade de ferramentas MCP/nativas daquela sessão, mesmo se o
grant for restaurado. Outras sessões conservam suas próprias leases. Interromper
e fechar continuam sujeitos à autorização existente e não são bloqueados pela
nova obrigação.

A reconciliação existente de reconexão registra a liberação na mesma transação
que valida os recursos e o fluxo de eventos originais. Digest, geração ou stream
incorretos não encerram a obrigação. Falha após sua atualização desfaz também
a mudança de prontidão da sessão e do executor. Não é fabricado receipt de
fechamento, conclusão de trabalho nem ausência de efeito.

Os testes desta etapa totalizam 76 casos distintos aprovados, com evidências e
duas correções de expectativas do teste de controle registradas em
`session_containment_obligation_validation`. A recriação dos serviços verifica
que o estado não depende de memória; isso não substitui a campanha final de
restart em processos/hosts independentes.

Ainda falta publicar e confirmar a prova de liberação de uma única sessão pelo
canal remoto que continua ativo. A reconciliação global existente é apenas o
caminho de recuperação após reconexão, não a solução de isolamento ao vivo.
Também faltam os desfechos correlacionados das operações já aguardando uma
renovação recusada e da recusa da lease inicial. A negociação automática e a
checagem remota de trabalho permanecem desabilitadas até esses cortes estarem
implementados e validados. Nenhuma instalação foi alterada; sem commit ou push.

### Protocolo de liberação no canal ativo e validação independente

O Core acrescenta a extensão negociável `nexus-session-release-v1`, separada do
contrato R4 imutável. O relatório identifica a abertura original, escopo e
geração, prova de liberação, posição final dos eventos e digest dos receipts
canônicos mais recentes. O digest é calculado incrementalmente em ordem de
operation_id. A resposta accepted ou deferred contém a requisição original
inteira; não confirma outra sessão nem representa conclusão de negócio.

No Nexus, `ExecutionSessionRelease` usa uma porta de observação/persistência.
A leitura e validação de todo o histórico ocorre em snapshot somente leitura;
o commit compara uma revisão compacta da sessão, operações, receipts e eventos.
Um escritor concorrente pode progredir durante a leitura, mas sua mudança
invalida a confirmação. Apenas a transação curta final fecha a sessão, projeta
a liberação e encerra a obrigação. Falhas deixam o estado anterior intacto.

O WebSocket não aguarda a leitura histórica. Um owner limitado a quatro tarefas
retém validações, deduplica pedidos em andamento e responde deferred quando
está cheio. O encerramento do canal observa essas tarefas antes de liberar sua
identidade. O teste segura a leitura de uma sessão e confirma uma lease de
outra pelo mesmo socket, inclusive com escrita SQLite concorrente.

O transporte do Connector mantém o leitor único, correlação integral, produtor
retido após cancelamento do observador e repetição dos mesmos bytes/ID após
timeout do ACK. Respostas duplicadas idênticas são toleradas. A alteração de
sessão, geração, ID ou provas não pode confirmar o pedido original.

`R4SessionReleaseReporter` constrói o relatório usando APIs públicas do Core.
`Journal.get_session_claim` consulta a abertura exata, sem varrer o histórico
de outras sessões. O reporter exige slot liberado, publicações reconhecidas,
projeções iguais aos receipts atuais do Core e cursores remoto/local de eventos
iguais ao fluxo final. A sessão irmã ativa não impede essa validação. Os testes
também corrigiram um relógio simulado que contava duas vezes o tempo de
renovações simultâneas; a política de prazo em produção não foi relaxada.

As evidências estão em `live_session_release_validation`. O wheel Core 0.0.11
foi construído e seus contratos foram verificados por importação do artefato;
isso não é qualificação de uma instalação nem campanha de host independente.

O vínculo durável com o owner foi implementado na etapa descrita abaixo.
Operações já aguardando a renovação recusada e recusas de lease inicial
continuam pendentes. As extensões não são negociadas automaticamente;
a checagem remota de trabalho não foi ativada.

### Publicação durável da liberação pelo owner do Connector

`R4SessionReleasePublisher` usa a porta `SessionReleaseOutbox`; seu adaptador
SQLite confirma os bytes exatos antes do envio. Um resultado desconhecido
mantém o pedido original, mesmo se o reporter já conseguir observar um
histórico mais recente. Somente uma resposta deferred correlacionada permite
outra observação. O ID inclui o histórico observado, evitando a reutilização
do mesmo ID com receipts ou cursores diferentes.

O owner executa esse produtor na tarefa retida da sessão após confirmar a
parada e drenar ferramentas nativas. Contenção física e confirmação do Server
são estados separados. Uma publicação pendente não repete a parada e não
ocupa os workers das sessões irmãs. Um evento explícito de shutdown termina
a espera pelo ACK e preserva a outbox; cancelar apenas o observador continua
sem abandonar o produtor. Uma confirmação tardia não é convertida em sucesso
local sem o respectivo commit.

`session_release_outbox_validation` registra 104 testes distintos aprovados,
incluindo uma falha real de commit SQLite da confirmação, reconstrução do
publicador, parada durante espera e execução de uma sessão irmã enquanto a
prova permanece sem confirmação. Os testes do owner usam journal/ledger reais
do Core e peers nativos simulados; não qualificam providers nem o restart de
um host remoto independente.

A reconciliação global autenticada continua responsável pela troca de geração;
sua integração com a outbox está descrita a seguir. Permanecem os cortes de
recusa de lease inicial e operações na fila, as demais entregas H5/H6 e a
campanha do tuple instalado. Não houve ativação, reinstalação, reinício,
commit ou push.

### Baixa da outbox após reconciliação em nova geração

O handshake só chama o produtor de commit após validar o ACK do ciclo exato
e confirmar que o relatório está completo. O callback fica retido durante
cancelamento do observador. Erro no commit impede que o Connector prossiga
para publicação de inventário e prontidão de execução.

`R4ReconciliationReporter` conserva, com orçamento limitado, os fatos de
liberação efetivamente enviados e a identidade da abertura original. A porta
`SessionReleaseRecoveryOutbox` aplica a baixa em páginas. Confere a geração
nova, abertura/hash originais, binding, agente, sessão, geração do owner e
watermark do fluxo. Registro sem fato correspondente permanece pendente;
conexão pronta não significa liberação de qualquer sessão.

A migração v2 da outbox acrescenta uma prova de reconciliação com hash sem
modificar os bytes originais nem fabricar um ACK no canal antigo. O limite de
publicações pendentes deixa de contar o histórico já resolvido. Um canal
reconciliado também recusa observações com outro ID, evitando reativação local
de uma obrigação antiga.

`session_release_recovery_validation` registra a suíte de 117 testes aprovada,
incluindo migração, páginas com registros não correspondentes, rollback de
commit, ACK incorreto e cancelamento. A integração usa journal e ledger reais
do Core, mas peers nativos e de protocolo simulados. Após perder o ACK da
liberação, uma nova geração resolve a pendência sem abrir outro harness;
falha de commit permite nova reconciliação do mesmo histórico.

O próximo corte é a recusa das operações produtivas que já aguardavam uma
renovação negada, seguida da recusa de lease inicial. A publicação/recuperação
agora está integrada, mas esses caminhos ainda podem acionar o tratamento
genérico que encerra o canal compartilhado. Negociação automática e guarda
remota de trabalho continuam desativadas até essa correção e sua validação.

### Recusas de operações aguardando lease e da abertura inicial

O corte descrito acima foi implementado. O Core oferece uma associação pública
de recusa, sem payload ou autoridade inventada, vinculada à negativa de lease
correlacionada pelo host. Um domínio distinto de hash permite usar o journal
existente para impedir execução tardia com o mesmo ID. Uma intenção nativa já
admitida entra em conflito e conserva sua evidência; ela não pode virar uma
recusa sem efeito. A recusa usa quota normal, preservando a reserva para
interrupt/close, e não cria claim de sessão nem slot físico.

O Connector persiste essa associação antes da admissão técnica da recusa.
A recuperação pode concluir o mesmo receipt nos cortes entre associação,
admissão, resultado terminal e publicação. Um vínculo genérico sem receipt
continua incerto; a correção não infere ausência de efeito de qualquer lacuna
no journal. O owner marca a negativa antes de liberar o gate de renovação,
recusa a operação enfileirada sem chamá-la no provider e mantém a sessão irmã
executando. A recusa inicial encerra os recursos do runtime ainda sem abertura
e não tenta produzir uma prova fictícia de encerramento nativo.

No Nexus, a negativa inicial fica registrada apenas quando corresponde ao
bootstrap original autorizado e à sua geração. O ingresso HTTP exige esse
registro para aceitar a falha sem uma lease aplicada. O receipt sem efeito,
o encerramento da sessão pendente e a baixa da obrigação são atômicos.
Alterações no receipt, ausência da negativa ou falha de commit não encerram a
sessão. Recusas de renovação continuam exigindo a prova física correspondente.

`lease_refusal_validation` registra 172 casos distintos aprovados nos três
repositórios. Inclui journal/ledger reais, disputa entre duas conexões ao
journal, quatro cortes de persistência, execução de sessão irmã, negação de
receipts incorretos, repetição idempotente e rollback do fechamento. Fixtures
de protocolo/provider são simuladas; houve também validação HTTP/WebSocket
autenticada local do Server. A campanha instalada e em host independente ainda
não foi executada.

### Negociação e revalidação de trabalho remoto

O Connector agora anuncia `nexus-lease-denial-v1` e
`nexus-session-release-v1`. O canal autenticado do Server conserva somente
as capacidades aceitas no handshake; sua identidade serializada continua
contendo os quatro campos originais, sem estender frames imutáveis.

A revalidação de trabalho em execução passa a atender também os runtimes
remotos quando ambas as extensões estão negociadas. A descoberta de candidatos
e a autoridade de capacidade exigem esse suporte para novas aquisições e
consumo remoto. A segunda checagem impede que uma descoberta anterior contorne
uma mudança de suporte. Consulta e liberação de reservas históricas permanecem
disponíveis para recuperação. Os demais modos de execução de conectores antigos
mantêm o comportamento anterior; nenhum LLM é acionado como fallback.

`negotiated_work_containment_validation` registra 150 testes distintos aprovados:
55 no Nexus e 95 no Connector. As falhas intermediárias dos quatro casos de
descoberta eram de preparação da fixture remota: integridade do cadastro e
política de localização. Após corrigir ambos, os quatro casos passaram.

As evidências cobrem negociação ausente/parcial/completa, recusa antes da
concessão e antes da aplicação da lease, repetição da negativa, progresso de
sessão irmã no mesmo canal, recuperação de reservas, reconexão e regressões de
contenção/publicação. O teste de revalidação usa WebSocket autenticado e regra
real de autoridade, com a porta de leitura do trabalho controlada. Não equivale
à campanha completa entre processos/hosts independentes.

Permanecem as demais entregas H5/H6, a integração produtiva da agenda,
UI/modelos de leitura, lockfiles/artefatos e campanhas T39/T40. Nenhum commit,
push, reinstalação, reinício ou ativação na instância atual foi realizado.

### Agenda integrada ao ciclo de vida do Server

O startup compõe um `HandoffRuntimeService` que aciona a agenda limitada e
retém seus produtores até o encerramento efetivo. A configuração de rollout
`runtime_handoff_auto_claim_enabled` é exclusiva do startup e permanece falsa
por padrão; o opt-in global/agente e o grant `execute_work` continuam sendo
autoridades independentes. Quando há tentativas persistidas, o serviço inicia
mesmo com o rollout desligado, em modo de recuperação sem novas aquisições.

A descoberta desse modo cancela/reconcilia reservas ainda sem claim. Operações
já comprometidas mantêm suas identidades e seguem a recuperação existente.
O host embedded habilita a capacidade compartilhada quando a agenda precisa
dela. A composição produtiva do daemon Connector agora habilita a capacidade
do Core e anuncia suporte por negociação, mantendo a autoridade no Server.

O shutdown fecha a admissão e a criação de tarefas imediatamente. A contenção
nativa ocorre em paralelo ao esvaziamento da agenda; o lock/store só é liberado
depois dos produtores. O caminho de falha parcial de startup fecha o owner real
mesmo sem coordenador completo. O reset encerra esse owner e cria outro após a
limpeza. A documentação de notificações e o help CLI descrevem ativação e rollback.

Os testes de integração do Connector revelaram um observador legado de mudança
de conexão que ficava pendente no teardown. O daemon agora retém e aguarda esses
observadores no shutdown. A repetição da suíte passou sem o aviso.

`scheduler_lifecycle_validation` registra 79 casos distintos aprovados: 47 no
Nexus e 32 no Connector. Inclui aquisição automática sem ticks manuais, opt-in
independente, reserva recuperada após restart com rollout desligado até a agenda
ficar IDLE, planner bloqueado durante contenção nativa, observador de fechamento
cancelado, falha parcial de startup, reset e novo handoff, e regressões da agenda,
shutdown e fronteiras hexagonais. As CLIs nativas são simuladas; T39/T40 continuam
pendentes, assim como a UI/modelos de leitura e o tuple instalado final.

Todos os processos de teste terminaram. Nenhuma alteração foi instalada na
instância atual; não houve commit nem push.

### Opt-in na interface e salvamento atômico da política

Settings agora oferece o opt-in global para handoffs broadcast. A modal de
Connections permite herdar, habilitar ou desabilitar por agente. O campo explica
a reserva de capacidade, execução somente pelo vencedor e necessidade das
permissões e grants existentes. A interface informa separadamente quando o
rollout de startup está desligado; salvar a preferência não ativa esse rollout.

O opt-in pertence ao Server, fora da configuração técnica portátil do Core.
No setup, campo ausente preserva a política e null restaura herança. Finish salva
essa política na mesma transação dos demais ajustes, com CAS e idempotência.
O snapshot inicial retorna política e revisão na mesma leitura. Importar ou
trocar instalação/binding conserva a revisão original da política durante a
edição, impedindo sobrescrita silenciosa de mudanças concorrentes.

O teste de revisão obsoleta encontrou um defeito no tratamento HTTP: detalhes
ausentes de um conflito provocavam AttributeError e HTTP 500. A correção mantém
o retorno CONFLICT e a ausência de alterações persistidas. As verificações de
modal foram atualizadas para o rodapé portado; a de revogação aguarda a prova
real de encerramento pelo owner assíncrono, sem exigir parada no observador.

`auto_claim_policy_ui_validation` registra 46 casos distintos aprovados, incluindo
11 no navegador Edge com dashboard compilado, API e SQLite reais. O provider do
teste de conexão é simulado. Build TypeScript/Vite, sintaxe Python e whitespace
passaram. Capturas da política global e da modal foram inspecionadas em
`output/playwright/auto-claim-policy/`. Todos os processos terminaram.

Continuam pendentes os modelos de leitura e indicadores operacionais, auditoria
completa dos critérios T01–T40, artefatos/locks e campanhas instaladas em processos
e host independente. Nenhum commit, push, reinstalação ou reinício foi realizado.

### Projeções de andamento e histórico de tentativas

Foi implementada a porta `HandoffRuntimeViewRepository`, seu adaptador SQLite e
composição no bootstrap. A administração recebe o serviço por injeção. As leituras
não disputam handoffs, não consultam providers e não liberam recursos. A migração
139 acrescenta um índice para a página limitada do histórico por agente.

Cards e detalhes de handoffs broadcast mostram o andamento separadamente do
estado canônico. Final nativo implica espera por decisão; VERIFYING continua
sujeito à verificação. Somente o binding do epoch atual fornece receipts, impedindo
que uma execução histórica seja apresentada como execução do novo dono. Origem
ausente, canal de claim e latências comprováveis ficam explícitos. Com rollout
desligado, trabalhos abertos são apresentados como disponíveis para claim explícito.

A modal do agente mostra até 20 tentativas recentes, em painel recolhível, com
motivos e horário do último relatório de reserva. O relatório de admissão/consumo
substitui o antigo relatório da tentativa. A leitura não retorna payloads,
credenciais, principal/request internos nem chaves de origem de sessão.

`runtime_read_models_validation` registra 39 casos distintos aprovados. Inclui
28 testes de projeção/domínio, quatro regressões de administração, seis de HTTP,
dependências e fronteiras arquiteturais, e um fluxo real de navegador. O primeiro
teste de VERIFYING falhou por faltar o flag de verificação na fixture; a repetição
com esse cenário habilitado passou. Build e verificações estáticas passaram.
As capturas em `output/playwright/handoff-runtime-views/` foram inspecionadas.

Naquela etapa, a entrega cobria histórico e andamento; a inspeção contextual e
as métricas agregadas continuavam pendentes. A etapa abaixo acrescenta essas
leituras. A auditoria T01–T40 e as campanhas instaladas/remotas permanecem abertas.

### Observações contextuais de capacidade e métricas limitadas

O registro de disponibilidade agora mantém um cache limitado de observações
reais de avaliação, reserva, consumo e liberação. Não é uma segunda autoridade
de recursos. A leitura não consulta o host, não acorda o scheduler e não altera
claims ou reservas. Respostas antigas, troca de owner, mudanças de revisão,
avaliações concorrentes com mutações e expiração não restauram capacidade livre.
Uma liberação observada nunca é convertida automaticamente em disponibilidade.

A porta de leitura recebe um adaptador SQLite que verifica as revisões atuais
de configuração/autorização/credencial, binding, workspace, owner e sessão.
O cálculo das revisões ganhou um modo somente leitura; o comportamento de
persistência usado na autenticação permanece o padrão. A consulta é limitada
a uma página de contextos e não grava contadores nem invalida lanes por leitura.

A modal mostra até 20 contextos em um painel recolhível, separando sessão
observada ociosa, capacidade de abertura, reserva, uso, espera e desconhecido.
O tempo de validade vem da observação, limitado a cinco segundos. O navegador
também expira a apresentação quando a próxima requisição fica pendente.

O endpoint local de métricas, somente para operadores, agrega amostras das
últimas 1.000 tentativas e dos últimos 1.000 handoffs broadcast. Estados, motivos,
canal vencedor e latências observadas usam rótulos limitados, sem IDs ou payloads.
Truncamento e tamanho da amostra são explícitos; não se apresentam como contagem
global de backlog ou vagas livres. Falha no armazenamento retorna indisponível,
e latência sem evidência não é convertida em zero. A migração local 139 inclui
índices para as duas consultas de amostragem, além do histórico por agente.

Validação final: 84 testes distintos aprovados, somando diagnóstico/cache/escopo,
métricas, regressões de autenticação/administração/projeção/arquitetura e dois
fluxos no navegador. As falhas intermediárias eram expectativas de fixture:
localização das credenciais, header restrito ao endpoint de operador e expiração
de uma avaliação do Core em 100 ms durante a consulta. O teste de mudança de
configuração agora controla apenas o relógio das observações; testes separados
mantêm a prova de expiração, inclusive no navegador real com resposta bloqueada.
Build TypeScript/Vite, sintaxe Python e whitespace passaram. Evidências detalhadas
estão em `runtime_diagnostics_validation` no ledger. Capturas revisadas em
`output/playwright/handoff-runtime-views/`. Nenhum commit, push, reinstalação,
reinício ou alteração da instância do usuário foi realizado.

### Auditoria dos critérios e campanha entre processos

A matriz `acceptance-audit.md` passa a registrar cada requisito T01–T40 com
evidência e limites explícitos. Listas de pendências nas etapas históricas do
ledger descrevem seus checkpoints; a matriz consolida o estado atual. Não se
considera um lote de testes aprovado como prova de requisitos não exercitados.

Foram acrescentados cenários integrados de 100 candidatos realmente cadastrados
e conectados pelas APIs, três sessões autenticadas de origem simultaneamente
ocupadas, perda do sinal de capacidade com recuperação por varredura limitada e
duas tarefas disputando a última vaga física. O último cenário também confirma
o erro público de claim tardio pelo MCP e a possibilidade de o MCP assumir a
tarefa que ficou sem capacidade runtime. Não inicia outro provider por isso.

Uma recusa depois de enviar reserve não encerra imediatamente a tentativa:
outra requisição em trânsito pode ter produzido uma reserva. O teste exige a
confirmação durável de liberação da identidade original. A tentativa vencedora
permanece ativa enquanto executa; as 99 perdedoras no cenário de escala são
encerradas sem efeito. Esses ajustes corrigem expectativas dos testes e não
enfraquecem a recuperação implementada.

O novo runner `capacity_connector_process.py` inicia um daemon Connector em
processo separado, com diretório e journals próprios. Somente descoberta e
provider são sintéticos. Negociação, TCP HTTP/WebSocket, tickets, lanes, leases,
reservas, execução, receipts e shutdown usam os componentes reais. O Server não
acessa o ledger do Connector e o filho não importa componentes do Server. As
credenciais descartáveis passam por stdin, sem serem registradas na saída.

A campanha exercita perda da resposta depois da reserva remota, consulta pelo
mesmo identificador, recusa por limite físico, desconexão/reconexão, reinício
com ticket persistido, execução posterior e encerramento físico confirmado.
Os resultados finais e o escopo exato ficam em `acceptance_audit_validation` no
ledger. Isso não substitui a campanha instalada com o tuple final nem a máquina
remota independente de T40. A instância do usuário não foi alterada.

### Seleção entre executores, ordem e desfechos canônicos

A campanha complementar aprovou 48 casos distintos: 26 de seleção/scheduler/
métricas, 17 de desfechos e autorização, um de ordem por sender, um de fanout
comum e três de fronteiras arquiteturais. Os critérios T08, T22, T32, T33 e T34
agora têm evidência integrada registrada na matriz e no ledger.

Dois Connectors foram executados em processos separados para o mesmo agente.
O cadastro atual substitui a máquina anterior; por isso o teste prepara
explicitamente o formato de catálogo histórico/restaurado com dois bindings
aprovados. Grants, autenticação, canais, journals, capacidade e execução usam
os caminhos reais. Prioridade e grupo resolvem um único destino; afinidade
ocupada prevalece sobre outro endpoint de maior prioridade, e sessão não
reconciliada não é ignorada para fabricar uma vaga. Grants revogados são
excluídos. Providers e inventários são sintéticos.

Esse teste revelou uma falha de diagnóstico: a seleção recusava corretamente
um empate, mas a descoberta convertia seu motivo em RECOVERING. O resolvedor
agora fornece o motivo estruturado AMBIGUOUS_BINDING, reconhecido pelo scheduler
e pelas projeções limitadas. O backoff trata-o como conflito de configuração;
nenhuma reserva ou execução é admitida durante a ambiguidade. A correção fica
na camada de aplicação e não altera contratos negociados do Core.

O teste de ordenação envia três mensagens diretas do mesmo sender; o handoff
fica OPEN e sem consumo de grant até as três terminarem em FIFO na mesma
sessão. A prova de fanout usa dois agentes runtime e um MCP-only com sessão no
workspace, e confirma o encaminhamento direto apenas ao agente escolhido.

Os testes de desfecho executam de fato o turno antes do final nativo e da
conclusão autenticada, por MCP e por ferramentas nativas. Repetir completion ou
verificação não multiplica eventos/notificações. Conversation habilitado não
gera uma segunda resposta do auto-claim. Reprovação mantém o dono no epoch2,
sem recolocar a tarefa na disputa inicial. Nenhuma semântica de conclusão foi
alterada para satisfazer os testes; feedback foi retirado apenas do verdict
pass da fixture, conforme o contrato vigente.

Os processos de teste terminaram. A alteração de diagnóstico, seus testes e os
registros permanecem locais; nenhum commit, push ou mudança da instância em uso.

### Deadline de startup e contenção da abertura fria

A auditoria de T16 reproduziu duas falhas reais. O pool aceitava iniciar uma
chamada depois do admission_deadline se o despacho ganhasse a corrida contra a
varredura de expiração. Além disso, uma abertura competitiva one-shot vencida
ainda recebia renovação de lease. A regra de início agora compara o prazo na
própria transação de despacho. O serviço de autoridade recebe o instante do
Server e consulta o deadline por um método do port de repositório; o adapter
SQLite vincula chamada, reserva, abertura e escopo exato. Uma chamada já iniciada
continua sujeita ao prazo de execução, sem ser cancelada pelo antigo prazo de
startup. Nenhuma regra de pool depende de SQL ou do Connector.

Os novos testes usam os dois adapters de pool, o dispatcher embedded e um daemon
Connector em processo separado. O provider sintético pode reter a abertura;
transporte, leases, reserva física e confirmação de parada são reais. O teste
remoto mostrou um segundo problema: o pool admitia close enquanto o owner de
contenção já encerrava a sessão após negar a lease. O pool passou a consultar a
obrigação existente antes do close automático. O canal permanece disponível e
a vaga só é devolvida após a prova de liberação.

T16 continua parcial. Expirar antes da primeira lease local revela uma lacuna
no owner embedded: a negação é encaminhada para recuperação do agente, sem
concluir o bootstrap como recusa comprovadamente sem efeito. O teste conserva
essa falha, com OPEN_PENDING/NONE e slot CLOSING; nenhum provider é aberto.
É necessário tratar a recusa inicial com persistência/recuperação pela mesma
operação, incluindo os cortes de commit, antes de qualificar o critério. Os
relatórios, falhas de fixture e resultados finais ficam em
`startup_deadline_validation` no ledger. Nenhuma instalação foi alterada.

### Recusa inicial embedded: persistência e reinício

A recusa da primeira lease agora é persistida como obrigação de contenção da
operação original antes da publicação da falha. O owner mantém a recuperação
por sessão; falhas de gravação nessa etapa não bloqueiam as sessões irmãs.
A associação para o receipt é persistida antes do fato no Core. O Core conserva
sua proteção de identidade: um intent nativo existente ou efeito incerto não
pode ser substituído por uma recusa sem efeito. Não são fabricados stream,
sessão nativa ou contexto autorizado para registrar a recusa.

As consultas e a associação persistida ficam no adaptador SQLite através de
SessionContainmentRepository. O bootstrap coordena essa porta com as APIs de
journal, capacidade e publicação; as regras de pool continuam independentes
da infraestrutura.

O teste com dois ciclos de vida do Server revelou outro erro: antes de Core.open,
o slot consumido ainda usa a identidade provisória da reserva. A auditoria de
recursos compartilhados esperava somente o ID da abertura e bloqueava o host.
CapacitySlotLedger.capacity_opening_for_slot agora consulta a associação exata
armazenada no Core, sem expor seu formato de ID ao Server nem liberar o slot.
Somente a recuperação posterior com prova de abertura não iniciada pode liberar
a reserva. IDs opacos de versões anteriores continuam válidos.

Três cortes de reinício foram exercitados: antes do fato no Core, depois dele e
depois do receipt no Server. O serviço automático, habilitado na segunda
inicialização da fixture, executa uma tarefa nova sem reapresentar a antiga.
Os providers são sintéticos; SQLite, journals, scheduler e controle são reais.
A primeira ampliação do teste selecionava incorretamente o turno antigo; outra
fixture introduzia tentativas manuais enquanto o serviço estava corretamente
em modo apenas limpeza. As fixtures foram corrigidas para selecionar a nova
sessão e usar o serviço automático ativado, preservando o gate de produção.

Os resultados finais e limites de qualificação estão em
startup_deadline_validation no ledger. Nenhum commit, push, instalação ou
reinício da instância do usuário foi realizado.

A campanha final aprovou 19 casos depois da extração do repositório. T16 e T17
passam a Local na matriz; os checkpoints parciais anteriores ficam preservados
como histórico. Restam 9 critérios parciais, T40 externo e a auditoria final
dos invariantes/artefatos instalados. O plano completo ainda não está concluído.

### Revogação entre aquisição e execução

A matriz de sete fronteiras para policy/grant/binding encontrou uma reserva
consumida que não era liberada quando o dispatcher recusava o envio. A recusa
agora grava prova exata de não envio e obrigação de release na mesma transação.
O serviço de admissão usa o port de capacidade fora da transação para liberar
o ticket original; apenas confirmação do Core encerra a obrigação. Não reabre
o claim nem encerra o processo de uma sessão aquecida.

Os 71 casos distintos da campanha final passaram, incluindo Connector em
processo separado, sessão aquecida, perda de respostas, provas inválidas e
rollback. O ledger preserva as falhas iniciais e as correções de fixtures.
`revocation-audit.md` mapeia as fronteiras e limitações. T23 e T26 passam a Local;
restam sete critérios parciais, T40 externo e a qualificação final do conjunto.
Nenhuma alteração foi instalada ou publicada.

### Expiração remota, FIFO e backlog após reinício

Três cenários com Connector em processo separado confirmam expiração pelo TTL
real do Core: antes da consulta, entre consulta e consumo, e com resposta perdida.
O ticket original nunca executa depois de expirado. A compensação ocorre uma vez
e a vaga física pode receber uma reserva nova; T27 passa a Local.

A campanha seguinte aprovou 44 casos de FIFO, backlog e arquitetura. O scheduler
automático não ultrapassa uma execução one-shot nem as duas chamadas anteriores
na fila, inclusive quando recriado entre rodadas. Dois ciclos de inicialização
preservam integralmente registros de resultado desconhecido e tentativas antigas,
retirando somente o aviso sem envio comprovado. T36 e T38 passam a Local.

Restam T24/T28/T29/T30 parciais, T40 externo e a auditoria final de invariantes,
locks e artefatos instalados. Os relatórios e limitações estão no ledger; nenhum
commit, push ou alteração da instância em uso foi realizado.

### Resultado nativo incerto no Connector

O teste T28 encontrou um fato OUTCOME_UNKNOWN já durável no Core que não chegava
ao Server: o Connector propagava a exceção nativa como falha da conexão inteira.
Agora a camada de serviço consulta o journal pelo port do Core e usa o projetor
público para verificar o vínculo exato antes de publicar a incerteza. Não há
novo envio, conclusão canônica presumida ou liberação física nesse caminho.

Os 45 casos distintos do Connector e o cenário com dois processos remotos
confirmam publicação sem queda da conexão, rejeição de fatos ausentes/adulterados
e ausência de reapresentação ao outro executor. T28 passa a Local.
Uma tentativa de qualificar reconexão completa após desconexão explícita excedeu
o watchdog de 25 segundos; esse ponto continua registrado para T29. O cenário
final de T28 cobre preservação da posse antes e durante a desconexão, sem
declarar que o host voltou a ficar pronto.

Estado atual: 36 critérios Local, T24/T29/T30 parciais, T40 externo, além dos
invariantes e da qualificação instalada. Alterações continuam somente locais.

### Reconexão, gerações antigas e contenção remota

A investigação da reconexão confirmou a espera deliberada pela lease já
concedida antes de encerrar os recursos desconectados. O watchdog anterior de
25 segundos não cobria esse prazo. A campanha isolada passou com lease real de
15 segundos: o Connector voltou a ready em nova geração/boot, preservando o
resultado incerto, sem outro envio ou claim. A geração anterior não restaura
observações nem posse. Os 24 casos de mensagens fora de ordem, ACK/lease antigos,
fences de agenda/claim e arquitetura passaram.

Dois casos adicionais iniciaram trabalho remoto e retiveram seu close nativo:
revogação de grant e runtime.close pela API. Após mais de 11 segundos, capacidade
e Server continuavam aguardando prova; só o close confirmado permitiu reutilizar
a vaga. O handoff conservou epoch e dono, sem compensação ou repetição.
T29 e T30 passam a Local. Permanecem T24 parcial, T40 externo e os gates finais.

`commit-boundary-audit.md` inventaria 20 fronteiras de persistência do fluxo,
com evidências e lacunas explícitas para T24. O inventário não transforma testes
parciais em validação de todos os commits. Nenhum commit, push, instalação ou
reinício da instância em uso foi realizado.

O complemento de T24 aprovou seis cortes: rollback e resposta de commit perdida
em RESERVING, RESERVED e CONSUMED. O serviço reconstruído recupera o mesmo ticket
e executa apenas uma vez, sem nova tentativa, epoch ou consumo de grant. Não foi
necessário alterar produto nesses cortes. As lacunas restantes permanecem
explícitas no inventário; T24 não foi marcado como concluído.

### Negação inicial: falhas de gravação e reinício

Os cortes da gravação da negação inicial reproduziram bloqueio do agente inteiro.
O dispatcher agora conserva o request autenticado para repetição pela recuperação
daquela sessão. Falhas repetidas não solicitam outra lease nem autorizam abertura
nativa; a prova de recusa só é publicada depois de persistida.

O reinício anterior ao commit revelou uma segunda lacuna: a reserva física já
consumida continuava ocupada, mesmo sem começar Core.open. A recuperação consulta
a admissão original por um port de aplicação e adaptador SQLite, exige proprietário
anterior cercado por geração nova e ausência de publicação, stream e receipts no
Server. O Core confirma a liberação somente do placeholder ainda não iniciado.
Depois, a recuperação existente exige histórico vazio antes de encerrar a sessão.
Não se fabrica request, receipt ou conclusão de handoff quando a negação não chegou
a ser gravada. Claim, epoch e operação originais permanecem no histórico.

A composição do serviço de capacidade é preguiçosa: recuperações sem reserva
mantêm o comportamento anterior, inclusive quando o protocolo de pool está
desabilitado. A primeira regressão detectou a dependência indevida desse protocolo;
o ajuste solicita o port somente depois de encontrar uma admissão correspondente.
Relatórios de reprodução e campanhas finais são registrados no ledger. T24 segue
parcial até completar as demais fronteiras; a instância do usuário não foi alterada.

### Commits de compensação, observações e páginas

Vinte novos cenários locais passaram sem mudança de produto. Dez cobrem
indisponibilidade antes/depois do RPC, incerteza após reserva física com resposta
perdida e compensação de ticket expirado/liberado. Cada caso distingue rollback
da perda de confirmação depois do commit real. A recusa pré-envio já confirmada
permanece terminal; trabalho incerto consulta a identidade original antes de
qualquer reserva. A compensação repetida conserva uma única reabertura no epoch1.

Seis casos adicionais cortam os commits de scan/wake/aquisição de lease,
renovação e finish/cursor da agenda. Quatro cobrem criação da tentativa e
retirement de backlog. Recriar o serviço mantém o candidato persistido, enquanto
um UUID que sofreu rollback nunca alcança o host. A conversão de backlog libera
somente a inbox que possuía, sem ACK artificial nem alteração de resultado incerto.

`criteria-recovery-commit-cuts.xml` contém dez aprovados e
`criteria-page-commit-cuts.xml` mais dez. A primeira execução dos testes de agenda
teve quatro erros na fixture (concatenação de string com alvo numérico); foi
corrigida a mensagem de injeção, sem mudar o comportamento testado. T24 continua
parcial para as demais fronteiras inventariadas, inclusive journals Core/Connector.
Nenhum commit, push, instalação ou reinício da instância em uso foi realizado.

### Commits físicos e publicações do Connector

O Core passou em 38 casos finais: 22 cortes de reserva/consumo/bind/liberação/
expiração, oito cortes de COMMIT nos gates de abertura/turno e provas de liberação,
mais oito regressões de recurso iniciado versus cancelamento. A reabertura do
ledger conserva IDs, hashes, TTL e ocupação. Um gate já commitado não se torna
uma nova autorização de execução quando a confirmação se perde.

O Connector passou em 39 casos, incluindo 16 cortes novos de reserve/bind/record/
ACK no store e com Core real/provider sintético. A publicação retoma fatos exatos
sem repetir abertura. As falhas iniciais eram expectativas/ambiente de fixture:
uma reserva expirada nunca consumida não deve bloquear turnos comuns, e o host
frio do teste precisa do diretório privado que o daemon cria na inicialização.
Não foi necessária alteração de produto nesta campanha.

Há uma lacuna distinta de liveness: a obrigação reserve/bind já persistida sem
receipt Core continua pending depois de recover_publications. O reporter impede
reconciliação enquanto essa pendência existir. Os testes aprovados atestam
preservação de identidade e ausência de replay; não comprovam recuperação
automática para ready nesse corte. T24 permanece parcial e a próxima correção
deve usar evidência positiva de não execução, preservando o fence da geração
anterior, em vez de eliminar a obrigação ou tratar ausência de receipt como prova.

### Recuperação remota antes da abertura: reprodução e fence do Core

`test_remote_preopen_publication_recovery.py` reproduziu a lacuna em dois
processos Connector descartáveis, com HTTP/WebSocket e persistência reais.
Perder a resposta do commit de reserve ou bind impede retorno a ready, embora
o provider permaneça com zero aberturas e zero envios. Os dois casos falham
intencionalmente contra o comportamento ainda incompleto; o relatório
`remote-preopen-publication.xml` registra 2 falhas em 113,63 segundos.
A falha de reserve também conserva uma obrigação pendente no shutdown.

O Core agora oferece prepare/validate/persist_r4_preopen_refusal. A associação
preserva a fonte original, a geração da sessão, o binding anterior quando
existente e a conexão de recuperação estritamente posterior. Uma intenção
separada por domínio disputa a mesma chave no Journal: se a abertura original
venceu, mesmo sem efeito iniciado, a recusa não a sobrescreve; se o fence venceu,
uma abertura tardia não pode admitir sua intenção. Interrupções entre admissão
e receipt terminal retomam a mesma associação. Nenhuma lease, posse de sessão,
liberação física ou decisão de handoff é fabricada por essa API.

`preopen-refusal.xml`: 37 aprovados em 4,61 segundos, incluindo 23 novos casos
de persistência/reabertura, disputa entre dois journals, fatos nativos existentes,
perda de resposta e escopo, mais 14 regressões de recusa por lease. O Core usa
somente a porta Journal existente; não há acesso ao SQLite na nova política.

A integração permanece pendente. O Connector deverá persistir a associação
antes do CAS, preservar o binding original para auditoria, distinguir uma
proposta de recusa de um fence efetivamente confirmado e conservar fatos
originais quando perder a disputa. Depois deverá confirmar a liberação da
capacidade exata. O Server deverá validar a conexão autenticada de recuperação,
a admissão original e a prova, fechando apenas a abertura comprovadamente
impedida. O handoff canônico não é compensado nem reexecutado por essa operação.
Os dois testes remotos continuam gates vermelhos até esse circuito e a execução
de novo trabalho serem comprovados. T24 continua parcial. Nenhuma instalação,
reinício da instância do usuário, commit ou push foi realizado.


### Auditoria T24: aviso canônico e contrato de recuperação

A recuperação de publicação pré-abertura foi integrada ao Connector e ao Server,
com fence persistido no Core, liberação física confirmada e aceite atômico.
A campanha final anterior teve 14 cenários de recuperação e 59 regressões
aprovados, incluindo ACK perdido e trabalho novo após retorno a ready.

A auditoria do artefato encontrou drift no gerador R4. A extensão negociada
nexus-preopen-refusal-v1 agora tem schema e manifesto próprios, gerados junto
com o contrato base, sem alterar os bytes do schema/manifesto R4 existente.
Core: 67 testes aprovados; Connector: 30. Wheel construído e carregado diretamente
com verificação dos recursos empacotados. O reteste integrado do Server terminou
com 14 aprovados em 147,56s; nenhuma instalação foi modificada.

Quatro novos testes de cortes nos commits de criação e desbloqueio passaram.
Rollback preserva os registros anteriores; resposta perdida conserva uma tarefa,
agenda e aviso por destinatário, sem execução nativa. A criação não dispõe de
chave idempotente pública: o teste recupera a tarefa commitada por consulta,
sem inventar deduplicação por repetir create. T24 continua parcial para as
demais fronteiras identificadas. Sem commit ou push.

A recusa de envio após consumo ganhou mais dois cortes de commit aprovados.
A prova da abertura e do turno filho nunca enviado, o estado terminal e a
obrigação de release são atômicos. A capacidade física permanece CONSUMED até
a confirmação real do Core; o claim original não é compensado. Os relatórios
finais desta etapa somam 117 casos executados (67 Core, 30 Connector, 20 Nexus),
todos com processo terminal bem-sucedido. O gerador e diff --check dos três
repositórios também passaram. Os gates restantes estão mantidos no ledger.

### Cortes de contenção e correção do journal ao reabrir

A auditoria acrescentou quatro cortes no commit da contenção após renovação
negada e dois no aceite da prova de liberação pelo Server. Os seis passaram
contra os pacotes instalados: uma nova factory recupera a obrigação e o pedido
originais; perda da confirmação do commit não provoca outro close, receipt ou
execução. No Connector, seis cortes de prepare/ACK/reconcile também passaram,
mantendo os bytes originais e a proveniência da recuperação separada do ACK.

Os quatro cortes correspondentes da recusa no journal Core expuseram um erro:
o backfill de compatibilidade criava session_claims ao reabrir journals modernos,
inclusive para recusas sem admissão nativa. A rotina agora cria e preenche a
tabela atomicamente apenas na migração de um journal que ainda não a possui.
Os claims existentes são preservados. Recusas modernas continuam sem posse de
sessão depois do reinício. A fixture antiga de migração foi ajustada para
representar o schema anterior, sem a tabela de claims.

As fontes corrigidas passaram em 90 casos de recusa/preopen/capacidade, mais
28 casos finais de claims/migração. A regressão adicional de journal teve
78 aprovados e a única falha era essa fixture antiga, depois corrigida.
O Core foi reconstruído para qualificação instalada com Nexus e Connector;
a campanha congelada anterior permanece evidência do build anterior, não do
novo. Os digests, resultados terminais e pendências constam no ledger.

## Conclusão da etapa local — 2026-10-14

A campanha final instalada terminou: Nexus 54, Core 187 e Connector 99 testes
aprovados, sem falhas/erros/skips. O runner Nexus registrou PASS, exit 0 e
changed_inputs vazio. Hashes dos wheels e bytes dos pacotes instalados foram
conferidos novamente. Ambos os consumidores exigem Core==0.0.11.

T24 foi consolidado com as 21 fronteiras e a composição transacional do claim.
T01–T39 e INV-01–INV-10 estão local_verified. O Connector local foi exercitado
em processo separado, com HTTP/WebSocket reais, reinício normal, queda abrupta,
recuperação da operação original e contenção com parada retida. Os providers
nativos são sintéticos; isso não qualifica universalmente os harnesses reais.

Por decisão explícita do usuário, T40 em outra máquina fica para um teste
conjunto posterior (deferred_by_user), sem bloquear a conclusão local. Essa
decisão não converte o teste local em comprovação de host independente.

Versões: Nexus 0.3.0, Connector 0.0.9, Core 0.0.11. Instância em uso preservada.
Trabalho pronto para revisão do usuário; nenhum commit ou push realizado.

## Complemento solicitado: terminal e scrollback — 2026-10-14

Inputs Nexus de Codex, Claude e Pi agora exibem a mensagem, identificação e
contexto expansível, sem despejar o envelope JSON. Live tail e History usam o
mesmo fluxo contínuo: últimos 500 eventos na abertura, carregamento anterior
ao rolar para cima e retenção do histórico carregado. Pausar/retomar não apaga
eventos; chegada de eventos novos preserva a posição de leitura. Foram removidos
o corte de texto em 32 mil caracteres e o viewport interno de 320px do output.

Validação: 21 testes de apresentação/cursores e dois cenários de Edge aprovados.
O navegador exercitou 607 eventos via API/SQLite reais com peer sintético,
input acima de 40 mil caracteres, scroll, concorrência com live tail, pausa,
retomada, maximização, fonte, gap, reload e rejeição de escopo adulterado.
TypeScript/Vite compilaram os assets do repositório. As qualificações de wheels
anteriores continuam vinculadas aos hashes anteriores; esta mudança não foi
reinstalada na instância em uso. Nenhum commit/push.


## 2026-10-14 — Local Pi recovery and installation revalidation

Fixed discovery provenance changes blocking automatic version observations; Pi launch now tolerates same-authority lease renewal and records pre-launch refusal as a safe failure. Recovery accepts uncertain opening receipts only with retained container-stop proof or scoped operator attestation. 45 distinct targeted checks passed. Clean wheels installed and byte-verified. The old Pi unknown opening was released through the audited recovery endpoint after verifying no Pi process; its uncertainty remains in history. Live verification: Pi/Claude/Codex READY, four Pi WARM sessions, Claude/Codex intents accepted without blockers. No commit/push/publication. Evidence and wheel hashes recorded in ledger.json.


## 2026-10-14 — Pending admission contention and unsent initial turns

A retryable writer admission timeout in queue maintenance incorrectly stopped the embedded executor. Maintenance now retries that narrow storage failure after scheduling renewals; an empty pending queue uses a read transaction. Recovery also settles initial turns that never acquired a dispatch row after their session is proven closed. 54 distinct targeted checks passed, including automatic restart recovery and first-ready/FIFO startup allocation through both pool adapters. The rebuilt Nexus wheel is installed and byte-verified. Claude/Codex are READY; the original Claude session is CLOSED, its unsent turn is resolved without a Core receipt, and the expired delivery is REJECTED without another attempt. Pi remains RECOVERING: two replacement warm opens raced shutdown before Core admission and their retained bindings need preopening recovery. This is an unresolved live limitation, not a completed recovery claim. Exact evidence and wheel digest are in ledger.json. No commit/push.


## 2026-10-14 — Shared opening recovery completed

The remaining Pi shutdown cuts are recovered through Core's existing positive preopening fence. The exact association is persisted before Core admission and survives lost replies at preparation, journal commit and Server acceptance. Native claims/receipts are never replaced by absence assumptions. A durable no-effect refusal can also precede slot reservation; absent slots are accepted only with that receipt and no process birth, while existing reservations must prove release. The path is shared by Pi, Codex and Claude. Core and Connector sources were unchanged.

Validation: 51 targeted source cases passed across recovery, authority, publication cuts, initial turns, pool FIFO/parallel warmup, normal shutdown and abrupt process exit; the rebuilt installed wheel also passed its restart regression. The earlier 31 pool adapter checks remain applicable. All three real harnesses returned the requested marker through Meta-harness and their replies reached PUBLISHED. The running instance has all three agents READY and four Pi WARM instances. No live database patch or manual stop attestation was needed. Wheel, source and installed package bytes match; the final SHA256 and evidence are recorded in shared_preopen_recovery_20261014. This closes the Pi limitation recorded in the preceding entry.


### 2026-10-14 — Claude event pump overflow during streamed output

- Production session `ses_2c8c610e19667f6a91ef218ba735514b` recorded `core.event_pump_failed` at sequence 198 with `NATIVE_EVENT_OVERFLOW`. Its 128-entry live queue filled with small text fragments before the final result. Existing scoped recovery contained that session without replaying its work or stopping sibling agents.
- Core now batches adjacent compatible Claude and Codex deltas before normalization/persistence, following the existing Pi behavior. Text is concatenated exactly; session, turn, item, block and operation boundaries remain intact. Snapshots, approvals and lifecycle events stay separate. Merged payloads are bounded to 24 KiB UTF-8, and genuine unbatchable overload still reports an explicit gap.
- Validation: 95 source tests passed, 1 skipped; all 30 new tests also passed against the installed wheel. Paused actual subscriptions processed bursts of 1,800 Unicode fragments plus terminal events in two consecutive turns. The previous plain queue fails that same burst.
- Live Nexus validation: Claude and Codex each returned all 120 requested lines (7,105 and 7,104 characters), published successfully, then answered a follow-up in the same session. Neither new session recorded a pump failure; Claude, Codex and Pi are READY.
- Installed the rebuilt development Core 0.0.11, verified all installed package files, and updated its vendored wheel in Nexus and Connector. Existing development versions remain Nexus 0.3.0 / Core 0.0.11 / Connector 0.0.9. Nexus is running on port 8202. No original user request was replayed and no database records were manually patched.


### 2026-10-14 — Codex command-output burst coverage

- Session `ses_fcdfb6ca0805666f2e699aeb80aea543` recorded `NATIVE_EVENT_OVERFLOW` at sequence 553 after 188 `item/commandExecution/outputDelta` events. The preceding fix batched text/reasoning but omitted command output. The original user operation was not replayed.
- Extended Core's bounded batching to command output, preserving exact command item, turn, thread and channel metadata. Logs remain tool activity rather than agent reply text; completion/control boundaries and explicit true-overload faults remain intact.
- Validation: 102 distinct source tests passed (one skipped); 37 passed against the installed wheel. Regressions cover paused actual subscriptions, two command bursts, quiet sibling isolation, item/channel boundaries, final reply, bridge normalization and durable SQLite replay.
- Live Meta-harness: Codex executed one read-only command with exit code 0; all 1,200 output lines (31,200 characters) were recorded in three events. Its final response and a same-session follow-up were published successfully, with zero pump faults. All three agents are READY.
- Rebuilt/installed development Core 0.0.11, updated the vendored wheel in both consumers, and restarted Nexus on port 8202. Existing development versions remain Nexus 0.3.0 / Core 0.0.11 / Connector 0.0.9. No database records were manually patched.

### 2026-10-15 — Handoff startup defaults and shared Connector workspaces

- The existing global handoff policy was enabled, but the startup scheduler gate was off and the local connection grants omitted execute_work. Startup now defaults on with explicit opt-out preserved. Connection Finish includes execute_work only for effective opt-in, retaining the operator-selected duration and action limits. Existing policy choices are not overwritten.
- Granted the three current local agents execute_work through the operator API in their existing authorization scope. Both pending broadcasts completed: Codex handled hof_f4c9281ac9de494d8f2299d533526b08 and Claude handled hof_37f41d38b5c8499e812873e11df005c8. All three local agents were READY afterward.
- Connector setup now selects an existing Nexus workspace (including one belonging to another harness) independently of its local folder. The paginated catalog enforces workspaces.list and returns no host paths. Explicit IDs, unavailable-catalog choices and saved-request resume remain supported; listing never grants execution access.
- Validation: 32 handoff/connection/policy cases, 2 workspace API/realization cases and 30 Connector wizard/onboarding cases passed. The realization test preserves the existing workspace name and other-host path while storing a separate local connection directory. Independent remote-host testing remains for the user's joint test.
- Rebuilt development Nexus 0.3.0 and Connector 0.0.9; Core 0.0.11 is unchanged. Package hashes are recorded in the ledger.

### 2026-10-15 — Promotion validation

- Opened feature-to-develop PRs Core #40, Connector #51 and Nexus #58 for the authorized develop-to-main promotion sequence. Full CI remains a merge prerequisite.
- Core's clean-checkout CI exposed extension manifests generated from Windows CRLF resources while Git stored LF, and missing LF attributes on the generated preopen extension. Canonicalized extension hashes and pinned contract JSON to LF without changing protocol semantics or disabling integrity checks. The new wheel's nine manifest-pinned resources match committed Git bytes.
- Updated the Core 0.0.11 API/version documentation. Targeted validation passed 108 contract cases and all three public documentation cases. Both consumers now use the same corrected Core wheel, SHA-256 c931685f84d1be1af8a09bb373a8e7a1fb5c2b78dcc7bbb4f45e5593b054668a.
- Connector CI exposed legacy test fixtures bypassing CoreRuntimeHost initialization and an obsolete blanket ban on the MCP SDK now owned by Core for presets. The correction uses the real host constructor and retains checks for no direct Connector MCP dependency and no Nexus Server dependency.
