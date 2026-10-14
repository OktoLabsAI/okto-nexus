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
  boot do Core. Repetir a tentativa não altera esse vínculo nem renova seu prazo.
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

## Próximas integrações obrigatórias

1. Reserva técnica durável no Core integrada ao gate normal de turno e ao
   ledger físico de slots; transferência, liberação comprovada e recuperação.
2. Adaptadores embedded/Connector sobre a mesma porta, com negociação, journal
   de tentativas, observação por mudança e fencing na reconexão.
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
