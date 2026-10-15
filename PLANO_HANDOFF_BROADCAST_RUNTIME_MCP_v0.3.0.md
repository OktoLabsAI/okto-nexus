# Okto Nexus — handoff broadcast com claim determinístico por disponibilidade

## 0. Base de implementação e alcance da análise

Plano de evolução, não relatório de implementação concluída. A análise foi feita por leitura estática de código e de testes diretamente no GitHub. Não foram executados testes nem alterados os repositórios. Os símbolos e tabelas explicitamente marcados como **propostos** ainda precisam ser implementados.

| Componente | Branch examinada | Commit de referência | Versão declarada |
|---|---|---|---|
| Nexus | `feature/v0.3.0` | `1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9` | `0.3.0` |
| Connector Core | `feature/v0.0.10` | `109e7fb17d7f777cee8b33f76b962f750ba14c73` | `0.0.10` |
| Connector | `feature/v0.0.8` | `eea0efb8260ca5456658ceab182b6ca0081ed540` | `0.0.8` |

Nexus e Connector fixam `okto-nexus-connector-core==0.0.10`. O Core dessa base declara `rfc8785==0.1.4`, `jsonschema==4.26.0` e `mcp>=1.30,<2`. O Connector utiliza `websockets>=15,<18` e `httpx>=0.27,<1`. Não confundir essas branches de desenvolvimento com releases publicadas ou com qualificação operacional conjunta. Fontes: [S01–S03].

## 1. Decisão de arquitetura

**Manter um único handoff e um único mecanismo canônico de claim no Server. Acrescentar um consumidor determinístico de handoffs para agentes gerenciados por runtime, que só pode disputar depois de reservar capacidade operacional para o contexto exato do trabalho.**

O consumidor MCP permanece explícito: observa o aviso ou consulta os handoffs disponíveis, tenta `handoff_claim` e executa se vencer. O consumidor runtime consulta disponibilidade, reserva capacidade e usa o mesmo caso de uso canônico. Somente depois da confirmação do claim o runtime recebe a execução `handoff_execute`.

Disponibilidade não é uma propriedade global booleana do agente. É uma decisão contextual:

`disponível(agente, executor, binding, workspace, remetente, origem_de_sessão, política, instante)`.

Nenhum modelo participa de descobrir capacidade, competir, selecionar um vencedor ou informar que perdeu a disputa.

### 1.1 Escopo obrigatório

A mudança de consumo automático é aplicada a handoffs com `target.strategy == "broadcast"`. Usar os predicados atuais de elegibilidade, visibilidade, permissões e audiência do criador. Não inventar campos de capability fora da gramática existente.

A arquitetura deve admitir extensão futura aos seletores competitivos de capability, role, tags e mixed, mas essa generalização não é autorização para alterar silenciosamente o comportamento de todos os targets nesta entrega. `direct_with_fallback` requer testes próprios das duas fases antes de aderir ao novo consumo.

Mensagens broadcast comuns continuam podendo produzir várias respostas. Mensagens diretas e handoffs direcionados conservam o roteamento, o isolamento e a possibilidade atual de espera. `visibility=public` não transforma um target direto em handoff competitivo.

Ficam fora deste plano: validação da veracidade das capabilities declaradas pelo operador, seleção pela qualidade do modelo, fairness obrigatória entre transportes e uma nova infraestrutura externa de filas.

### 1.2 Invariantes

| ID | Regra |
|---|---|
| INV-01 | A posse é definida pelo claim canônico; nenhuma tabela de agenda, reserva ou inbox estabelece outro dono. |
| INV-02 | O runtime não invoca o modelo por um aviso competitivo. Apenas o vencedor recebe a execução do trabalho. |
| INV-03 | Falta de capacidade deixa o handoff `OPEN`; espaço em fila não equivale a disponibilidade. |
| INV-04 | MCP-only não precisa publicar ocupação para continuar elegível. |
| INV-05 | Um agente tem uma identidade lógica mesmo com várias sessões, executores ou acesso simultâneo por MCP. |
| INV-06 | A reserva não concede permissão de claim, de execução ou de acesso ao payload. |
| INV-07 | As validações atuais de target, audiência, dependências, grants, revisões e claim epoch permanecem obrigatórias. |
| INV-08 | Evento, heartbeat, ACK de transporte, processo vivo e final de texto do modelo não significam conclusão canônica do handoff. |
| INV-09 | Efeito incerto nunca é convertido em falha sem efeito para autorizar repetição automática. |
| INV-10 | Mensagens normais e claims explícitos não perdem sua semântica de fila por causa desta feature. |

## 2. O que aproveitar do código atual

### 2.1 Claim e execução gerenciada já se encontram na mesma transação

`HandoffService.handoff_claim` executa as validações de domínio e chama `SqliteHandoffRepo.claim`, cujo UPDATE condicional exige `status=OPEN` e incrementa `claim_epoch`. Quando são informados os parâmetros de execução gerenciada, `RuntimeWorkService.enqueue` registra o binding e a execução dentro da mesma Unit of Work. A notificação ao dispatcher ocorre depois; é apenas uma otimização de latência. [S04–S06]

Portanto, não implementar outro CAS, um lock de posse independente, um claim no Connector ou uma disputa no Core. Refatorar a composição transacional do caso de uso quando necessário, sem copiar suas regras.

O teste `test_canonical_competitive_work.py` já descreve uma disputa de três agentes via REST/MCP com execução gerenciada: um vencedor, um binding, uma entrega, um consumo de grant e uma abertura/envio nativo. Esse é um teste a preservar e ampliar, não uma evidência de que a nova seleção automática por disponibilidade esteja pronta. [S07]

### 2.2 O caminho de notificação ainda explica o ruído relatado

`runtime_handoff_notifications.py` encaminha notificações para `runtime_pending_deliveries`, e `RuntimeDeliveryPlanner` pode tratá-las como conversa. O teste `test_handoff_creation_notifies_runtime_without_claiming` cobre explicitamente `direct` e `broadcast`: espera envio nativo contendo a orientação `handoff_claim`, enquanto o handoff permanece `OPEN` e ainda não existe `runtime_handoff_bindings`. [S08–S10]

A correção deve mudar a classificação e o consumo desse aviso competitivo antes da entrada no harness. Filtrar a frase “não consegui claim” depois da geração não atende ao requisito.

### 2.3 One-shot já possui pool; o problema é a modalidade de admissão

`one_shot_capacity.py` é uma fachada sobre `ResourcePool`. O pool já distingue instâncias `STARTING`, `WARM`, `CLAIMED`, `RUNNING` e `CLOSING`, possui fila, controle de capacidade e descarte confirmado. `one_shot_runtime.py` integra esse pool à admissão canônica. [S11–S13]

O teste `test_managed_handoffs_share_capacity_and_keep_distinct_sessions` aceita um segundo claim enquanto existe uma chamada one-shot `QUEUED`. Esse comportamento é compatível com pedidos explícitos, mas não com a seleção automática do primeiro disponível. [S14]

Acrescentar uma modalidade interna de admissão imediata, sem apagar a modalidade atual que permite fila.

### 2.4 Há sinais técnicos, mas nenhum deles isolado resolve a disponibilidade requerida

`CandidateAvailability` do Core é avaliação de instalação, plataforma, qualificação e preparação. `READY_FOR_RUNTIME` não quer dizer que uma sessão esteja ociosa. `RuntimeSnapshot` já contém `turn_state`, `process_state`, `ownership`, `lease_state` e gerações. `SQLiteOwnedSlotLedger` protege slots físicos compartilhados entre instâncias do Core. [S15–S17]

`execution_capacity.py` limita operações pendentes e filas de despacho. `agent_runtime_administration.py` oferece uma visão administrativa das instâncias. Ambos ajudam a compor ou apresentar o estado, mas não são, por si só, uma reserva de execução. [S18–S19]

## 3. Definição operacional de disponibilidade

### 3.1 Etapas distintas

A avaliação deve retornar separadamente:

1. **Elegibilidade de domínio:** target, capabilities declaradas, audiência, workspace, permissões e dependências.
2. **Autorização de automação:** opt-in para auto-claim competitivo, política vigente e grant aplicável.
3. **Prontidão técnica:** executor conectado/reconciliado, instalação e binding atuais, autoridade válida.
4. **Capacidade imediata:** sessão relevante utilizável ou vaga para abri-la; capacidade de agente/host; nenhuma execução ou reserva anterior bloqueando a mesma unidade.

Falhar numa etapa não autoriza pular outra. Um agente ocupado pode ser elegível, mas indisponível agora; um MCP-only pode ser elegível com ocupação desconhecida.

### 3.2 Chave de afinidade

A chave deve usar as mesmas regras de `select_delivery_session`, incluindo escopo de executor, binding, workspace e configuração. A avaliação e o despacho não podem calcular chaves diferentes. [S20]

| Política | Unidade avaliada | Condição para disputar automaticamente |
|---|---|---|
| `shared` | Sessão compartilhada no escopo de execução aplicável | Livre de turno ativo, reserva conflitante e trabalho anterior bloqueante; ou abertura de sessão permitida. |
| `per_sender` | Sessão daquele remetente | A sessão do remetente está livre ou pode ser criada. Sessões de outros remetentes não bloqueiam por si só. |
| `per_sender_session` | Sessão daquele remetente e daquela origem autenticada | A afinidade exata está livre ou pode ser criada. Outras origens não bloqueiam por si só. |
| `one_shot` | Uma vaga de chamada no pool do agente e no host escolhido | Instância warm utilizável ou vaga reservável para abertura; não apenas posição livre na fila. |

Em todos os modos, o limite do host e as reservas já existentes continuam valendo. Não abrir outra sessão em modo shared/per_sender apenas para contornar uma sessão ocupada; isso violaria o isolamento escolhido pelo usuário.

**Exemplo:** Claude/s1 e Claude/s2 têm trabalho ativo no Codex. Um handoff de Claude/s3 pode disputar no Codex em `per_sender_session`, desde que a afinidade s3 e os limites de abertura estejam disponíveis. Outro handoff originado de Claude/s1 não pode usar uma sessão inventada para escapar da ocupação de s1.

### 3.3 Ocupação efetiva

Uma sessão é indisponível para uma nova aquisição competitiva quando existe turno produtivo em curso, trabalho admitido ainda não despachado para a mesma afinidade, reserva de próximo turno, abertura/reconciliação inconclusiva, encerramento em andamento ou solicitação interativa que mantém o trabalho ativo.

O término de uma chamada de transporte ou a liberação de um semaphore de envio não prova que o modelo terminou. A liberação da unidade deve se basear no ciclo real da operação e nos eventos/receipts correlacionados.

A disponibilidade não deve ser deduzida exclusivamente do status do handoff. Por exemplo, um trabalho entregue para verificação pode não ocupar mais um turno, enquanto uma chamada a `handoff_complete` feita antes do término nativo não libera imediatamente a sessão física. Se o turno termina sem uma decisão canônica obrigatória, registrar trabalho pendente de decisão; não criar uma conclusão nem reofertar automaticamente. Tratar a afinidade ainda vinculada de forma conservadora até sua reconciliação.

### 3.4 Semântica one-shot

A modalidade nova, proposta como `immediate_only`, deve:

- Consumir uma instância warm compatível sem descontar duas vezes o mesmo slot físico.
- Permitir reserva para abertura fria se há capacidade efetiva agora, com deadline de startup limitado. “Imediato” significa sem esperar atrás de outra tarefa, não latência zero.
- Recusar a disputa quando só seria possível enfileirar; manter o handoff aberto para outro agente.
- Não ultrapassar chamadas anteriores que já têm direito à capacidade pelo pool atual.
- Considerar `STARTING` e `CLOSING` ocupadas conforme seu estado real; timeout de conversa não comprova liberação do processo.
- Respeitar o teto físico mesmo quando `max_parallel=0` remove o teto específico do pool.

Não criar N chamadas one-shot, uma para cada candidato, para depois cancelar os perdedores. Criar apenas reservas limitadas e sem execução; a chamada produtiva pertence ao vencedor.

## 4. Proveniência da sessão do criador

A afinidade do trabalho usa o **criador do handoff e sua sessão de origem**, não a sessão do dispatcher nem a sessão do agente que assume o trabalho.

O módulo `message_session_origin.py` já produz chaves namespaced para origem runtime e MCP e utiliza origem vazia quando não há prova. O caminho de execução gerenciada cria uma mensagem sintética; o plano deve garantir que a proveniência original chegue a essa mensagem e à seleção de sessão. [S06, S21]

Adicionar persistência de origem do handoff, por exemplo uma tabela proposta `execution_handoff_origins`, com versão, chave opaca de origem verificada e contexto mínimo de auditoria. Reutilizar a validação existente de principal runtime ou sessão MCP. Nunca persistir `session_secret` nem aceitar um ID arbitrário como prova.

Aplicar o mesmo procedimento a criação via MCP, REST/operator e execução de aprovação. Replay de aprovação preserva a proveniência anteriormente verificada sem renovar autoridade a partir de uma credencial antiga.

Handoffs históricos e mensagens do operador sem sessão comprovada usam o fallback explícito já adotado para ausência de origem. Não fabricar uma sessão por aba do navegador, assunto, timestamp ou nome do agente. A UI deve mostrar quando o contexto usa esse fallback.

## 5. Contrato reutilizável de capacidade — proposto

### 5.1 Responsabilidades

| Componente | Responsabilidade |
|---|---|
| Nexus | Elegibilidade, política, afinidade lógica, concessões, reserva lógica de admissão, claim canônico, coordenação de despacho e resultados. |
| Core | Observação técnica de turnos e recursos; reserva atômica local da unidade de execução; consumo/liberação segura; fencing e journal. |
| Connector | Expor o contrato do Core ao Server pelo canal autenticado existente, manter correlação e reconciliação; não selecionar vencedor de handoff. |

O serviço de disponibilidade consumido pelo handoff deve pertencer ao gerenciamento de runtime do Nexus. Não colocar conhecimento de remetentes, inboxes, targets ou regras de handoff dentro do Core.

### 5.2 Portas propostas

Definir uma fachada de aplicação `RuntimeAvailabilityService` e um contrato técnico compartilhado, com operações equivalentes a:

- `assess(request)`: consulta sem efeito; resultado não garante reserva.
- `try_reserve(request, attempt_id)`: reserva a unidade, sem abrir processo de trabalho nem executar modelo.
- `get_reservation(reservation_id)`: reconciliação após resposta perdida.
- `consume(reservation_id, admitted_operation)`: transferência da reserva à operação canônica correspondente, uma vez.
- `release(reservation_id, reason)`: liberação idempotente quando permitida pelo estado.

Os nomes são propostas, não APIs encontradas prontas no código. Antes de criar implementações, revisar os métodos públicos existentes de runtime/journal/ledger e estendê-los onde já há a responsabilidade correta.

### 5.3 Dados mínimos

A requisição inclui escopo `server_id`, `executor_id`, `agent_id`, `binding_id`, `workspace_id`, tipo de unidade (`next_turn` ou `new_session`), sessão existente ou identidade proposta, chave opaca de afinidade, revisões de configuração/autorização e identidade estável da tentativa.

O resultado contém versão de contrato, decisão, motivo estável, identificador opaco de reserva, gerações do executor/owner, revisão de capacidade, prazo aplicável e vínculo imutável ao pedido. Exemplos de motivos: `BUSY_AFFINITY`, `POOL_FULL`, `HOST_FULL`, `EARLIER_WORK_PENDING`, `RECOVERING`, `STALE_OBSERVATION`, `NOT_AUTHORIZED`, `CAPACITY_PROTOCOL_UNSUPPORTED`.

Uma reserva não deve transportar o payload privado do handoff nem credenciais. Não comparar relógios monotônicos de máquinas diferentes. O host impõe seu deadline local; o Server usa validade de observação e margens próprias, mas o consumo da reserva continua sendo validado pelo host.

### 5.4 Exclusão real, não apenas leitura seguida de claim

Todas as admissões produtivas que competem pela mesma unidade devem respeitar a reserva: mensagem normal, handoff explícito, broadcast automático e ação manual do operador. A mensagem normal conserva seu enfileiramento, mas não pode ocupar uma unidade já reservada para outro trabalho.

A reserva de `next_turn` deve competir com o mesmo gate de admissão do turno normal. A reserva de `new_session` deve estender/transferir a capacidade protegida pelo ledger de slots, não manter um contador paralelo incapaz de impedir uma abertura por outro processo.

Distinguir reserva lógica do Server e posse física do Core. Elas são necessárias em autoridades diferentes; não devem contar o mesmo recurso duas vezes dentro da mesma autoridade. Conversões warm→claimed→running e reserved→opened precisam manter essa contabilidade.

## 6. Fluxo de claim automático

### 6.1 Descoberta e agenda

Persistir o handoff e o aviso MCP antes de acionar a disputa automática. Não conceder o claim runtime dentro da transação de criação, tornando-o invisível aos demais consumidores até depois da escolha.

Criar um índice durável de trabalho agendável, proposto como `handoff_runtime_schedule`, e histórico de tentativas. Isso não é outra fila de posse: o handoff canônico continua sendo a única tarefa. Um registro por handoff e geração relevante é suficiente; evitar materializar trabalho produtivo por destinatário.

Eventos de criação, desbloqueio, liberação de capacidade, reconexão reconciliada e alteração de política acordam o scheduler. Fazer também varredura limitada para recuperação de eventos perdidos. Processar páginas, coalescer despertares e aplicar backoff por motivo; não criar loops de polling por agente/handoff.

### 6.2 Disputa

Usar os predicados de `handoff_list_available` como fonte compartilhada de elegibilidade, sem depender de consumir a inbox do agente. O scheduler monta candidatos lógicos, um por agente, e usa o resolvedor atual para escolher um binding autorizado e não ambíguo.

Agentes com vinte slots não ganham vinte identidades de concorrência pelo mesmo handoff. Seus slots permitem assumir trabalhos distintos; não devem multiplicar entradas na disputa de um só trabalho.

Tentar reservas com concorrência limitada e ordem de varredura rotativa/estável para evitar preferência permanente pelo primeiro ID. Isso organiza o trabalho do scheduler, não cria uma garantia de distribuição proporcional. O vencedor é quem confirma primeiro o claim canônico válido.

### 6.3 Transação e despacho

Fluxo normativo:

1. Registrar tentativa durável e obter a pré-avaliação do runtime.
2. Solicitar a reserva técnica ao host **fora da transação SQLite do Server**. Uma tentativa/resposta perdida é consultada pela identidade original.
3. Abrir uma Unit of Work curta no Server. Revalidar status, target, audiência, dependências, política, grant, binding, revisões, afinidade e vínculo da reserva.
4. Compor na mesma UoW a reserva lógica, o claim canônico existente, `RuntimeWorkService.enqueue`, o registro da origem da mensagem sintética e a admissão imediata da execução.
5. Confirmar a transação. Qualquer conflito ou capacidade insuficiente deve desfazer claim e registros produtivos dessa tentativa.
6. Despachar a operação persistida, que consome exatamente a reserva correspondente. O Core revalida autoridade e gerações antes de qualquer efeito.
7. Registrar resultados, liberar as reservas conforme o ciclo real e acordar outros handoffs que aguardavam capacidade.

O caminho deve aceitar uma Unit of Work fornecida ou expor um núcleo transacional compartilhado do caso de uso. Não chamar o método público em uma segunda transação e gravar a reserva somente depois.

A admissão imediata não pode aceitar o retorno “nenhuma operação pronta porque entrou em QUEUED” como sucesso competitivo. Uma abertura fria reservada é distinta: há uma obrigação durável de startup, com capacidade efetivamente vinculada, não espera por outra chamada terminar.

Se o MCP vence enquanto o runtime obtém a reserva, o runtime perde o CAS, libera a reserva com obrigação durável de limpeza e encerra silenciosamente. Não cria mensagem de derrota, não inicia harness e não consome o orçamento de execução do handoff.

### 6.4 Principal e autorização

Adicionar um contexto interno de automação vinculado ao agente representado, à política de auto-claim e ao grant vigente. Não simular uma chamada MCP com segredo inventado, nem utilizar privilégio irrestrito de `operator` para assumir trabalho por qualquer agente.

O ator registrado, o criador do handoff, o agente executor e o operador que autorizou a automação são papéis distintos. Preservar essa distinção em auditoria e em idempotência.

O opt-in de auto-claim competitivo deve ser independente de `response_policy=conversation`: um agente pode estar autorizado a executar handoffs sem ser um respondedor conversacional. A autorização de execução também deve limitar o conjunto de ferramentas e o claim epoch fornecidos à sessão vencedora.

## 7. Consumo, notificações e conclusão

Adicionar classificação estrutural confiável ao aviso competitivo, estabelecida pelo Server, nunca inferida por regex sobre assunto/corpo. Manter o aviso lógico de inbox e a observabilidade para MCP; encaminhar seu tratamento automático ao scheduler, não ao pipeline conversacional.

Antes do claim, candidatos recebem somente o que já podem observar pelas regras de visibilidade. Depois do claim, o vencedor recebe o envelope existente `handoff_execute`, payload, `handoff_id`, `claim_epoch`, proveniência e contrato de conclusão.

As capacidades MCP/native da sessão gerenciada devem reconhecer que o claim já foi adquirido. Aproveitar o tratamento atual de claim existente e a vinculação à sessão; uma chamada redundante não pode gerar outro dispatch. O mesmo agente usando MCP e runtime não pode abrir duas execuções do mesmo epoch.

Resultado final do harness é evidência de execução, não conclusão automática de negócio. Manter `handoff_complete`/`handoff_reject` autenticados ou o contrato explicitamente admitido `structured_result_v1`. Preservar critérios de aceite e `VERIFYING`. [S06, S22]

Os avisos originais também precisam de ciclo de vida: não apagar o histórico, não produzir ACK fingindo ser um consumidor MCP e não deixar um aviso já superado reativar a execução após reinício. Para a projeção de controle runtime, marcar/derivar resolução pelo estado canônico; para o MCP, preservar as regras de entrega e reconhecimento aplicáveis. O aviso não é a tarefa e sua leitura não é um claim.

Publicar ao criador os desfechos canônicos previstos. Não duplicar uma resposta por relay conversacional e outra pelo canal de conclusão. Um candidato ocupado ou perdedor produz apenas telemetria. Uma falha real do vencedor continua visível; silêncio dos perdedores não pode esconder perda de trabalho.

## 8. Falhas, prazos e recuperação

Não há uma transação ACID única entre SQLite do Server e o journal remoto. A segurança vem da composição transacional local, da reserva limitada, das identidades estáveis, de fencing e de obrigações duráveis de reconciliação.

Estados propostos de reserva: `HELD`, `CONSUMED`, `RELEASE_PENDING`, `RELEASED`, `EXPIRED_UNCONSUMED`. Estado incerto é representado explicitamente; não é sinônimo de expiração segura.

Estados propostos da tentativa de agenda: `WAITING`, `RESERVING`, `RESERVED`, `CLAIM_COMMITTED`, `DISPATCHED`, `SETTLED`, com saídas `NOT_AVAILABLE`, `LOST`, `CANCELLED_NO_EFFECT` e `NEEDS_RECONCILIATION`. Esses estados não substituem os estados canônicos do handoff.

| Corte/falha | Regra obrigatória |
|---|---|
| Queda antes de obter a reserva | Handoff continua aberto; repetir/consultar a mesma tentativa. |
| Reserva concedida, resposta perdida | Consultar seu ID/attempt_id; não pedir outra reserva sem resolver a primeira. |
| Reserva existente, MCP ganhou | Persistir e executar a liberação; nenhuma execução runtime do trabalho. |
| Claim confirmado, resposta do Server perdida | Consultar operação e idempotency key originais; não criar outro claim. |
| Reserva expirou antes do consumo | Host recusa efeito. Server confirma a recusa sem efeito antes de compensar ou readmitir. |
| Queda depois de possível envio nativo | Preservar resultado incerto, claim/epoch e obrigações; não despachar para outro agente. |
| Processo parou após executar parte do trabalho | Capacidade física pode ser liberada com prova; efeitos anteriores não são apagados. Reexecução requer reconciliação ou decisão explícita. |
| Cancelamento/revogação antes de efeito | Bloquear o consumo e limpar reservas de forma idempotente. |
| Cancelamento/revogação durante execução | Solicitar contenção; manter capacidade ocupada até a confirmação aplicável. |
| Core reconectou com nova geração | Invalidar observações antigas; reconciliar reservas/efeitos antes de publicar disponibilidade. |
| Handoff entrou em verificação | Não reabrir como novo broadcast; preservar o contrato de verificação e dono do retrabalho. |

Apenas reservas **comprovadamente não consumidas** podem expirar e devolver capacidade por prazo. Recursos com possível execução continuam sujeitos à prova de encerramento e às obrigações do journal. A duração da reserva, a lease do handoff, a lease de execução e os deadlines do pool são controles diferentes.

O código já tem testes de recuperação revisada que preservam histórico, usam claim epochs e exigem reconhecimento explícito do risco de duplicação em resultados incertos. Manter essa fronteira. [S23]

## 9. Convivência com MCP e previsibilidade

O primeiro claim válido continua vencendo, independentemente de vir de MCP ou do consumidor automático. A garantia de não acionar perdedores e não gerar respostas de derrota se aplica ao caminho automático de runtime. Um cliente MCP externo ainda controla o próprio raciocínio e pode decidir enviar uma mensagem; o Server não deve gerar essa resposta por ele, e a documentação deve orientar que perder o claim é um resultado normal, não uma falha a reportar ao criador. A capacidade desconhecida de um MCP-only não é registrada como zero nem usada para removê-lo da audiência.

Um runtime pode ser mais rápido que um agente que verifica a inbox a cada minuto. Esse plano garante a mesma regra de posse, **não a mesma probabilidade de vencer**. Não é possível prometer ausência de starvation para qualquer consumidor arbitrariamente lento mantendo exatamente “primeiro claim vence”.

Evitar vantagem estrutural desnecessária: publicar antes de disputar, não retirar avisos MCP porque existem runtimes, não aguardar todos os runtimes falharem para oferecer o handoff ao MCP e não favorecer permanentemente a ordem dos IDs no scheduler.

Uma política futura de janela inicial para MCP ou seleção por rodízio pode oferecer mais equilíbrio, mas muda a latência e/ou a semântica. Não é dependência desta correção e não deve ser introduzida implicitamente.

## 10. Alterações por repositório

### 10.1 Nexus Server

| Área | Arquivos existentes de referência | Entrega |
|---|---|---|
| Domínio/claim | `application/handoff.py`, `adapters/outbound/sqlite/handoff_repo.py`, `application/runtime_work.py` | Composição com reserva na mesma UoW; preservar CAS, grants, epochs e completion. |
| Classificação/consumo | `runtime_handoff_notifications.py`, `runtime_delivery.py` | Aviso competitivo deixa de abrir conversa; mensagens e handoffs diretos mantêm caminho atual. |
| Afinidade | `execution_domain_delivery.py`, `message_session_origin.py` | Origem do handoff persistida e propagada; uma regra de chave para consulta/reserva/despacho. |
| Capacidade | `resource_pool.py`, `one_shot_capacity.py`, `one_shot_runtime.py`, `execution_capacity.py` | Admissão imediata e contabilidade compartilhada; não confundir fila, turno e slot físico. |
| Autorização | `runtime_actor_authority.py`, `runtime_policy.py`, composição de grants | Principal de automação limitado, opt-in e revalidação; sem credencial permanente nova por scheduler. |
| Hosts/despacho | `bootstrap/embedded_dispatch.py`, `application/execution_dispatch.py` e portas do host | Consumir reserva no caminho produtivo comum, sem I/O sob UoW. |
| Operação/UI | `agent_runtime_administration.py`, visões de execução e tela correspondente | Mostrar motivo de indisponibilidade e tentativa; modelo de leitura não decide posse. |
| Persistência | Nova migração após a última presente ao implementar | Origem, agenda, vínculo de reserva, deduplicação e obrigações; não renumerar/reescrever migrações publicadas. |

Novos módulos propostos: `runtime_availability.py`, `handoff_runtime_scheduler.py`, `handoff_runtime_attempts.py` e porta/adaptadores de reserva. Os nomes podem ser ajustados à organização vigente, mantendo responsabilidades separadas.

### 10.2 Connector Core

Estender as APIs públicas em torno de `runtime.py`, `models.py`, `ports.py` e `slot_ledger.py`, evitando manipulação de `_sessions` pelos consumidores.

Fornecer observação contextual técnica e reserva de próximo turno/abertura. Reutilizar o journal e o ledger para identidade, exclusão e recuperação. `one_shot.py` continua contrato de política, não scheduler de negócio. `availability.py` continua descrevendo instalações; não mudar silenciosamente o significado de `READY_FOR_RUNTIME`.

Publicar um contrato negociável para capacidade/reservas, com validação estrita, testes e fixtures. Se houver alteração de frames ou semântica NXL, atualizar a revisão/manifesto conforme a disciplina do projeto; não modificar um schema imutável mantendo a mesma identificação. Não colocar target/capability matching de agentes ou autoridade de handoff no Core.

### 10.3 Connector

Integrar a publicação e as operações de reserva no owner existente, especialmente `services/r4_execution.py` e a composição de Core/estado/publicação/reconciliação. Esse owner já recebe operações admitidas pelo Server e as traduz por APIs públicas do Core, sem criar outro intent canônico. [S24]

Publicar ocupação por mudança de estado e renovar a validade de forma limitada. A perda da conexão torna a observação obsoleta; reconectar não declara automaticamente IDLE. Manter controle de cancelamento/fechamento disponível mesmo com saturação produtiva.

Uma requisição de reserva não inicia a CLI do provider. A CLI do Connector pode mostrar disponibilidade, mas fechar a CLI não cancela produtores admitidos. Segredos e caminhos locais não devem ser publicados como parte do contrato de capacidade.

Connector antigo sem suporte declarado fica fora do **auto-claim competitivo**, com diagnóstico explícito. Não perder outros modos de consumo existentes e não usar a invocação do LLM como fallback para descobrir disponibilidade.

## 11. Plano de execução e dependências

| Etapa | Entrega e responsabilidade | Dependência / gate de saída |
|---|---|---|
| H0 — Caracterização | Nexus: separar testes atuais de broadcast/direto, registrar tuple e comportamento de fila explícita. | Evidência do problema sem mudar os invariantes já corretos. |
| H1 — Contratos | Core + Nexus: chave de contexto, motivos, reserva/consumo/liberação, principal e estado de tentativa. | Contrato aceito pelos consumidores e testes de validação. |
| H2 — Reserva real | Core: próximo turno, abertura, ledger e recuperação; Nexus: reserva lógica e `immediate_only`. | Corridas por última vaga e mensagem concorrente não excedem capacidade. |
| H3 — Host local/remoto | Server embedded + Connector: implementar a mesma porta, negociar contrato, publicar estado, consumir reserva. | Paridade de comportamento e teste de resposta perdida/reconexão. |
| H4 — Claim automático | Nexus: agenda durável, bypass do aviso conversacional, composição com claim/RuntimeWork, proveniência e grants. | Um vencedor, perdedores sem LLM; MCP e chamadas explícitas preservados. |
| H5 — Ciclo completo | Nexus + Core + Connector: completion, cancelamento, verificação, recuperação e limpeza. | Falhas não geram duplicação nem liberação fictícia de capacidade. |
| H6 — Operação/release | UI/docs, migração, teste misto e campanha remota, pins/lockfiles/artefatos. | Evidência reproduzível do tuple final e política explícita de ativação. |

H1 deve ser estabilizada antes de agentes executores implementarem contratos diferentes em paralelo. Depois, Core e adaptações dos consumidores podem progredir em paralelo contra fixtures acordadas. H4 não deve ser habilitada até H2/H3 impedirem de fato que outro ingresso roube a unidade reservada.

Não estimar o tamanho da entrega apenas pela mudança do handler de notificações: a exclusão e a recuperação são o núcleo da garantia.

## 12. Matriz mínima de testes e aceite

| ID | Cenário | Resultado obrigatório |
|---|---|---|
| T01 | 100 candidatos runtime para um broadcast | Um claim vencedor; nenhuma invocação de modelo causada por esse aviso nos perdedores. |
| T02 | MCP vence durante reserva runtime | Nenhum dispatch runtime do handoff; todas as reservas perdedoras reconciliadas. |
| T03 | Runtime vence antes do claim MCP | Erro de claim esperado ao MCP, sem nova execução; mesmo estado canônico. |
| T04 | Todos runtimes ocupados | Handoff permanece OPEN e consultável por MCP; nenhuma chamada produtiva enfileirada por candidato. |
| T05 | Capacidade liberada sem nova mensagem | Agenda reavalia automaticamente e assume trabalho pendente elegível. |
| T06 | Evento de capacidade perdido | Varredura limitada recupera, sem duplicar tentativa produtiva. |
| T07 | `shared` ocupado | Sem nova sessão para contornar o bloqueio. |
| T08 | `per_sender`, mesmo sender ocupado | Candidato não assume; mensagem direta continua no fluxo/ordem normal. |
| T09 | `per_sender`, outro sender | Pode abrir/reutilizar afinidade distinta respeitando teto físico. |
| T10 | `per_sender_session`, mesma origem | Sem concorrência na afinidade ocupada. |
| T11 | Claude/s3 enquanto s1/s2 ocupadas | Codex elegível se há capacidade para s3. |
| T12 | Origem ausente ou histórica | Fallback explícito; não fabricar sessões novas para aparentar capacidade. |
| T13 | Origem falsificada | Nenhuma afinidade privilegiada, acesso cruzado ou escape de limite. |
| T14 | One-shot no limite, fila com espaço | Não ganhar claim automático; claim explícito ainda pode usar fila. |
| T15 | Instância warm compatível | Consumida sem slot contado duas vezes. |
| T16 | Abertura fria com vaga | Reserva sem provider antes do claim; startup limitado depois de vencer. |
| T17 | Instância CLOSING ou parada incerta | Não liberar slot antecipadamente. |
| T18 | Max_parallel zero, host cheio | Auto-claim indisponível; zero não é capacidade física infinita. |
| T19 | Duas tarefas disputam a última vaga | Apenas uma reserva efetiva; a outra tarefa permanece disponível para outros. |
| T20 | Mensagem direta chega entre assess/reserve/claim | Não rouba a reserva; preserva ordenação e enfileiramento da mensagem. |
| T21 | Mesmo agente com MCP e runtime | Um dono lógico e uma execução para o claim epoch; sem adoção silenciosa de claim alheio. |
| T22 | Vários executores do mesmo agente | Resolver binding sem ambiguidade; não multiplicar identidades concorrentes. |
| T23 | Policy/grant/binding revogado entre passos | Recusa e compensação seguras; nenhum efeito sob autoridade antiga. |
| T24 | Falha antes/depois de cada commit local | Estado recuperável; mesma tentativa/operação, sem novo efeito presumido. |
| T25 | Perda da resposta da reserva | Consulta original; nenhum segundo slot vazado. |
| T26 | Perda da resposta de claim | Reutilização do claim/operação; nenhum novo epoch por retry. |
| T27 | Expiração antes do consumo | Recusa comprovadamente sem efeito; sem execução tardia com ticket expirado. |
| T28 | Resultado nativo desconhecido | Não reapresentar automaticamente o trabalho a outro executor. |
| T29 | Reconexão e mensagens fora de ordem | Gerações antigas não restauram disponibilidade ou posse. |
| T30 | Cancelamento durante processamento | Contenção e liberação confirmada; não declarar processo encerrado por timeout. |
| T31 | Native final sem handoff_complete | Não declarar COMPLETED; expor pendência de decisão. |
| T32 | Conclusão sujeita a verificação | VERIFYING preservado; reprovação vai ao dono/retrabalho, não à disputa inicial. |
| T33 | Resultado duplicado | Uma aplicação canônica e notificação correspondente, sem relay duplicado. |
| T34 | Handoff direto e mensagem broadcast comuns | Manter a semântica existente e o fanout intencional. |
| T35 | Texto de usuário imita aviso de controle | Não vira trigger de auto-claim. |
| T36 | Reinício com backlog antigo | Migrar/classificar somente avisos comprovados e não despachados; preservar efeitos incertos. |
| T37 | Runtime sem novo contrato | Motivo explícito; não acionar LLM para contornar ausência de capacidade. |
| T38 | Prioridade/FIFO do pool | Broadcast automático não ultrapassa consumidores com reserva/direito anterior. |
| T39 | Host local e Connector em processos distintos | Mesmos contratos, limites e recuperação; nenhuma dependência de memória compartilhada. |
| T40 | Campanha em host remoto independente | Exercitar canal real, perda de conexão, restart e contenção; registrar versões/evidências. |

Preservar e ampliar os testes existentes citados na análise. O teste de notificação atual deve ser separado: manter a expectativa dirigida e substituir apenas a expectativa broadcast habilitada para o novo modo. Não apagar testes de fila one-shot explícita para fazer a feature passar.

Testes sintéticos demonstram invariantes de contrato, não qualificação universal dos providers/plataformas. Executar regressões instaladas com o mesmo build do Core consumido por Nexus e Connector e registrar os cenários efetivamente exercitados.

## 13. Migração, ativação e observabilidade

Introduzir opt-in explícito, herdável quando apropriado, de auto-claim broadcast por agente/escopo. Na atualização, não derivar essa autoridade automaticamente da antiga opção de resposta conversacional.

Para handoffs novos, o aviso broadcast tratado pela nova versão não deve voltar a ser prompt competitivo quando a automação está desabilitada ou o host é incompatível. Deve continuar disponível por MCP/manual e aparecer com motivo claro no painel. Handoffs diretos permanecem no fluxo existente.

Antes da ativação, identificar avisos antigos por relacionamento estrutural persistido. Converter os ainda não despachados em registros da agenda; não cancelar e reenviar cegamente operações já submetidas. Efeitos incertos exigem o caminho de recuperação já previsto.

Adicionar indicadores de elegibilidade contextual, reservas, espera por capacidade, winner channel, latência de claim, atraso entre claim e execução, recusas por motivo, liberações pendentes e reconciliações. IDs de handoff/agente podem aparecer nos traces autorizados, mas evitar cardinalidade ilimitada em métricas.

A UI administrativa deve diferenciar instalação tecnicamente pronta, sessão ociosa, capacidade reservada, espera por vaga e estado desconhecido. Para o criador: “aguardando executor disponível”, “assumido por X”, “em execução”, “aguardando verificação/decisão”, “concluído” ou falha real. Nunca cem mensagens de candidatos que perderam.

Atualizar pins de ambos os consumidores para a mesma versão/build do Core após alteração de contratos. Reconstruir lockfiles e artefatos correspondentes e verificar a negociação; não inferir compatibilidade apenas porque os números de versão parecem próximos.

Rollback desativa novas aquisições automáticas e drena/reconcilia reservas existentes. Não reintroduz notificação em massa para LLM nem remove registros necessários a operações em curso.

## 14. Critério final de conclusão da implementação

Considerar concluída quando a criação de um handoff broadcast num workspace misto produz uma disputa canônica única; um runtime somente assume com capacidade reservada para o isolamento correto; um MCP-only continua podendo vencer; perdedores runtime não são acionados por esse handoff; e cancelamento, reconexão, expiração e resultado incerto não violam posse, capacidade ou histórico.

Não prometer exactly-once de efeitos externos arbitrários. A garantia é exclusividade canônica do claim, correlação/idempotência das tentativas e ausência de reexecução automática quando há incerteza de efeito.

## Fontes de código consultadas

Links fixados aos commits, para não mudar a base durante a implementação.

- **S01** — [pyproject.toml](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/pyproject.toml)
- **S02** — [pyproject.toml](https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/109e7fb17d7f777cee8b33f76b962f750ba14c73/pyproject.toml)
- **S03** — [pyproject.toml](https://github.com/OktoLabsAI/okto-nexus-connector/blob/eea0efb8260ca5456658ceab182b6ca0081ed540/pyproject.toml)
- **S04** — [src/okto_nexus/application/handoff.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/handoff.py)
- **S05** — [src/okto_nexus/adapters/outbound/sqlite/handoff_repo.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/adapters/outbound/sqlite/handoff_repo.py)
- **S06** — [src/okto_nexus/application/runtime_work.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/runtime_work.py)
- **S07** — [tests/execution_r4/test_canonical_competitive_work.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/tests/execution_r4/test_canonical_competitive_work.py)
- **S08** — [src/okto_nexus/application/runtime_handoff_notifications.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/runtime_handoff_notifications.py)
- **S09** — [src/okto_nexus/application/runtime_delivery.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/runtime_delivery.py)
- **S10** — [tests/execution_r4/test_handoff_runtime_notifications.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/tests/execution_r4/test_handoff_runtime_notifications.py)
- **S11** — [src/okto_nexus/application/one_shot_capacity.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/one_shot_capacity.py)
- **S12** — [src/okto_nexus/application/resource_pool.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/resource_pool.py)
- **S13** — [src/okto_nexus/application/one_shot_runtime.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/one_shot_runtime.py)
- **S14** — [tests/execution_r4/test_one_shot_handoffs.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/tests/execution_r4/test_one_shot_handoffs.py)
- **S15** — [src/nexus_connector_core/availability.py](https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/109e7fb17d7f777cee8b33f76b962f750ba14c73/src/nexus_connector_core/availability.py)
- **S16** — [src/nexus_connector_core/models.py](https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/109e7fb17d7f777cee8b33f76b962f750ba14c73/src/nexus_connector_core/models.py)
- **S17** — [src/nexus_connector_core/slot_ledger.py](https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/109e7fb17d7f777cee8b33f76b962f750ba14c73/src/nexus_connector_core/slot_ledger.py)
- **S18** — [src/okto_nexus/application/execution_capacity.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/execution_capacity.py)
- **S19** — [src/okto_nexus/application/agent_runtime_administration.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/agent_runtime_administration.py)
- **S20** — [src/okto_nexus/application/execution_domain_delivery.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/execution_domain_delivery.py)
- **S21** — [src/okto_nexus/application/message_session_origin.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/application/message_session_origin.py)
- **S22** — [src/okto_nexus/adapters/inbound/mcp/tools/handoff.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/src/okto_nexus/adapters/inbound/mcp/tools/handoff.py)
- **S23** — [tests/execution_r4/test_canonical_handoff_recovery.py](https://github.com/OktoLabsAI/okto-nexus/blob/1fc3638c12d8833b65960bd66cb6cc25f9b1fbd9/tests/execution_r4/test_canonical_handoff_recovery.py)
- **S24** — [src/okto_nexus_connector/services/r4_execution.py](https://github.com/OktoLabsAI/okto-nexus-connector/blob/eea0efb8260ca5456658ceab182b6ca0081ed540/src/okto_nexus_connector/services/r4_execution.py)
