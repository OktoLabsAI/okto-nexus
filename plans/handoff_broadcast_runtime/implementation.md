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
