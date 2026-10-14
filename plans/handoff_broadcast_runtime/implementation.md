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
