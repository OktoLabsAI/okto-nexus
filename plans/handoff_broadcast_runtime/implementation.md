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
