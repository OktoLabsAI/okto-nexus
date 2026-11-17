# Okto Nexus — Home: Active, Needs You, Results e badges de estado

**Plano:** HOME-STATES-R1 · especificação consolidada · 17/11/2026  
**Destinatário:** Codex / agente de implementação com capacidade intermediária.  
**Estado:** plano de desenvolvimento, não declaração de entrega.  
**Objetivo:** tornar inequívoca a diferença entre conexão do harness, execução, pendência humana e entrega, mantendo a Home simples.  
**Dimensão:** 32 tarefas, 116 cenários de aceite, 20 requisitos e 7 etapas de implementação.  
**Entrega:** evoluir a Home existente, com as mesmas três colunas, sem outro menu, inventário ou sistema de execução.

## Como executar

Este documento é autocontido para esta evolução. Entregar junto o ledger e o prompt deste pacote. O Markdown é normativo; o ledger registra execução. Começar pela etapa HST-00 e reconciliar o checkout, pois há desenvolvimento concorrente. Não substituir ledgers anteriores, repetir recursos prontos ou resetar trabalho do usuário. A leitura de documentos antigos é contextual, não uma dependência para entender as regras deste plano.

As definições finais desta conversa prevalecem para a apresentação: **Active inclui harnesses conectados executando ou Idle; Needs You tem comportamento duplo; Results apresenta entregas e encerramentos com seu significado real.** Não recuperar a recomendação intermediária de excluir todo harness ocioso de Active. A simplificação da navegação e o Quick Connect já planejados continuam preservados, mas não serão reconstruídos aqui.

Nomes novos de campos, serviços e testes são propostas. Reutilizar equivalentes no checkout real e registrar a correspondência. Os snippets são contratos conceituais, não código pronto para colar sem adaptação. Nenhum teste da aplicação foi executado na elaboração deste plano.

---

# 1. Base consultada e diagnóstico

## 1.1 Snapshot

| Item | Referência |
|---|---|
| Repositório | `OktoLabsAI/okto-nexus` |
| Branch de versão mais alta encontrada na consulta | `feature/v0.3.6` |
| SHA fixado para esta inspeção | `f28a31a22436c366a4c8dbdf5e3b250d606a61be` |
| Versão declarada | `0.3.6` |
| Dependência Core declarada | `okto-nexus-connector-core==0.0.14` |
| Python mínimo declarado | `>=3.11` |
| Natureza da análise | Inspeção estática de arquivos selecionados; não foi executada uma instalação Nexus, navegador ou harness. |

A referência identifica código, não release publicado nem instalação do usuário. Antes de alterar, registrar branch, HEAD, working tree, instruções `AGENTS.md`, dependências e drift. Não retroceder automaticamente ao SHA. Fontes fixadas estão na seção 18. [S01]

## 1.2 Fatos concretos que orientam o delta

| Evidência atual | Consequência |
|---|---|
| `home_harness_board.py` já cria cards por conexão registrada, coloca o harness em Needs You apenas com `blocks_harness=True` e publica entregas separadamente. | Evoluir a projeção; não recriar a Home ou regressar a cartões de tipos variados em Active. [S02] |
| `home_harness_blocking.py` distingue `working`, `registered`, `waiting_for_user`, `awaiting_confirmation` e `unknown`. | Acrescentar prova de Idle e badges; não renomear `registered` para Idle sem evidência. [S03] |
| A leitura `CONNECTIONS` agrega bindings registrados; não comprova por si só processo conectado ou heartbeat atual. | Separar cadastro, conectividade, sessão e atividade antes de contar conectados. [S04] |
| `HARNESS_BLOCKING` reconhece booleano de bloqueio para `item/tool/requestUserInput`; outras solicitações não têm automaticamente a mesma prova. | Cobrir aprovação, pergunta e coordenação conforme contratos reais; não afirmar que todo pedido bloqueia, nem inventar suporte de Pi/Claude. [S03–S04] |
| Results inclui turnos `turn.submit` com recibo terminal `SUCCEEDED`, `FAILED` ou `CANCELLED`, e resultados de handoffs `COMPLETED`/`REJECTED` sem equivalente nativo. | Results não é só uma lista de sucessos; classificar escopo, resultado, estado da tarefa e verificação separadamente. [S05] |
| O card mostra `Completion recorded · Outcome: SUCCEEDED` e uma orientação genérica para revisar a verificação. | Substituir por texto explícito: fim de turno, tarefa concluída, verificação pendente, falha etc. [S06] |
| O controller publica `hasPendingUpdate` quando a apresentação está pausada; o painel de atividades usa esse sinal para desabilitar leitura e pedir fechar/reabrir. | Criar um teste de reprodução e separar pausa visual, mudança real, atualização do detalhe e autorização. O defeito ainda precisa de reprodução no navegador. [S07–S08] |
| Os contratos carregam `workspace_label` e timestamps, mas os cards não os usam de forma consistente. | Mostrar projeto em All projects e tempo com significado correto. [S06, S09] |
| O principal botão do harness abre um painel intermediário de atividades; o seletor de sessão expõe IDs técnicos. | Abrir direto a sessão inequívoca e melhorar as opções de escolha mantendo a referência exata. [S08, S10] |
| Há `Reconnect` desabilitado em todo card Active; o relatório informa que a recuperação existente do Connector tem escopo de daemon. | Retirar a ação indisponível do destaque, sem implementar restart como falsa reconexão individual. [S06, S11] |
| Testes existentes já cobrem pergunta bloqueante, trabalho paralelo, snooze e decisão recebida sem confirmação nativa. | Preservar e ampliar esses testes; fixtures não comprovam harness real. [S12] |

Os relatórios do repositório registram evidências e gates pendentes de outros cortes. Não tratá-los como execução realizada neste plano nem apagá-los para liberar a entrega. Em particular, não afirmar que o default da nova Home, o desempenho ou todas as plataformas já foram qualificados. [S11]

## 1.3 Relação com os demais trabalhos

Preservar a navegação Home/Conversas/Grafo/Artefatos/Avançado, as identidades, o ID público do Harness, o Quick Connect, os checkpoints, o daemon e o uso completo pelo terminal. Este plano altera **projeção, semântica visual e interação contextual da Home**. Não modifica quem pode executar, a regra de claim, o protocolo nativo ou as permissões de uma conexão.

A composição atual por harness e suas três colunas, documentada em `HARNESS_CARD_R3_AMENDMENT.md`, é a base. Este documento complementa essa composição com a definição final de Idle, badges de ação, confirmação de retomada e classificação de entregas. A antiga orientação de uma única lista sem colunas não deve ser reaplicada. [S13]

---

# 2. Decisões de produto fechadas

## 2.1 O que significa cada coluna

| Coluna | Unidade principal | Regra |
|---|---|---|
| **Active** | Uma conexão canônica de harness | Fica visível enquanto conectada e não globalmente parada por uma dependência humana. Pode estar Executando ou Idle. Estados de preparação/incerteza são explícitos. |
| **Needs You** | Harness bloqueado **ou** solicitação independente | Se toda a execução produtiva relevante do harness está parada por ação humana comprovada, mover seu card para cá. Se ele continua trabalhando, somente a solicitação aparece aqui, e o harness permanece em Active. |
| **Results** | Entrega/encerramento correlacionado | Mostra saída de turno, entrega de tarefa, verificação e encerramentos com falha/cancelamento. Não recebe o card operacional do harness por ele terminar o trabalho. |

As colunas não são etapas de um Kanban e seus contadores não se somam. Um harness pode estar em Active e ter uma entrega em Results; é a mesma conexão com dois objetos diferentes, não duplicação do card do harness.

## 2.2 Regras que não podem ser reinterpretadas

1. Ocioso conectado permanece visível em Active com **Idle**, quando houver evidência suficiente.
2. Pedido humano não é sinônimo de bloqueio. A origem e o estado efetivo determinam a colocação.
3. A passagem de não bloqueante para bloqueante move o card quando houver prova; não por timeout ou ausência de tokens.
4. Responder/aprovar não significa retomada. A interface aguarda evidência posterior da mesma execução.
5. Entrega de um turno não conclui automaticamente um handoff; conclusão de handoff não prova aprovação de verificação se essa prova não existe.
6. Active e Needs You contêm no máximo um card operacional por conexão no mesmo snapshot. Results contém entregas, nunca outra cópia operacional.
7. Cada pergunta/decisão tem uma única apresentação acionável no quadro: independente ou incorporada ao harness bloqueado. Badge e sino são referências à mesma ocorrência, não cópias de comando.
8. A Home permanece mínima: mesmas três colunas, um painel contextual ativo, sem nova tela de harnesses/sessões/estados.

## 2.3 Limite de escopo

Não criar scheduler, motor de QA, novo workflow de verificação, PTY, console de shell, sumarizador por LLM, servidor MCP no Connector, novo cadastro de tarefas ou novo sistema de notificações. Não instalar software nem chamar provedor para calcular um badge.

Não criar uma quarta coluna Offline. Conexões sem prova atual continuam encontráveis na mesma região, explicitamente como registradas, reconectando ou indisponíveis; não contam como conectadas/Idle. A apresentação de exceções é definida na seção 4.6.

---

# 3. Modelo de fatos: não reduzir tudo a um enum

## 3.1 Identidade estável

A unidade do card é a conexão canônica comprovada, seguindo a tupla usada pelo produto: `server_id`, `executor_id`, `binding_id`, `workspace_id`, `workspace_binding_id`, `agent_id`, com `endpoint_id` e revisões quando exigidos pelo contrato. Não agrupar por `connect_id`, nome, PID, família do harness ou `agent_id` isolado.

`connect_id` é o **ID do Harness** público. `harness_id` nos DTOs atuais é a família/adaptador técnico; não renomeá-lo implicitamente para ID público. Várias sessões pertencem à mesma conexão e preservam suas referências próprias. Dois Codex ligados à mesma identidade continuam sendo dois cards se os bindings forem distintos.

## 3.2 Dimensões independentes

| Dimensão | Exemplos | O que não comprova |
|---|---|---|
| Cadastro | binding aprovado/desabilitado/revogado | Processo vivo, conectividade ou execução. |
| Conectividade | conectado, reconectando, desconectado, não confirmado | Que há trabalho ou capacidade autorizada. |
| Sessão/processo | sessão ativa, aquecida, encerrada, sob demanda | Que está executando uma tarefa. |
| Atividade | executando, Idle, na fila, esperando agente, recuperação, não confirmada | Que o usuário deve agir. |
| Dependência humana | nenhuma, não bloqueante, parcial, bloqueio total, desconhecida | Que a pessoa atual tem permissão para resolver. |
| Entrega | turno encerrado, tarefa concluída, falha, cancelamento, reporte externo | Verificação aprovada. |
| Verificação | não aplicável, não informada, pendente, aprovada, rejeitada | Estado de outro claim/versão ou aprovação de ferramenta. |
| Atualidade | atual, desatualizada, indisponível | Estado real atual só porque o SSE está conectado. |

O backend compõe os fatos; a UI traduz para rótulos e ações. Não criar outra máquina de estados produtiva para sustentar essa apresentação.

## 3.3 Evidência necessária

Para cada fato, manter a referência canônica, geração/epoch/revisão pertinente, origem e validade/as_of. Uma query recente pode devolver fatos antigos. Usar os TTLs e contratos existentes; não introduzir arbitrariamente “após 30 segundos sem evento é Idle”.

**Prova positiva pode sobreviver a cobertura parcial de outra fonte:** uma operação corrente comprovadamente executando pode manter o badge Executando, acompanhado de cobertura parcial. Já **provar ausência** de trabalho ou bloqueio global exige cobertura completa do conjunto pertinente. Separar exatidão de contagem de conhecimento de um fato positivo.

Não usar a página visível, `events_preview`, `runtime_refs` limitado ou os três eventos do card para classificar o harness. A classificação utiliza a relação autorizada completa antes de paginação e de filtros de apresentação.

## 3.4 Fontes e lacunas a resolver

Reutilizar as relações de operações, recibos, sessões, conexões, Attention e resultados. A consulta atual de conexões deve ser enriquecida com prontidão/conectividade de escopo correto; um status agregado por agente não serve se duas conexões daquele agente têm estados diferentes.

Criar na etapa inicial a matriz **adaptador → tipo de pedido → metadado de bloqueio → geração → prova de retomada → disponibilidade da fonte**. Para Codex, Pi e Claude, conferir contratos e fixtures de cada integração; não extrapolar o booleano de um método do Codex para outro harness.

O pedido pode aparecer com ação correta mesmo sem prova de bloqueio. Nesse caso, `blocks_harness` é desconhecido, não falso. Caso falte fato nativo essencial, primeiro buscar sua normalização no Server a partir do que já é publicado. Uma mudança de Core/Connector só é admitida com lacuna e contrato documentados, compatibilidade e testes próprios; a UI não passa a consultar processos remotos.

---

# 4. Active e classificação operacional

## 4.1 Executando

Exibir **Executando / Working** quando pelo menos uma execução produtiva da conexão tiver início/progresso corrente comprovado e não estiver atualmente suspensa por uma dependência aplicável. Respeitar a geração de sessão, a tentativa/claim atual, o stream sem lacuna relevante e o estágio terminal posterior.

Uma execução que espera aprovação não permanece “executando” apenas porque conserva um recibo RUNNING anterior. Outra execução independente e corrente da mesma conexão, contudo, mantém o card em Active.

Fila, aceite nativo, abertura de processo, manutenção e pool aquecido não contam como execução produtiva.

## 4.2 Idle

Exibir **Idle**, não “Aguardando”, somente se:

- existe evidência atual de conexão/runtime pertinente e binding válido;
- o conjunto autorizado de sessões e operações relevantes está completo;
- não há turno produtivo ainda em andamento, envio não confirmado, reconciliação pendente, fila de execução, bloqueio humano ou confirmação de retomada pendente;
- o contrato do runtime confirma prontidão/ociosidade ou permite derivá-la inequivocamente da sessão vigente e de todos os turnos encerrados.

Não basta `pending == {}` na consulta atual. Fonte ausente, diretório de sessões limitado ou histórico incompleto não autoriza Idle.

**Sessão fechada por política one-shot:** uma configuração pronta para futura abertura, sem processo/sessão ativa, pode mostrar **Sem sessão ativa / No active session**, não Idle nem “desconectado por erro”. Não iniciar uma sessão para fazer o badge parecer Idle. Harness conectado com sessão persistente e trabalho encerrado fica Idle normalmente.

## 4.3 Outros estados honestos

Rótulos propostos: **Na fila**, **Conectando**, **Reconectando**, **Aguardando outro agente**, **Aguardando confirmação**, **Estado não confirmado**, **Sem sessão ativa**, **Desconectado**. Não mostrar todos no caso comum. Cada estado raro aparece somente quando aplicável, com causa curta e link de inspeção.

O estado principal usa a evidência mais relevante sem apagar as outras dimensões. Ex.: uma execução corrente e outra bloqueada produzem **Executando** + **Resposta pendente**, e o detalhe mostra “2 sessões: 1 executando, 1 bloqueada”. Não criar badge genérico Idle para esconder esse paralelismo.

## 4.4 Resumo de Active

Exemplo: **3 conectados · 1 executando · 2 Idle**.

Contar conexões distintas, não sessões, operações ou todos os bindings cadastrados. Somar separadamente estados restantes quando existirem: “2 conectados · 1 na fila · 1 Idle; 1 estado não confirmado”. Um card de cadastro sem prontidão comprovada não entra no número “conectados”.

Nenhum total é obtido de `items.length` de uma página. Totais podem ser parciais/desconhecidos com motivo explícito. Número de ações, tarefas e harnesses são unidades diferentes.

## 4.5 Reconexão e configuração

Retirar o botão Reconnect indisponível de todos os cards. A explicação de limitação fica em Detalhes da conexão/diagnóstico. Só apresentar ação de recuperação quando ela já existir com escopo e autorização correspondentes.

Reiniciar um daemon que atende vários harnesses não pode aparecer como “Reconectar este harness”. Abrir um card, ver uma sessão ou atualizar a Home nunca executa `runtime.start`, Test ou novo grant.

## 4.6 Conexões desconhecidas e desconectadas

**Decisão de borda para evitar falsa disponibilidade:** preservar o card no mesmo espaço operacional, com rótulo explícito, prioridade visual menor e sem contá-lo como conectado/Idle. Não criar coluna/lista administrativa paralela. O título Active ganha um resumo que separa conectados de indisponíveis/não confirmados quando necessário.

Se a prova atual do bloqueio expirar junto com a conexão, não continuar afirmando bloqueio atual. Mostrar “Último estado: aguardando resposta; conexão não confirmada”, e manter a ocorrência humana atual acessível em Needs You. Se o backend ainda comprovar bloqueio e pedido no escopo atual, o card pode permanecer em Needs You com a conectividade indicada separadamente. Nunca sumir com a pergunta só porque houve desconexão.

Uma queda do Server vista pelo navegador é erro de consulta global, não prova individual de que todos os harnesses ficaram desconectados. Conservar somente dados autorizados do mesmo escopo, rotulados como antigos. Logout/revogação limpa o conteúdo protegido.

---

# 5. Needs You: ação, bloqueio e transições

## 5.1 Decidir se existe ação do usuário

A ocorrência deve estar canonicamente aberta, destinada ao operador/usuário autorizado e ter uma ação pertinente ao seu estado. Reusar `AttentionOccurrence`, `allowed_actions`, destinatário, `source_revision`, preferências e controles atuais. Não gerar uma solicitação humana apenas porque há um handoff OPEN, mensagem não lida ou erro técnico.

Um handoff destinado a outro agente não exige intervenção do usuário por definição. Uma verificação realmente atribuída ao operador exige. A pergunta dirigida a outro agente pode ser acompanhada sem o operador personificar esse agente.

## 5.2 Bloqueio por operação e agregação por harness

Primeiro classificar cada execução/contexto: `blocked_by_user`, `independently_progressing`, `waiting_other`, `terminal`, `unknown`. A classificação usa dependência/pause real, não só o tipo de formulário.

O card inteiro vai para Needs You se houver bloqueio humano confirmado **e** nenhuma execução produtiva independente da mesma conexão puder progredir segundo a evidência completa. Sessões ociosas não contam como progresso e não impedem essa movimentação. Execução em outro binding do mesmo agente também não a impede.

Se outra execução estiver correntemente trabalhando, Active mantém o card. A ação bloqueante para uma sessão aparece como solicitação independente em Needs You, com texto **“Bloqueia esta sessão; o harness continua outro trabalho”**. Não rotular essa solicitação como intrinsecamente não bloqueante: distinguir `blocks_session=true` de `blocks_harness=false`.

Uma fila só impede a prova de bloqueio total quando houver evidência de que contém trabalho independente admissível; mera existência de itens queued ou mensagem unread não prova que consegue progredir. Se a relação de dependências é incompleta, a agregação é desconhecida.

## 5.3 Ação que ainda não bloqueia

O card Active mostra o badge principal de atividade e um badge secundário **Resposta pendente**, **Aprovação pendente**, **Decisão pendente** ou **N ações pendentes**. Em Needs You aparece a solicitação com contexto, origem e botão apropriado.

Se depois o harness atingir a dependência e parar, a leitura atual do backend move seu card para Needs You e incorpora a mesma ocorrência. O ID/revisão da pergunta não muda por uma movimentação de UI; não criar outra pergunta. A transição só ocorre com prova nativa/canônica.

## 5.4 Ação bloqueante

O card de harness em Needs You mostra o tipo da dependência: **Aguardando sua resposta**, **Aguardando sua aprovação**, **Aguardando sua decisão**, **Aguardando sua verificação** ou **Aguardando N ações**.

O motivo e a ação principal precisam ser visíveis no card. Com uma ocorrência, um botão abre diretamente o formulário exato. Com várias, **Ver N ações** abre no mesmo painel a lista contextual, priorizando bloqueantes, prioridade canônica e idade; desempate por ID estável. Não esconder ocorrências além do preview.

Incorporar nesse card todas as solicitações próprias que precisam ser mostradas, distinguindo quais bloqueiam. Não manter simultaneamente cópias acionáveis soltas dessas mesmas ocorrências. Um evento no card e o sino podem apontar para elas; não contam como outras pendências.

## 5.5 Resposta registrada não é retomada

Definir o ciclo por ocorrência/decisão:

| Evidência | Apresentação | Próxima ação possível |
|---|---|---|
| Pedido aberto e decidível | Aguardando sua resposta/aprovação/etc. | Ação canônica correspondente. |
| Envio em curso | Enviando resposta/decisão | Impedir duplicação da mesma intenção. |
| Resposta HTTP perdida | Confirmação do envio pendente | Recuperar o recibo existente; não reenviar às cegas. |
| Decisão registrada, aplicação nativa não confirmada | Resposta/decisão enviada · aguardando confirmação | Consultar; não mostrar Responder outra vez. |
| Aplicação recusada | Resposta não aplicada | Inspeção/recuperação canônica, se autorizada. |
| Evidência posterior de trabalho corrente | Executando | Card retorna a Active se não restar bloqueio total. |
| Turno encerrado e sessão conectada/pronta, conjunto completo | Idle | Card em Active; entrega em Results. |
| Sessão encerrada por política normal | Sem sessão ativa | Card preservado, sem iniciar outra sessão. |

Para o intervalo após responder um harness que estava totalmente bloqueado, manter provisoriamente o card em Needs You com **Aguardando confirmação de retomada**, explicitando que **não é necessária outra resposta**. Essa posição exige referência à decisão e ao bloqueio anterior da mesma execução; não é uma pendência inventada no domínio. O contador de ações humanas abertas fica zero para a decisão já registrada. Se houver trabalho paralelo comprovado, o card pode estar Active e o estado da decisão aparece como acompanhamento, sem outro pedido acionável.

A prova de retomada deve ser causalmente posterior à decisão e da mesma geração/contexto. Timestamp de chegada de um recibo RUNNING antigo não basta; usar correlação, sequência/epoch ou contrato específico que comprove avanço. Ao faltar evidência, continuar “não confirmado”, não assumir Idle nem Working.

## 5.6 Expiração, negação, visto e snooze

Negar uma aprovação não implica que o turno foi cancelado; esperar resultado real. Pedido expirado não concede permissão para reapresentá-lo como decidível. Se o runtime continuar parado, mostrar a necessidade de recuperação comprovada, não reutilizar revisão antiga.

Marcar visto não responde. Adiar lembrete não libera bloqueio. Um harness comprovadamente bloqueado permanece em Needs You mesmo com lembrete adiado, com indicação discreta. Para solicitações independentes, respeitar a preferência do sistema de Attention; o badge do harness pode indicar pendências totais e quantas foram adiadas, sem renotificar continuamente.

Uma decisão concluída por outra aba ou CLI atualiza a mesma ocorrência. Não copiar texto/controle para uma pergunta nova e não confirmar uma decisão contra a revisão da anterior.

## 5.7 Deduplicação e contagens

Produzir uma relação de ocorrências canônicas distintas antes de paginar. `pending_action_count` conta IDs abertos acionáveis, inclusive quando incorporados a harnesses; uma resposta já registrada não entra nele. `visible_notification_count` respeita snooze; `blocked_harness_count` conta conexões, e `resume_confirmation_count` conta contextos aguardando aplicação. Não confundir os quatro.

O cabeçalho pode dizer **2 ações · 1 harness parado**. Se só existir aplicação pendente, dizer **1 retomada em confirmação** em vez de “1 ação pendente”.

Pedido com vínculo único pertence à conexão comprovada. Pedido compartilhado sem dono único fica como uma única solicitação independente com referências autorizadas; não distribuí-lo como várias aprovações. Pedido sem vínculo permanece acessível com **Origem não confirmada**, sem criar harness fictício. Incidentes globais do Server continuam em faixa compacta separada dos números do projeto.

---

# 6. Results: resultado do turno, da tarefa e da verificação

## 6.1 O que alimenta a coluna

Reusar a projeção `RESULTS` e seus registros canônicos. Atualmente ela parte de turnos produtivos encerrados e de resultados de handoffs; reportes externos explícitos têm um caminho próprio no quadro. Uma conexão ficar Idle ou uma ferramenta imprimir “terminei” não cria entrega. [S02, S05]

O mínimo para uma entrada é um encerramento canônico de turno produtivo, uma conclusão/rejeição de handoff ou um reporte de término externo canônico identificado como tal. Progresso parcial de tokens e saídas individuais de ferramenta ficam no acompanhamento, não inundam Results.

## 6.2 Campos semânticos de entrega

Manter separados: origem da evidência (`canonical`/`reported`), escopo (`turn`/`handoff`/`external_report`), resultado do turno, estado atual da tarefa, estado de verificação, estado de limpeza, disponibilidade de conteúdo, episódio/claim, versão e histórico.

O campo atual `verification_state` pode conter status de handoff, e não uma prova independente de verificação. Não interpretar automaticamente `COMPLETED` nesse campo como “Verificado”. Auditar a fonte real de decisão de verificação/aceite e só mostrar o selo quando o registro específico, autorizado e da mesma entrega existir.

## 6.3 Tabela normativa de mensagens

| Fato confirmado | Mensagem principal | Complemento / badge |
|---|---|---|
| Turno SUCCEEDED sem handoff associado | **Resposta disponível** / **Turno concluído** | Não inventar tarefa pendente nem exigir verificação inexistente. |
| Turno encerrado com saída, handoff ainda OPEN/CLAIMED | **Resultado do turno disponível** | **Tarefa ainda não concluída**. |
| Entrega em VERIFYING atual | **Entrega disponível** | **Aguardando verificação**. |
| Handoff COMPLETED, sem prova independente de verificação aprovada | **Tarefa concluída** | Sem selo “Verificada”. |
| Conclusão e verificação aprovada da mesma versão/claim | **Tarefa concluída** | **Entrega verificada**. |
| Verificação rejeitada da entrega atual | **Entrega não aprovada** | Exibir motivo disponível e estado atual da tarefa, sem reabrir/reexecutar por UI. |
| Turno FAILED | **Execução encerrada com falha** | Saída parcial/diagnóstico se existirem; sem botão retry genérico. |
| Turno CANCELLED | **Execução cancelada** | Artefatos/saída parcial permanecem acessíveis. |
| Handoff REJECTED | **Entrega/tarefa rejeitada**, conforme contrato real | Não confundir com cancelamento do runtime. |
| Sucesso produtivo com cleanup pendente | **Resultado disponível** | **Limpeza pendente**, sem reexecutar trabalho bem-sucedido. |
| Término confirmado, conteúdo ainda não publicado/capturado | **Execução encerrada** | **Saída ainda não disponível**; não afirmar entrega completa. |
| Reporte externo explícito | **Término reportado** | **Não verificado pelo Nexus**; nunca sucesso nativo inferido. |
| Resultado de claim/tentativa anterior | Resultado histórico com seu outcome | **Tentativa anterior**; não concluir a tarefa atual. |

`OUTCOME_UNKNOWN` sem término confirmado não entra como uma nova entrega concluída. Continua no contexto de execução e, havendo necessidade real de decisão do operador, em Attention. Um resultado histórico confirmado não é apagado porque uma tentativa posterior ficou incerta.

Se fontes canônicas se contradisserem, apresentar estado não confirmado/limitação e permitir inspeção. Não inventar regra que altere o handoff para harmonizar os badges.

## 6.4 Exemplo ponta a ponta

Pedido: “Revise a autenticação e entregue um parecer”. Harness Codex aparece Active/Executando.

O turno termina e devolve um texto. Results cria uma entrega, e o harness continua no quadro operacional: Idle se isso estiver comprovado, Executando se há outro trabalho, ou estado apropriado se o processo/sessão terminou.

Se o parecer pertence a um handoff ainda em andamento, Results diz **Resultado do turno disponível · tarefa ainda não concluída**. Ao handoff ir a VERIFYING, a mesma entrega correlacionada passa a **Aguardando verificação**. A pendência de revisão atribuída ao operador aparece em Needs You; não mover o harness para Needs You apenas porque um humano precisa ler a entrega, se ele continua livre para outro trabalho.

Depois do aceite/conclusão canônicos, Results mostra **Tarefa concluída**. O selo **Entrega verificada** só aparece se a verificação positiva está registrada para essa entrega. Sem handoff, mostrar apenas resposta/turno concluído, sem adicionar um workflow de tarefas artificial.

## 6.5 Identidade, retenção e visualização

Preservar as chaves atuais de entrega por operação ou handoff/claim. Uma mudança de verificação atualiza a mesma entrega relacionada; não duplica a linha. Várias entregas realmente distintas permanecem distintas, mesmo com título igual. Operação igual em executores diferentes não colide.

Artefatos são agrupados somente por associação persistida. Listar metadados autorizados; conteúdo e transcript são carregados sob demanda. Não deduzir associação por nome de arquivo ou similaridade de texto.

Preservar a política atual de retenção de resultados e de visto, inclusive sua distinção entre `seen`, `unseen` e `not_tracked`. Não tornar retenção de 24h uma regra universal nova: conferir o comportamento existente de cada origem. Sem rastreamento confiável, dizer **Recentes**, não um total exato de “Novos”.

Ver/abrir Results não reconhece inbox, verifica entrega, completa handoff nem avança um watermark global. Uma ação explícita de visto usa a ocorrência e revisão atuais. Quando uma nova versão exigir nova atenção, seguir o contrato canônico de episódio, não criar outro sistema de novidades.

---

# 7. Badges e conteúdo mínimo do card

## 7.1 Hierarquia

Card de harness: identidade pública + família + projeto/host úteis; badge operacional principal; badge de ação quando houver; evento/objetivo curto; acesso principal ao contexto. Até dois badges destacados no caso comum, com detalhes adicionais recolhidos. Indisponibilidade/atualidade é aviso discreto, não um “Idle” verde contraditório.

Exemplos conceituais, não mockups implementados:

```text
ACTIVE
reviewer · Claude Code                  Projeto: API
[Executando] [Resposta pendente]
Revisando autenticação · pergunta recebida há 2 min
[Acompanhar]

NEEDS YOU — solicitação independente
reviewer · API
“Precisamos manter compatibilidade com v1?”
[Resposta pendente] O harness continua trabalhando.
[Responder]

NEEDS YOU — harness totalmente bloqueado
reviewer · Claude Code                  Projeto: API
[Aguardando sua resposta]
“Precisamos manter compatibilidade com v1?”
[Responder]  [Ver contexto]

ACTIVE depois da conclusão e com sessão conectada
reviewer · Claude Code                  Projeto: API
[Idle]
Última entrega: parecer da autenticação
[Ver contexto]

RESULTS
Parecer da autenticação · reviewer · API
[Resultado do turno disponível] [Tarefa ainda não concluída]
Resumo autorizado · 2 arquivos · recebido há 1 min
[Ver resultado]
```

Um badge pode abrir/focar o pedido existente no painel; não oferecer uma segunda instância independente de submissão. Não colocar controles de seleção técnica em cada card.

## 7.2 Vocabulário por situação

| Tipo de ação | Não bloqueante/execução paralela | Bloqueio total | Botão |
|---|---|---|---|
| Pergunta | Resposta pendente | Aguardando sua resposta | Responder |
| Permissão/ferramenta | Aprovação pendente | Aguardando sua aprovação | Revisar aprovação |
| Decisão/handoff dirigido ao humano | Decisão pendente | Aguardando sua decisão | Revisar solicitação |
| Verificação de entrega | Verificação pendente | Aguardando sua verificação, só se o bloqueio for comprovado | Verificar entrega |
| Várias | N ações pendentes | Aguardando N ações | Ver ações |
| Pós-decisão | Confirmação pendente, quando pertinente | Aguardando confirmação de retomada | Acompanhar confirmação |

Textos seguem o idioma atual do frontend. A especificação em português não autoriza migração global de idioma: em inglês usar `Working`, `Idle`, `Response pending`, `Approval pending`, `Waiting for your response`, `Waiting for resume confirmation` etc., centralizados em um mapa testado.

## 7.3 Projeto, tempo e rótulos

Em **All projects**, todo card de harness, solicitação e resultado mostra o projeto autorizado. Dois `reviewer` em projetos diferentes precisam ser distinguíveis sem abrir detalhes. Em projeto único, omitir o marcador redundante quando claro pelo cabeçalho.

Usar `state_since` somente quando a transição é comprovada. Se há apenas timestamp do evento, mostrar **Última atualização** ou **Recebido há**, não “executando há”. Oferecer data absoluta no detalhe. Passagem do tempo atualiza texto de forma limitada; não emitir anúncio de leitor de tela a cada segundo.

## 7.4 Compactação sem nova reorganização

Reduzir texto repetido acima do quadro. Projeto e Add harness cabem numa barra curta; indicadores podem ser uma faixa, sem quatro grandes painéis obrigatórios. Escolher um controle principal de refresh, evitando duplicação com o shell. Explicações longas ficam no primeiro acesso/ajuda/estado vazio.

Manter as três colunas visíveis ou empilhadas responsivamente. Não substituir o quadro por tabs que escondam pendências por padrão. Novo pedido pode apresentar **Pedir trabalho** e **Conversar**, reutilizando handoff/message canônicos; não converter automaticamente o texto em um tipo via LLM.

---

# 8. Contrato de leitura e implementação backend

## 8.1 Projeção, não novas entidades

Estender `EntryRelations`, `ConnectionContext` ou projeções equivalentes com fatos de conectividade/atividade e semanticamente tipar o resultado. Fazer leituras batch na mesma UoW autorizada. Nenhum GET chama Core, Connector, filesystem de artefatos, processo do harness ou provedor para calcular um badge.

Não criar `home_harness_status`, `home_pending_tasks` ou outra tabela de estado produtivo. Preferir derivar o ciclo pós-decisão dos recibos existentes. Uma cache otimizada só pode existir como cache invalidável e sem autoridade, com justificativa medida; não é necessária por padrão.

## 8.2 DTOs propostos, a reconciliar

Adicionar campos de apresentação versionados sem reutilizar enums antigos com significado diferente. A UI atual valida estritamente `activity_state`; atualizar backend, validadores, tipos e fixtures juntos. Preferir manter campos antigos durante a transição e criar `operational_status`, mapeando Idle para o estado legado neutro quando houver consumidor antigo. Não enviar `idle` a um cliente que só aceita `registered/working/...` sem negociação/compatibilidade.

```typescript
// Contrato conceitual; adaptar aos tipos e envelopes reais.
type TriState = true | false | null;
type Count = { value: number | null; exact: boolean };
interface OperationalStatus {
  version: 1;
  connection: 'connected' | 'connecting' | 'reconnecting' | 'disconnected' | 'registered' | 'unknown';
  activity: 'working' | 'idle' | 'queued' | 'waiting_user' | 'waiting_agent'
          | 'awaiting_confirmation' | 'no_active_session' | 'recovering' | 'unknown';
  blocking: 'full' | 'partial' | 'none' | 'unknown';
  freshness: 'current' | 'stale' | 'unavailable';
  as_of: string | null;
  state_since: string | null;
  reason_code: string | null;
  pending_actions: Count;
  pending_by_kind: Partial<Record<'question'|'approval'|'decision'|'verification', Count>>;
  pending_request_ids: string[]; // referências limitadas; total exato não depende do preview
  has_more_pending_requests: boolean;
  pending_requests_cursor: string | null;
  running_sessions: Count;
  blocked_sessions: Count;
  awaiting_native_confirmation: boolean;
}
interface DeliverySemantics {
  version: 1;
  scope: 'turn' | 'handoff' | 'external_report';
  evidence: 'canonical' | 'reported';
  execution_outcome: 'succeeded'|'failed'|'cancelled'|'rejected'|'unknown'|'not_applicable';
  task_state: 'open'|'claimed'|'verifying'|'completed'|'rejected'|'cancelled'|'unknown'|'not_applicable';
  verification: 'approved'|'rejected'|'pending'|'unknown'|'not_applicable';
  verification_evidence_ref: string | null;
  cleanup: 'pending'|'complete'|'unknown'|'not_applicable';
  content_state: 'available'|'pending'|'not_captured'|'unavailable';
  historical: boolean;
  semantic_revision: string;
}
```

Não copiar estes tipos para produção ignorando o contrato real. Preencher source refs de prova com IDs opacos autorizados, não payloads nativos. Campos desconhecidos são explícitos; `not_applicable` não é sinônimo de falha de leitura.

### Colocação pós-decisão e compatibilidade do contrato

O contrato atual valida que todo card de harness em Needs You tenha `blocks_harness=true`. A espera pós-decisão precisa de uma distinção nova: **não colocar true artificialmente nesse campo para satisfazer o validador**, pois a aplicação/retomada ainda está sendo confirmada. Acrescentar uma razão de colocação separada, por exemplo `placement_reason=awaiting_native_confirmation`, junto à referência da decisão e do bloqueio anterior. O enum não concede uma ação humana nova.

Para a apresentação nova, validar Needs You quando houver `blocking=full` comprovado **ou** confirmação de retomada pertinente à mesma execução, sem trabalho paralelo comprovado. Neste segundo caso, `blocks_harness` pode continuar null, e `pending_actions` não inclui a decisão já respondida. O consumidor antigo deve continuar recebendo sua semântica histórica, sem uma combinação que seu validador rejeita.

**Estratégia de compatibilidade proposta:** a mesma família de endpoints pode aceitar uma versão de apresentação explícita (por exemplo `presentation_version=2`, nome a reconciliar no checkout). O consumidor antigo sem essa seleção mantém o contrato anterior. O novo frontend só seleciona a extensão após detectar capacidade; parsers de query, revisão e cursores incorporam a versão. Não criar uma segunda Home nem outra fonte de fatos. Se o repositório já possuir mecanismo equivalente de negociação, usá-lo e registrar o mapeamento. Não basta adicionar um campo opcional ao JSON se a distribuição das linhas quebra as invariantes do cliente antigo.

Exemplos de razão de colocação para a nova apresentação: `normal_monitoring`, `human_block_confirmed`, `awaiting_native_confirmation`, `monitoring_unconfirmed`. Os rótulos não substituem o estado de domínio nem devem ser persistidos como autoridade. Após logout ou mudança de geração, a referência anterior não pode sustentar indefinidamente a colocação.

## 8.3 Pipeline e algoritmo

```text
1. Autorizar operador e escopo.
2. Fixar relógio e leitura consistente.
3. Ler conexões/sessões/operações/pedidos/resultados, com cobertura conhecida.
4. Normalizar fatos por sessão/epoch/operação e prova de progresso/dependência.
5. Agregar status da conexão, sem usar previews ou IDs públicos como chave.
6. Derivar apresentação das entregas, separada da classificação de harness.
7. Distribuir cards e ocorrências com exclusividade/deduplicação.
8. Aplicar filtros visuais, ordenar e contar sobre relações autorizadas completas.
9. Paginar cards/filhos, gerar revisões e cursores.
10. Renderizar sem efeitos; detalhes e comandos revalidam suas fontes canônicas.
```

Filtros de agente/estado não podem eliminar uma sessão independente antes de decidir se um harness está totalmente bloqueado. Ler a evidência necessária para classificação de cada conexão candidata, sempre dentro da autoridade do operador. Não ampliar autorização para obter contexto.

## 8.4 Revisões e cursores

Mudanças reais de atividade, ações, decisão, verificação, conexão e validade devem invalidar as projeções afetadas. Uma atualização de `generated_at` sem mudança semântica não deve, por si só, contar como “novo conteúdo”. Separar revisão semântica de watermark/transporte/relógio de apresentação.

Heartbeat que muda a classificação connected→unknown é relevante; cada heartbeat sem mudança de classificação não precisa invalidar toda a paginação. Expiração precisa ser coberta por `next_refresh_at`/relógio mesmo sem evento. Campos usados na comparação de revisão devem ter ordenação determinística.

Cursores mantêm principal, Server, escopo, coluna/card, filtros e revisão próprios. Ao mudar revisão, ressincronizar a página com aviso discreto e preservar seleção pelo ID canônico. Não manter transação SQLite aberta entre páginas. Dados de um escopo antigo nunca substituem os do novo.

---

# 9. Atualização e painel contextual sem bloqueio artificial

## 9.1 Reproduzir antes de corrigir

Teste mínimo do problema identificado: abrir o painel de um harness; manter a resposta de polling semanticamente idêntica; avançar relógio pelo intervalo de refresh; verificar que ainda é possível abrir uma atividade e carregar sua página. Hoje a combinação de pausa com `hasPendingUpdate` pode impedir isso. Registrar reprodução e corte; se já estiver corrigido no novo HEAD, preservar a correção e adicionar regressão. [S07–S08]

## 9.2 Separar três estados de cliente

**Estado canônico consultado:** snapshot corrente, fontes, erros e revisões.

**Apresentação do quadro:** ordem visível, foco, expansões, scroll e pausa manual.

**Detalhe em interação:** alvo exato, consulta atual do alvo, rascunho, revisão da decisão e intenção de envio.

Abrir painel pode congelar a ordem do quadro, não congelar a possibilidade de consultar o alvo. Uma resposta idêntica não gera `hasPendingUpdate`. Uma mudança real pode avisar e ser aplicada por bloco sem remontar o formulário. Revogação e logout não são adiados pela pausa.

## 9.3 Gates de interação

Trocar o booleano global `blocked` por gates distintos:

- **Abrir leitura exata:** permitido com referência conhecida e permissão de leitura revalidável. Snapshot antigo provoca nova consulta do alvo, não fechamento obrigatório da Home.
- **Paginar relação:** exige cursor/revisão atual. Em conflito, atualizar o contexto no mesmo painel, sem misturar páginas antigas.
- **Decidir/agir:** exige destinatário, revisão, autorização e validade atuais e intenção idempotente, usando os componentes canônicos.

Um refresh em background ou fonte externa indisponível não desabilita indiscriminadamente todas as leituras nativas. Fonte antiga pode impedir uma ação específica, não todas as ações de todo o quadro por conveniência.

Atualização normal não entra em `state.error` nem em `role=alert`. Usar notice/status agrupado para mudança normal, warning para cobertura e alert para falha que realmente demanda atenção. Não imprimir erro interno cru para o usuário.

## 9.4 Abrir o contexto com o menor número de passos

Do card de harness:

1. Evento/ação com sessão exata: abrir seu alvo diretamente.
2. Há exatamente uma sessão elegível comprovada no conjunto completo: abrir acompanhamento dessa sessão.
3. Há várias sessões: abrir seletor curto dentro do mesmo painel, com objetivo, estado, projeto e horário; IDs nos detalhes.
4. Não há sessão ativa: abrir conexão e histórico conhecido, sem criar uma sessão.
5. Catálogo incompleto: não presumir unicidade porque o preview tem um item; pedir seleção/atualizar cobertura.

Não usar recência como seleção automática. Uma sessão bloqueada e outra executando continuam individualmente selecionáveis. Mover o card de coluna não fecha o painel nem muda o alvo.

Reutilizar `HomeEntryInspection`, `HomeSessionInspection`, o corpo de `SessionTerminalModal`/`RuntimeSessionTail`/`RuntimeHistory` e os controles canônicos. Uma camada de detalhe ativa, com possibilidade de maximizar; não empilhar modais. A saída é somente de leitura, não uma réplica interativa de TUI/shell.

## 9.5 Tempo real e acessibilidade

Reutilizar os streams do shell e o controlador existente; não abrir stream/poll por card. Debounce com teto e snapshot de recuperação cobrem eventos, retenção, reconexão e fontes sem evento. A frequência exata segue baseline medido; não aumentar polling para compensar uma modelagem incorreta.

Anunciar mudanças importantes sem roubar foco e sem narrar tokens/segundos. Dialog precisa ter nome, foco inicial adequado, navegação por teclado e retorno de foco ao card ou destino estável. Se o card se mover de coluna, localizar sua identidade no novo lugar; não focar a conexão “mais próxima”. Referências WAI sustentam mensagens de estado e comportamento de modal; testes reais continuam necessários. [W01–W02]

---

# 10. Segurança, compatibilidade e limites

As leituras da Home não alteram grants, fila, inbox, claims, provas de verificação ou runtime. O menu Avançado não é uma autorização nova. Resposta perdida recupera a mesma intenção; nenhuma regra de UI autoriza retry de tarefa incerta.

Autorização de prévia, contador, detalhe e artefato é a da fonte canônica. Não publicar conteúdo privado de prompts/tool arguments para explicar badges. Títulos vêm de metadados autorizados ou fallback determinístico. IDs em deep links são referências, não tokens de autoridade; URLs não contêm chaves, respostas ou paths privados.

Persistência nova não é exigida por padrão. Preferir extensões aditivas de DTO/projeção, respeitando clientes antigos. Se a prova de verificação/bloqueio faltar, registrar lacuna; não criar um workflow paralelo ou modificar recibos históricos. Novo campo no protocolo só depois de especificação/compatibilidade explícita.

A atualização do frontend empacotado deve acompanhar schemas e validadores. Testar cliente antigo/novo com capability adequada, retorno desconhecido e fallback existente. Não habilitar a Home nova por remover a flag de rollout como atalho.

---

# 11. Jornadas obrigatórias de referência

Estas jornadas orientam a implementação e os testes; são exemplos de comportamento esperado, não testes já realizados.

### J1 — Três harnesses terminam e continuam conectados

Codex, Pi e Claude em Active/Executando. Cada um encerra seu turno. As entregas aparecem em Results e, com prontidão comprovada, os três cards ficam Active/Idle. O total de conectados não cai e nenhum card vai para Results. Nova solicitação aceita deixa de ser Idle; início confirmado mostra Executando.

### J2 — Pergunta não bloqueante torna-se bloqueante

Codex faz uma pergunta, continua trabalho independente e mostra Resposta pendente em Active. A pergunta aparece em Needs You. Quando a execução atinge a dependência e há prova de pausa global, o mesmo card vai para Needs You e incorpora a pergunta. Não há duas ações duplicadas. Depois da resposta, mostra confirmação de retomada; só sai desse estado com evidência posterior.

### J3 — Duas sessões, uma bloqueada

Claude tem duas sessões do mesmo binding. Uma exige aprovação; a outra executa. O card permanece Active/Executando com Aprovação pendente e resumo das sessões. Needs You contém a aprovação exata. Se a segunda termina e a primeira continua bloqueada, o card inteiro migra. A entrega da segunda aparece em Results e não é perdida.

### J4 — Aprovação negada ou resposta perdida

Negação registra decisão, mas a UI espera o resultado do runtime. Resposta HTTP perdida mantém confirmação pendente e recuperação pela mesma intenção. Não reenviar decisão, não liberar grant, não assumir cancelamento nem conclusão. A segunda aba que vê decisão aplicada atualiza sem efetuar outro comando.

### J5 — Resultado de turno não conclui tarefa

Turno SUCCEEDED vinculado a handoff CLAIMED gera Resultado do turno disponível / Tarefa ainda não concluída. Em VERIFYING mostra Aguardando verificação. Em COMPLETED mostra Tarefa concluída. Só evidência de verificação positiva atual acrescenta Entrega verificada. Nenhum texto da saída é usado para inferir essa transição.

### J6 — Falha, cancelamento e limpeza

Resultados FAILED/CANCELLED ficam em Results com os rótulos apropriados. Sucesso com cleanup pendente preserva sucesso e mostra limpeza separada. Se há ação de recuperação do operador, Attention fornece a ocorrência; não apresentar retry genérico nem executar automaticamente.

### J7 — Escopo, conectividade e desconhecido

Dois projetos têm ID público reviewer. Em All projects, o nome do projeto distingue todos os cards. Uma conexão perde evidência: deixa de contar como Idle/conectada, continua acessível com estado não confirmado/desconectado e sua pergunta canônica não desaparece. Troca de projeto não mistura respostas lentas nem dados do outro escopo.

### J8 — Ler enquanto o sistema atualiza

Abrir a sessão inequívoca em um gesto, observar atividade por mais de dois intervalos de polling, responder no painel e receber nova entrega sem fechar/reabrir ou perder rascunho. Snapshot idêntico não gera aviso; mudança normal não vira erro; conflito de cursor atualiza o contexto sem trocar a sessão selecionada.

---

# 12. Mapa de implementação e etapas

| Área | Base a evoluir | Responsabilidade |
|---|---|---|
| Fatos batch | `src/okto_nexus/adapters/outbound/sqlite/home_entries.py` | Cobertura, conectividade, sessões, operações e pedidos sem consulta por card. |
| Estado e bloqueio | `src/okto_nexus/domain/home_harness_blocking.py` | Normalização e agregação conservadora de atividade/dependência humana. |
| Quadro | `src/okto_nexus/domain/home_harness_board.py` | Colocação exclusiva de harnesses, ações e entregas; counts/cursors. |
| Resultados | `src/okto_nexus/adapters/outbound/sqlite/home.py` | Fatos de outcome/claim/verification/content com proveniência. |
| Tipos/validação | `frontend/src/homeTypes.ts`, DTOs/handlers correspondentes | Campos aditivos e versões coerentes. |
| Atualização | `frontend/src/homeController.ts`, hook existente | Pausa, semântica de mudança, notices e consultas contextuais. |
| Cards | `HomeHarnessCard.tsx`, `HomeContextCards.tsx`, mapas de apresentação | Badges, projeto, tempo, CTA e compactação. |
| Painéis | `OperationalHome.tsx`, `HomeEntryInspection.tsx`, componentes de sessão/decisão | Abrir alvo exato, manter rascunho, leitura e ação com gates próprios. |
| Provas | `tests/ui_simplification/test_harness_blocking.py` e suites Home atuais | Ampliar fixtures, integração, browser e campanhas separadas. |

O Codex deve confirmar esses paths no HEAD. Extrair funções puras apenas quando necessário para testar/reutilizar; não criar um framework genérico de estados de dashboard.

| Etapa | Entrega | Gate |
|---|---|---|
| HST-00 | Baseline, fontes, contratos e fixtures | G0: mapa de evidência e semântica fechado. |
| HST-01 | Classificação Active/Needs You, Idle e confirmação | G1: status e colocação corretos sob concorrência/partição. |
| HST-02 | Semântica de Results e retenção | G2: nenhum sucesso/verificação/conclusão indevidos. |
| HST-03 | Badges e apresentação das três colunas | G3: informação compreensível e ações no contexto. |
| HST-04 | Controller e inspeção sem bloqueio artificial | G4: painel utilizável durante atualizações. |
| HST-05 | Segurança, acessibilidade, desempenho e integração | G5: evidências reproduzíveis e regressões controladas. |
| HST-06 | Campanhas, documentação, pacote e rollout | G6: entrega qualificada por escopo, sem publicação automática. |

Classificação e Results podem avançar em paralelo após contratos. A correção de refresh pode ser antecipada após fixture de reprodução, desde que o contrato compartilhado não seja quebrado. Testes de segurança não são adiados ao último gate.


# 13. Requisitos rastreáveis

| ID | Requisito obrigatório |
|---|---|
| HST-R01 | Manter somente Active, Needs You e Results na mesma Home, sem novo menu/inventário. |
| HST-R02 | Identificar o card por conexão canônica completa; sessões, agentes e nomes públicos não se confundem. |
| HST-R03 | Manter harness conectado sem trabalho em Active/Idle somente com evidência suficiente. |
| HST-R04 | Distinguir registro, conexão, sessão sob demanda, atividade e capacidade; não contar registro como conectado. |
| HST-R05 | Mover harness para Needs You apenas por bloqueio humano agregado comprovado; paralelismo mantém Active. |
| HST-R06 | Exibir badge do tipo de ação e apresentar cada ocorrência uma única vez como ação no quadro. |
| HST-R07 | Separar decisão enviada/registrada/aplicada de retomada; somente prova posterior confirma Working/Idle. |
| HST-R08 | Manter desconhecido, stale, falha de consulta e cobertura parcial explícitos, sem falsa ociosidade. |
| HST-R09 | Classificar Results por escopo de turno/tarefa/reporte, sem concluir tarefas por um turno bem-sucedido. |
| HST-R10 | Mostrar verificação aprovada somente com evidência específica da entrega/claim atual. |
| HST-R11 | Preservar falha, cancelamento, limpeza e conteúdo pendente como fatos diferentes; nenhum replay implícito. |
| HST-R12 | Agregar antes de paginar; deduplicar ocorrências/entregas e usar contadores de unidades definidas. |
| HST-R13 | Abrir sessão inequívoca diretamente; manter seletor explícito quando há múltiplas ou cobertura incompleta. |
| HST-R14 | Permitir acompanhamento durante refresh sem fechar/reabrir; preservar foco, rascunho e alvo exato. |
| HST-R15 | Usar ações/serviços canônicos, com autorização, revisão, idempotência e leitura sem efeitos. |
| HST-R16 | Preservar isolamento por Server/projeto/operador e não expor segredos/conteúdo privado nas prévias. |
| HST-R17 | Mostrar projeto em All projects, tempos honestos, badges acessíveis e cabeçalho compacto. |
| HST-R18 | Versionar DTOs/validadores e preservar fallback, recibos, dados e gates de rollout. |
| HST-R19 | Não refazer Core/Connector, Quick Connect ou navegação; preservar ciclo completo pelo terminal. |
| HST-R20 | Entregar evidências por teste/commit/ambiente, separando fixtures, browser e harness real. |

# 14. Backlog executável

Todos os itens começam como `TODO`. Implementação reaproveitada também precisa de prova para os critérios alterados. Estados permitidos: `TODO`, `IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`. Não promover uma tarefa a VERIFIED apenas por arquivo criado.

## Etapa HST-00

### HST-001 — Fixar baseline e conciliar trabalho em andamento

**Estado:** TODO. **Dependências:** nenhuma.  
**Requisitos:** HST-R18, HST-R19, HST-R20.  
**Áreas:** AGENTS.md/CI; branch e working tree; NEXUS_UI_R1/execution.

1. Registrar HEAD, versões, alterações locais e flags da Home; não fazer checkout/reset/clean destrutivo.
2. Comparar o SHA de referência com o checkout e marcar componentes reaproveitados; preservar ledgers e blockers anteriores.
3. Listar os comandos reais de teste/build, caminhos de evidências e responsáveis por arquivos em alteração concorrente.

**Aceite:** Baseline e mapa de drift verificáveis, sem alegação de instalação/qualificação não realizada.

**Cenários relacionados:** HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

### HST-002 — Mapear fontes de presença, bloqueio e verificação

**Estado:** TODO. **Dependências:** HST-001.  
**Requisitos:** HST-R03, HST-R04, HST-R05, HST-R07, HST-R10, HST-R16.  
**Áreas:** home_entries.py; execução e Attention canônicas; contratos dos adaptadores.

1. Rastrear os produtores de conexão, liveness, sessão, operações, native requests, decisões e verificação por claim/versão.
2. Documentar para cada método/adaptador a evidência de pause e resume; localizar a limitação atual de requestUserInput.
3. Distinguir o status de handoff da prova de verificação; registrar o que pode ser derivado e o que permanece desconhecido.
4. Fechar uma matriz de cobertura, validade, autoridade e sinais de invalidação por fonte.

**Aceite:** Mapa fonte→escopo→prova→validade→fallback, sem extrapolar contratos entre Codex/Pi/Claude.

**Cenários relacionados:** HST-T-B01 a HST-T-B12; HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14; HST-T-E01 a HST-T-E16; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

### HST-003 — Congelar DTOs e tabelas de decisão

**Estado:** TODO. **Dependências:** HST-002.  
**Requisitos:** HST-R02, HST-R05, HST-R06, HST-R09, HST-R12, HST-R18.  
**Áreas:** homeTypes.ts; domínio Home; validadores/API.

1. Especificar OperationalStatus, DeliverySemantics e contadores em contrato compartilhado ou equivalente existente.
2. Fechar os casos de multiple sessions, confirmação pós-decisão, offline/unknown, sem sessão e verificação ausente.
3. Planejar evolução aditiva dos campos e validadores estritos; manter mapeamento legado sem mudar significado silenciosamente.
4. Fechar a negociação de apresentação e placement_reason pós-decisão; não forçar blocks_harness=true para manter um card aguardando confirmação em Needs You.

**Aceite:** Um mesmo conjunto de fatos gera uma colocação e badges determinísticos; tipos completos sem any evasivo.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-B01 a HST-T-B12; HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14; HST-T-E01 a HST-T-E16; HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

### HST-004 — Criar fixtures e reproduzir o congelamento do painel

**Estado:** TODO. **Dependências:** HST-003.  
**Requisitos:** HST-R14, HST-R20.  
**Áreas:** tests/ui_simplification; tests/home_evolution; tests frontend/controller.

1. Criar fixtures pequenas das jornadas J1–J8 e casos de estado parcial/geração antiga.
2. Adicionar teste com relógio controlado: painel aberto e polling idêntico durante dois ciclos.
3. Registrar reprodução estática/browser quando disponível, sem apresentar fixture como execução de provedor.

**Aceite:** Fixture reproduzível e teste que falha no caminho defeituoso ou prova a correção já existente no novo HEAD.

**Cenários relacionados:** HST-T-F01 a HST-T-F14. O ledger contém os IDs individuais.

## Etapa HST-01

### HST-005 — Enriquecer fatos batch por conexão e sessão

**Estado:** TODO. **Dependências:** HST-003, HST-004.  
**Requisitos:** HST-R02, HST-R03, HST-R04, HST-R08, HST-R16.  
**Áreas:** sqlite/home_entries.py; EntryRelations/ConnectionContext.

1. Acrescentar fatos mínimos de conectividade e prontidão com generation/lease/freshness corretos, sem usar agregado por agente.
2. Ler operações/pedidos da relação autorizada completa antes do filtro visual; distinguir fonte indisponível de vazia.
3. Preservar a UoW curta e limites; não chamar host/provedor ou ler transcript por card.

**Aceite:** Prova de ausência e prova positiva distinguíveis; duas conexões do mesmo agente não compartilham estado indevidamente.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-B01 a HST-T-B12; HST-T-J01 a HST-T-J06. O ledger contém os IDs individuais.

### HST-006 — Normalizar dependência humana por operação

**Estado:** TODO. **Dependências:** HST-002, HST-005.  
**Requisitos:** HST-R05, HST-R06, HST-R08, HST-R15.  
**Áreas:** home_harness_blocking.py; metadados nativos e de coordenação.

1. Classificar pedido por tipo, destinatário e bloqueio com proveniência; método não suportado permanece unknown.
2. Validar sessão/epoch/operação/revisão e validade da ocorrência antes de usar prova de bloqueio.
3. Cobrir perguntas, permissões e handoffs quando houver contrato real; não inferir pause pelo formulário ou status OPEN.

**Aceite:** blocks_session e blocks_harness não se confundem; ocorrências humanas continuam disponíveis mesmo sem prova de pause.

**Cenários relacionados:** HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

### HST-007 — Implementar redução operacional Working/Idle e bloqueio agregado

**Estado:** TODO. **Dependências:** HST-005, HST-006.  
**Requisitos:** HST-R03, HST-R04, HST-R05, HST-R08.  
**Áreas:** domínio Home; classificador puro de status.

1. Implementar as regras das seções 3–5 para active work, Idle confirmado, fila, sem sessão e unknown.
2. Agregar todas as sessões da conexão: outra execução produtiva impede bloqueio total; sessão idle não impede.
3. Manter prova positiva conhecida com cobertura parcial alheia; negar inferências por ausência quando a fonte está incompleta.
4. Tratar cadastro/desconexão como exceções explícitas sem contabilizar conectados nem abrir quarta coluna.

**Aceite:** J1/J3/J7 atendidas; terminar turno não remove harness conectado nem transfere seu card para Results.

**Cenários relacionados:** HST-T-B01 a HST-T-B12; HST-T-C01 a HST-T-C12; HST-T-J01 a HST-T-J06. O ledger contém os IDs individuais.

### HST-008 — Modelar confirmação de aplicação e retomada

**Estado:** TODO. **Dependências:** HST-006, HST-007.  
**Requisitos:** HST-R07, HST-R08, HST-R15.  
**Áreas:** decisões/recibos atuais; home_harness_blocking.py.

1. Derivar a espera pós-decisão da mesma ocorrência/execução e seus recibos; não criar estado produtivo paralelo.
2. Exigir evidência causalmente posterior da mesma geração para sair de awaiting_confirmation.
3. Manter acompanhamento sem botão Responder duplicado; recusa/expiração/resposta perdida usa recuperação canônica.
4. Não permitir que RUNNING antigo entregue tarde vire prova de retomada.

**Aceite:** Decisão registrada, aplicada e execução retomada são distinguíveis; contagem humana aberta não inclui decisão já enviada.

**Cenários relacionados:** HST-T-D01 a HST-T-D14. O ledger contém os IDs individuais.

### HST-009 — Distribuir cards e ações sem duplicações

**Estado:** TODO. **Dependências:** HST-007, HST-008.  
**Requisitos:** HST-R01, HST-R02, HST-R05, HST-R06, HST-R12.  
**Áreas:** home_harness_board.py.

1. Preservar um card por conexão entre Active e Needs You, inclusive nas transições.
2. Incorporar ações próprias ao card bloqueado; manter somente a solicitação independente quando o harness continua.
3. Tratar pedidos compartilhados/sem vínculo sem any-owner incorreto; badges e sino referenciam o mesmo ID.
4. Manter entrega independente sem mover o harness para Results.

**Aceite:** Colocação e totais determinísticos sob múltiplas sessões/conexões; nenhum pedido some por dedup incorreta.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14. O ledger contém os IDs individuais.

### HST-010 — Atualizar contagens, revisões e cursores

**Estado:** TODO. **Dependências:** HST-009.  
**Requisitos:** HST-R08, HST-R12, HST-R18.  
**Áreas:** home_harness_board.py; home_entry_pages.py; homeTypes/API.

1. Definir totais de conectados/executando/Idle/ações/bloqueados/confirmando com unidades e exatidão explícitas.
2. Incluir mudanças semânticas nos fingerprints, excluindo mero generated_at/heartbeat sem mudança de estado.
3. Preservar cursores ligados a escopo/principal/revisão e invalidação por expiração; paginação não reduz totais.
4. Atualizar schemas e validação da resposta com os novos metadados.

**Aceite:** Totais não vêm de previews; revisões são estáveis para fatos iguais e mudam para transições relevantes.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-F01 a HST-T-F14; HST-T-J01 a HST-T-J06; HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

## Etapa HST-02

### HST-011 — Projetar semântica de entregas e tarefas

**Estado:** TODO. **Dependências:** HST-003, HST-005.  
**Requisitos:** HST-R09, HST-R11, HST-R12.  
**Áreas:** sqlite/home.py RESULTS/result_item; domínio Results.

1. Acrescentar escopo turn/handoff/report e classificar outcome/tarefa/conteúdo/cleanup em eixos separados.
2. Preservar IDs de entrega e current claim; tratar FAILED/CANCELLED/REJECTED e conteúdo pendente sem sucesso falso.
3. Não gerar entrega por silêncio, Idle ou texto; não usar LLM para classificar.

**Aceite:** Tabela de Results coberta por funções puras/consultas; handoff aberto não fica concluído por SUCCEEDED.

**Cenários relacionados:** HST-T-E01 a HST-T-E16. O ledger contém os IDs individuais.

### HST-012 — Vincular verificação à evidência correta

**Estado:** TODO. **Dependências:** HST-002, HST-011.  
**Requisitos:** HST-R10, HST-R16.  
**Áreas:** produtores de verificação/aceite; projeção Results.

1. Localizar o registro canônico de verificação positiva/negativa e sua versão/claim.
2. Adicionar prova segura ao DTO somente se existe; sem prova, manter tarefa concluída sem selo verificado.
3. Tratar historical_claim, rejeição e fontes conflitantes sem alterar estado produtivo nem inventar workflow.

**Aceite:** Entrega verificada só aparece com evidência da mesma entrega atual; COMPLETED isolado não basta.

**Cenários relacionados:** HST-T-E01 a HST-T-E16. O ledger contém os IDs individuais.

### HST-013 — Preservar retenção, artefatos e visto por ocorrência

**Estado:** TODO. **Dependências:** HST-011, HST-012.  
**Requisitos:** HST-R11, HST-R12, HST-R15, HST-R18.  
**Áreas:** Results/Attention; artifact refs; view preferences.

1. Reusar agrupamento persistido de artefatos, vistos/episódios e retenção da origem.
2. Atualização de verificação muda a entrega correlacionada, não multiplica registros ou apaga resultado histórico.
3. Não adicionar Home ao watermark global de mensagens; distinguir Recentes quando novos não são rastreáveis.

**Aceite:** Abrir Home/Results não resolve ação, ACK ou verificação; itens fora da página não são marcados vistos.

**Cenários relacionados:** HST-T-E01 a HST-T-E16; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

## Etapa HST-03

### HST-014 — Criar mapa de apresentação e badges reutilizáveis

**Estado:** TODO. **Dependências:** HST-003, HST-010, HST-013.  
**Requisitos:** HST-R06, HST-R09, HST-R17, HST-R18.  
**Áreas:** HomeHarnessCard.tsx; homePresentation/attentionPresentation; componentes badge.

1. Centralizar textos/ícones para atividade, tipo de ação e entregas no padrão linguístico atual.
2. Mostrar no máximo status e ação no caso comum; N ações abre contexto; unknown não coexiste com Idle confirmado.
3. Preservar dados técnicos no detalhe e nunca exibir enum SUCCEEDED como explicação única ao usuário.

**Aceite:** Mapas de apresentação testados por tabela; cores não são o único sinal.

**Cenários relacionados:** HST-T-D01 a HST-T-D14; HST-T-E01 a HST-T-E16; HST-T-G01 a HST-T-G08; HST-T-I01 a HST-T-I06. O ledger contém os IDs individuais.

### HST-015 — Evoluir cards Active e seus resumos

**Estado:** TODO. **Dependências:** HST-007, HST-010, HST-014.  
**Requisitos:** HST-R03, HST-R04, HST-R12, HST-R17.  
**Áreas:** HomeHarnessCard; HomeContextCards; OperationalHome.

1. Renderizar Working/Idle/queued/no-session/unknown com projeto em All projects e tempo semântico.
2. Mostrar pendência no mesmo card sem duplicar formulário; preservar conexão depois da entrega.
3. Exibir resumo de conectados e estados com totais do backend, sem prometer presença por registro.

**Aceite:** J1 e J7 reconhecíveis sem abrir detalhes; nenhum menu ou quarta coluna.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-B01 a HST-T-B12; HST-T-G01 a HST-T-G08; HST-T-J01 a HST-T-J06. O ledger contém os IDs individuais.

### HST-016 — Evoluir Needs You e ações no contexto

**Estado:** TODO. **Dependências:** HST-009, HST-014.  
**Requisitos:** HST-R05, HST-R06, HST-R07, HST-R15.  
**Áreas:** HomeHarnessSignalCard; AttentionInspection; controles nativos.

1. Renderizar ação independente ou harness bloqueado com o vocabulário correspondente.
2. Com uma ação abrir formulário exato; com várias mostrar lista paginada no mesmo painel.
3. Mostrar envio/confirmando/recusa e ações permitidas; não reapresentar botão decisório de ocorrência encerrada.
4. Revalidar por revisão atual e recuperar intenção existente em dupla submissão/resposta perdida.

**Aceite:** J2/J3/J4 completas e sem duplicação entre card, badge e sino.

**Cenários relacionados:** HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14; HST-T-H01 a HST-T-H10; HST-T-I01 a HST-T-I06. O ledger contém os IDs individuais.

### HST-017 — Evoluir cards Results com semântica visível

**Estado:** TODO. **Dependências:** HST-013, HST-014.  
**Requisitos:** HST-R09, HST-R10, HST-R11, HST-R17.  
**Áreas:** HomeHarnessSignalCard; ResultRow; result inspection.

1. Aplicar mensagens normativas de turno/tarefa/verificação/falha/cancelamento/cleanup/reporte externo.
2. Mostrar projeto/origem/tempo/preview autorizado e metadados de artefatos, sem payload completo inicial.
3. Permitir abrir resultado e continuar somente no contexto explicitamente associado.

**Aceite:** J5/J6 compreensíveis no card; verificação e sucesso nunca inferidos de texto ou outro claim.

**Cenários relacionados:** HST-T-E01 a HST-T-E16; HST-T-G01 a HST-T-G08; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

## Etapa HST-04

### HST-018 — Corrigir pausa e mudança semântica do controller

**Estado:** TODO. **Dependências:** HST-004, HST-010.  
**Requisitos:** HST-R14, HST-R18.  
**Áreas:** homeController.ts; useHomeOverview; OperationalHome.

1. Separar snapshot consultado, ordem apresentada e estado do painel; polling idêntico não marca update pendente.
2. Congelar movimento visual quando necessário sem proibir consulta atual do contexto.
3. Separar notice/warning/error; revisão normal não produz alert de falha.
4. Preservar invalidação de segurança e mudança real de geração independentemente da pausa.

**Aceite:** Reprodução passa em unidade e navegador; consulta periódica não exige fechar e reabrir.

**Cenários relacionados:** HST-T-F01 a HST-T-F14. O ledger contém os IDs individuais.

### HST-019 — Separar gates de leitura, paginação e ação

**Estado:** TODO. **Dependências:** HST-018.  
**Requisitos:** HST-R14, HST-R15, HST-R16.  
**Áreas:** OperationalHome blocked; HarnessActivityPanel; resolvers de detalhe.

1. Remover dependência exclusiva de um blocked global para toda interação.
2. Permitir leitura com revalidação de alvo exato; cursor inválido relê a relação no painel.
3. Manter validação fresca e autorização para comandos; falha parcial não libera nem bloqueia tudo indiscriminadamente.

**Aceite:** Leituras continuam úteis durante refresh; ações sensíveis seguem fechadas sem evidência atual.

**Cenários relacionados:** HST-T-F01 a HST-T-F14; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

### HST-020 — Abrir sessão exata diretamente quando inequívoca

**Estado:** TODO. **Dependências:** HST-003, HST-019.  
**Requisitos:** HST-R02, HST-R13, HST-R15.  
**Áreas:** HomeEntryInspection; connection target resolver; HomeSessionInspection.

1. Determinar unicidade com conjunto completo de sessões elegíveis, não preview ou recência.
2. Abrir target de evento específico diretamente; para card sem sessão oferecer conexão/histórico sem iniciar runtime.
3. Extrair/reutilizar visualização de tail/history sem novo PTY e sem modal aninhado.

**Aceite:** Um gesto para uma sessão conhecida; múltiplas continuam exigindo seleção explícita.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-G01 a HST-T-G08; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

### HST-021 — Melhorar seletor, foco e continuidade do painel

**Estado:** TODO. **Dependências:** HST-020.  
**Requisitos:** HST-R13, HST-R14, HST-R17.  
**Áreas:** HomeEntryInspection; AgentActionModal; homeNavigation.

1. Títulos/estado/projeto/host/tempo identificam opções; IDs ficam disponíveis em detalhe.
2. Preservar rascunho/revisão ao atualizar ou mover card; overlay tem chave independente da coluna.
3. Fechar devolve foco/scroll; trocar alvo/projeto respeita descarte e não transfere a resposta.

**Aceite:** Fluxo teclado/browser não perde texto ou muda destinatário por refresh ou navegação.

**Cenários relacionados:** HST-T-F01 a HST-T-F14; HST-T-G01 a HST-T-G08; HST-T-I01 a HST-T-I06. O ledger contém os IDs individuais.

### HST-022 — Tratar falha parcial e conectividade sem esconder pedidos

**Estado:** TODO. **Dependências:** HST-008, HST-019, HST-021.  
**Requisitos:** HST-R04, HST-R08, HST-R16.  
**Áreas:** Home source states; controller; cards e attention global.

1. Distinguir queda da leitura do Server de desconexão confirmada de uma conexão específica.
2. Manter pedido canônico alcançável quando liveness/telemetria fica desconhecida; não herdar bloqueio antigo como atual.
3. Limpar protegido em logout/401/403 e revalidar após reconexão, sem fallback para outro contexto.

**Aceite:** Não há empty state falso, perda de decisão ou falso Idle sob partição de rede.

**Cenários relacionados:** HST-T-B01 a HST-T-B12; HST-T-C01 a HST-T-C12; HST-T-F01 a HST-T-F14; HST-T-H01 a HST-T-H10. O ledger contém os IDs individuais.

### HST-023 — Compactar cabeçalho e remover ações indisponíveis do destaque

**Estado:** TODO. **Dependências:** HST-015, HST-016, HST-017, HST-021.  
**Requisitos:** HST-R01, HST-R17, HST-R19.  
**Áreas:** OperationalHome; HomeContextCards; HomeHarnessCard; composer existente.

1. Reduzir repetição de instruções e grandes indicadores; projeto/Add harness e resumo em hierarquia curta.
2. Escolher um refresh principal; Reconnect indisponível passa ao detalhe, sem implementar restart individual falso.
3. Nomear intenção de pedido como Pedir trabalho/Conversar reaproveitando protocolos e composer atuais.

**Aceite:** Home permanece com três colunas, sem outro inventário e com conteúdo útil antes de explicações repetidas.

**Cenários relacionados:** HST-T-G01 a HST-T-G08; HST-T-H01 a HST-T-H10; HST-T-I01 a HST-T-I06. O ledger contém os IDs individuais.

## Etapa HST-05

### HST-024 — Conferir atualização, cursores e corridas de fronteira

**Estado:** TODO. **Dependências:** HST-010, HST-018, HST-022.  
**Requisitos:** HST-R12, HST-R14, HST-R18.  
**Áreas:** SSE compartilhado; homeController; snapshots/cursores.

1. Validar início/reconnect/gap, eventos entre snapshot e assinatura, duplicatas e fora de ordem.
2. Revalidar validade por relógio/fallback; limitar bursts e não criar stream por card.
3. Proteger paginação e seleção em revisões novas sem restaurar conteúdo revogado.

**Aceite:** Eventos finais/novas perguntas não se perdem; revisão e cache não misturam scope/epoch.

**Cenários relacionados:** HST-T-F01 a HST-T-F14; HST-T-J01 a HST-T-J06. O ledger contém os IDs individuais.

### HST-025 — Executar revisão de autoridade e isolamento

**Estado:** TODO. **Dependências:** HST-016, HST-017, HST-019, HST-022.  
**Requisitos:** HST-R15, HST-R16, HST-R19.  
**Áreas:** API e resolvers; callbacks UI; auditoria de efeitos.

1. Cobrir usuários/scopes/epochs trocados, dupla submissão, receipt recovery e alvos adulterados.
2. Instrumentar GETs e cliques de leitura para provar ausência de efeitos produtivos.
3. Revisar exposição de preview/artefatos/URLs e limitar diagnósticos autorizados.

**Aceite:** Matriz adversarial passa no escopo declarado; nenhum atalho de UI amplia poder do operador.

**Cenários relacionados:** HST-T-A01 a HST-T-A08; HST-T-H01 a HST-T-H10; HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

### HST-026 — Qualificar acessibilidade e apresentação responsiva

**Estado:** TODO. **Dependências:** HST-021, HST-023.  
**Requisitos:** HST-R14, HST-R17, HST-R20.  
**Áreas:** browser real; AT quando disponível; temas.

1. Percorrer teclado/foco/modal e transição entre colunas; testar 360px e zoom 200%.
2. Validar nomes de ações, contraste/texto e anúncios agrupados; não anunciar cada timestamp/token.
3. Distinguir teste automatizado DOM de leitor de tela real e registrar o que não foi executado.

**Aceite:** Badges e decisões utilizáveis sem mouse; ambiente de acessibilidade efetivamente comprovado.

**Cenários relacionados:** HST-T-I01 a HST-T-I06. O ledger contém os IDs individuais.

### HST-027 — Medir e ajustar custo de leitura e atualização

**Estado:** TODO. **Dependências:** HST-010, HST-013, HST-024.  
**Requisitos:** HST-R12, HST-R20.  
**Áreas:** SQLite EXPLAIN; medição HTTP/DOM; fixtures volume.

1. Medir baseline e delta em 1/10/100 conexões e fixture ampliada descartável.
2. Registrar p50/p95, queries, payload, requests e fontes; evitar N+1 e leitura integral de histórico.
3. Só adicionar índices/caches necessários com prova; não dispensar meta anterior porque uma amostra passou.

**Aceite:** Relatório reproduzível com regressões explícitas; ausência de benchmark não vira PASS.

**Cenários relacionados:** HST-T-J01 a HST-T-J06. O ledger contém os IDs individuais.

### HST-028 — Executar jornadas integradas no navegador

**Estado:** TODO. **Dependências:** HST-023, HST-024, HST-025, HST-026, HST-027.  
**Requisitos:** HST-R01, HST-R03, HST-R05, HST-R07, HST-R09, HST-R14, HST-R20.  
**Áreas:** fixtures canônicas; navegador; J1–J8.

1. Executar as oito jornadas com backend real isolado e peers sintéticos onde adequado.
2. Capturar snapshots pareados HTTP/DOM e transições, inclusive polling aberto por mais de dois ciclos.
3. Registrar controles, cleanup de processos e limitações sem chamar fixture de campanha de provedor.

**Aceite:** Jornadas demonstram conceitos, não apenas existência de strings no código.

**Cenários relacionados:** HST-T-B01 a HST-T-B12; HST-T-C01 a HST-T-C12; HST-T-D01 a HST-T-D14; HST-T-E01 a HST-T-E16; HST-T-F01 a HST-T-F14; HST-T-G01 a HST-T-G08; HST-T-H01 a HST-T-H10; HST-T-I01 a HST-T-I06; HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

## Etapa HST-06

### HST-029 — Executar campanhas nativas consentidas ou registrar bloqueio preciso

**Estado:** TODO. **Dependências:** HST-028.  
**Requisitos:** HST-R03, HST-R05, HST-R07, HST-R19, HST-R20.  
**Áreas:** harnesses reais; Connector remoto conforme ambiente.

1. Obter consentimento, orçamento e ambientes descartáveis antes de inferência/instalação.
2. Executar J1/J2/J3 nos harnesses e topologias disponíveis, registrando IDs/recibos sem segredos.
3. Não presumir suporte dos três adaptadores ou remoto por um teste Codex local; deixar o restante NOT_RUN/BLOCKED.
4. Encerrar processos próprios, conferir ausência e preservar evidências sanitizadas.

**Aceite:** Qualificação por adaptador/OS/topologia real e distinta da implementação; nenhum PASS inventado.

**Cenários relacionados:** HST-T-L01 a HST-T-L04. O ledger contém os IDs individuais.

### HST-030 — Atualizar documentação e semântica pública

**Estado:** TODO. **Dependências:** HST-028.  
**Requisitos:** HST-R01, HST-R03, HST-R05, HST-R07, HST-R09, HST-R17.  
**Áreas:** guia Home; tooltips; docs do contrato; ledgers.

1. Documentar Active como harness conectado não bloqueado, Working/Idle e exceções explícitas.
2. Explicar dualidade Needs You e confirmação da retomada; Results distingue turno/tarefa/verificação.
3. Atualizar ajuda do card e fontes do read model, sem reescrever o onboarding ou documentação inteira.

**Aceite:** Operador entende a diferença entre ação, execução e entrega sem ler contratos técnicos.

**Cenários relacionados:** HST-T-G01 a HST-T-G08; HST-T-K01 a HST-T-K06; HST-T-L01 a HST-T-L04. O ledger contém os IDs individuais.

### HST-031 — Validar pacote e reversão não destrutiva

**Estado:** TODO. **Dependências:** HST-028, HST-030.  
**Requisitos:** HST-R18, HST-R19, HST-R20.  
**Áreas:** build frontend; wheel/sdist; flags rollout.

1. Construir/instalar pacote do corte final em ambiente descartável e conferir assets/types compatíveis.
2. Demonstrar fallback sem parar runtime/daemon, renomear ID, apagar dados ou repetir tarefa.
3. Preservar o gate atual de ativação padrão; autorização de implantação é separada da geração do pacote.

**Aceite:** Pacote reproduzível, smoke correto e rollback apenas de apresentação/contrato compatível.

**Cenários relacionados:** HST-T-K01 a HST-T-K06. O ledger contém os IDs individuais.

### HST-032 — Fechar evidências e gate de entrega

**Estado:** TODO. **Dependências:** HST-029, HST-030, HST-031.  
**Requisitos:** HST-R18, HST-R20.  
**Áreas:** execution ledger; release-report; aceite humano.

1. Associar todos os testes e tarefas a evidências do SHA correspondente; não zerar ledgers antigos.
2. Fazer aceite humano do significado dos cards e registrar entendimento real, sem aceitar em nome do usuário.
3. Separar Implementado, Qualificado por ambiente e Aprovado para default; relatar bloqueios remanescentes.
4. Não publicar release/deploy/merge protegido automaticamente.

**Aceite:** G6 tem decisão explícita baseada em evidências; limitações e próximos passos são rastreáveis.

**Cenários relacionados:** HST-T-K01 a HST-T-K06; HST-T-L01 a HST-T-L04. O ledger contém os IDs individuais.

# 15. Matriz de teste e aceite

Todos os cenários começam em `NOT_RUN`. Estados permitidos: `NOT_RUN`, `PASS`, `FAIL`, `BLOCKED`. Fixar relógios e usar barreiras para corridas, não sleeps frágeis. Título/conteúdo de fixture não prova harness real. Cada PASS registra comando, commit, ambiente, resultado e caminho de evidência.

## A. Identidade e escopo

### HST-T-A01 — Conexões da mesma identidade
**Dado:** Dois bindings do mesmo agent_id e harness.  
**Quando:** Projetar o quadro.  
**Então:** Dois cards distintos com alvos completos, sem fusão por nome.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A02 — ID público repetido entre projetos
**Dado:** Dois reviewer autorizados em A e B.  
**Quando:** Abrir All projects.  
**Então:** Projeto aparece em cada card e resumo; filtro A não mostra B.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A03 — Sessões múltiplas
**Dado:** Um binding tem sessões s1 e s2 com estados diferentes.  
**Quando:** Agregar e abrir.  
**Então:** Um card de conexão, duas sessões preservadas; nenhuma escolha por recência.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A04 — Owner de pergunta exato
**Dado:** Trabalho compartilhado por bindings A e B e pergunta nativa de A.  
**Quando:** Classificar ações.  
**Então:** B não recebe badge/pergunta como se fosse sua; apenas a origem comprovada é acionável.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A05 — Operação homônima entre executores
**Dado:** Mesmo operation_id em executores distintos.  
**Quando:** Gerar entrega/alvo.  
**Então:** Não há colisão de chave, recibo, revisão ou abertura.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A06 — Filtro não muda o bloqueio real
**Dado:** Sessão bloqueada e sessão independente da mesma conexão.  
**Quando:** Aplicar filtro visual de estado/agente.  
**Então:** Classificação usa o conjunto autorizado completo; filtro não cria bloqueio total falso.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A07 — Resultado tardio de escopo antigo
**Dado:** Consulta A lenta e seleção muda para B.  
**Quando:** Chega resposta de A.  
**Então:** Descartar pela geração; dados/contadores/formulários de B permanecem isolados.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-A08 — Pedido sem vínculo
**Dado:** Ocorrência humana válida sem conexão comprovada.  
**Quando:** Montar Needs You.  
**Então:** Uma solicitação com origem não confirmada, sem harness fictício e com ação revalidada.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

## B. Active, conexão e Idle

### HST-T-B01 — Execução confirmada
**Dado:** Sessão e operação correntes com progresso válido.  
**Quando:** Projetar harness.  
**Então:** Active/Executando; não depende de palavras na saída.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B02 — Fim com sessão viva
**Dado:** Último turno terminou e sessão segue pronta com fontes completas.  
**Quando:** Atualizar quadro.  
**Então:** Harness permanece Active/Idle e entrega aparece separada em Results.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B03 — Cadastro não é Idle
**Dado:** Binding registrado sem prova atual de conexão/sessão.  
**Quando:** Classificar.  
**Então:** Registered/estado não confirmado ou Sem sessão ativa; nunca Idle inferido.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B04 — Heartbeat do host não basta
**Dado:** Executor online mas sessão/harness sem evidência.  
**Quando:** Classificar.  
**Então:** Não afirmar processo vivo ou Idle apenas pelo host.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B05 — Fila não é ociosidade
**Dado:** Turno admitido aguardando execução.  
**Quando:** Classificar conexão.  
**Então:** Na fila/recebido conforme fonte, não Idle nem Executando sem início.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B06 — Envio incerto
**Dado:** Submissão com OUTCOME_UNKNOWN ou reconciliação.  
**Quando:** Fim do prazo de observação.  
**Então:** Estado não confirmado/recuperação; nunca Idle e nenhum envio automático.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B07 — Fonte parcial não prova ausência
**Dado:** Consulta de operações/sessões incompleta.  
**Quando:** Nenhum running na página visível.  
**Então:** Contagem parcial; não concluir Idle por página vazia.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B08 — Prova positiva com fonte alheia parcial
**Dado:** Execução corrente comprovada e falha só de observação externa.  
**Quando:** Atualizar.  
**Então:** Executando continua comprovado; cobertura externa parcial não transforma tudo em Idle ou desabilita leitura.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B09 — Prontidão expirada
**Dado:** Sessão era Idle, validade de evidência termina sem evento.  
**Quando:** Avançar relógio.  
**Então:** Badge passa a não confirmado; SSE live não mantém falsa atualidade.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B10 — One-shot encerrado
**Dado:** Turno termina e política fecha processo/sessão.  
**Quando:** Projetar.  
**Então:** Sem sessão ativa, não Idle nem erro inventado; nenhum runtime.start para melhorar o card.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B11 — Desconexão conhecida
**Dado:** Harness antes conectado perde liveness comprovadamente.  
**Quando:** Atualizar.  
**Então:** Card indisponível/desconectado permanece acessível, excluído do total conectado e sem quarta coluna.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

### HST-T-B12 — Outra conexão do agente trabalhando
**Dado:** Binding A parado e B produtivo, ambos mesmo agent_id.  
**Quando:** Agregar A.  
**Então:** B não torna A executando ou livre do seu bloqueio humano.  
**Nível:** unidade + contrato/SQLite. **Estado:** NOT_RUN.

## C. Colocação e paralelismo

### HST-T-C01 — Pergunta não bloqueante
**Dado:** Uma execução corrente e pergunta is_blocking=false comprovada.  
**Quando:** Projetar.  
**Então:** Card Active/Executando com Resposta pendente; solicitação independente em Needs You.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C02 — Bloqueio total
**Dado:** Única execução suspensa por pergunta atual decidível.  
**Quando:** Projetar.  
**Então:** Um card de harness em Needs You, pergunta incorporada, sem cópia em Active ou request solto.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C03 — Paralelismo real
**Dado:** Uma sessão bloqueada e outra executando no mesmo binding.  
**Quando:** Projetar.  
**Então:** Harness Active/Executando; request separado informa bloqueio parcial, não não bloqueante por natureza.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C04 — Independente termina
**Dado:** Cenário anterior e a outra sessão encerra.  
**Quando:** Ler fatos atuais.  
**Então:** Mesmo harness migra para Needs You; entrega da segunda sessão fica Results; pergunta não duplica.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C05 — Idle não invalida bloqueio
**Dado:** Uma sessão bloqueada e outra sessão ociosa.  
**Quando:** Agregar.  
**Então:** Ociosa não conta como trabalho independente; bloqueio total pode ser comprovado.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C06 — Fila com dependência desconhecida
**Dado:** Há blocker humano e uma operação queued sem prova de independência.  
**Quando:** Agregar.  
**Então:** Não inferir que fila consegue progredir; estado global desconhecido se falta prova.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C07 — Fila independente demonstrada
**Dado:** Runtime confirma atividade independente que pode progredir enquanto outra espera.  
**Quando:** Agregar.  
**Então:** Não rotular bloqueio total; mostrar estado produtivo/fila confirmado e pedido separado.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C08 — Não bloqueante vira bloqueante
**Dado:** Mesma pergunta passa a bloquear conforme nova prova canônica.  
**Quando:** Atualizar.  
**Então:** Mover card e incorporar o mesmo ID da ocorrência, sem nova pergunta.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C09 — Duas bloqueantes
**Dado:** Todas execuções produtivas esperam duas ações atuais.  
**Quando:** Projetar.  
**Então:** Card Needs You/Aguardando 2 ações; ambas alcançáveis, sem dupla contagem.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C10 — Coordenação não prova pause
**Dado:** Handoff ou pergunta do Nexus sem metadado de suspensão.  
**Quando:** Projetar.  
**Então:** Ação pode estar Needs You, mas bloqueio do harness permanece desconhecido; não mover por tipo.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C11 — Fonte do blocker fica stale
**Dado:** Prova de bloqueio expira e pedido canônico continua aberto.  
**Quando:** Atualizar.  
**Então:** Não afirmar bloqueio atual; preservar último estado rotulado e acesso ao pedido.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### HST-T-C12 — Ocorrência compartilhada
**Dado:** Uma decisão canônica relacionada a mais de uma conexão sem dono único.  
**Quando:** Projetar.  
**Então:** Uma ação independente com referências pertinentes; não duplicar formulários nem ocultar por any-binding bloqueado.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

## D. Ações, badges e confirmação

### HST-T-D01 — Pergunta simples
**Dado:** Um pedido humano aberto do tipo question.  
**Quando:** Renderizar card.  
**Então:** Resposta pendente ou Aguardando sua resposta, botão Responder para o alvo exato.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D02 — Permissão nativa
**Dado:** Pedido de aprovação de ferramenta com prova de bloqueio do adaptador.  
**Quando:** Renderizar.  
**Então:** Aprovação pendente/aguardando aprovação segundo escopo; sem aplicar regra exclusiva Codex a outro método.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D03 — Verificação humana
**Dado:** Entrega em verificação atribuída ao operador.  
**Quando:** Renderizar.  
**Então:** Verificação pendente e ação canônica; não bloquear harness por essa atribuição isolada.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D04 — Handoff ao agente
**Dado:** Handoff aberto atribuído a outro agente sem ação humana.  
**Quando:** Projetar.  
**Então:** Não criar pendência do usuário só por status OPEN/unread.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D05 — Vários tipos
**Dado:** Pergunta e aprovação abertas na mesma conexão.  
**Quando:** Mostrar preview limitado.  
**Então:** N ações pendentes; abrir revela todos os tipos com paginação e IDs únicos.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D06 — Decisão registrada não retoma
**Dado:** Harness bloqueado e operador responde com recibo registrado sem aplicação nativa.  
**Quando:** Atualizar.  
**Então:** Aguardando confirmação de retomada; zero nova resposta exigida; não Executando.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D07 — Recibo antigo entregue tarde
**Dado:** RUNNING da mesma operação, mas anterior causalmente à decisão.  
**Quando:** Receber após a resposta.  
**Então:** Não considerar retomada só por horário de chegada.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D08 — Retomada confirmada
**Dado:** Prova nativa causalmente posterior e da geração correta.  
**Quando:** Atualizar.  
**Então:** Mover para Active/Executando sem repetir envio; remover ação resolvida.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D09 — Termina após resposta
**Dado:** Resultado terminal e sessão viva/pronta confirmados após decisão.  
**Quando:** Atualizar.  
**Então:** Active/Idle e Results apropriado, sem inventar etapa Working intermediária.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D10 — Aplicação negada
**Dado:** Resposta recebida pelo Server, entrega nativa recusada.  
**Quando:** Atualizar.  
**Então:** Resposta não aplicada/inspeção; não marcar resolvida no runtime nem reenviar automaticamente.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D11 — Resposta HTTP perdida
**Dado:** Intenção de decisão existe e cliente recebe erro de rede.  
**Quando:** Recuperar.  
**Então:** Consultar a mesma intenção/recibo; não criar nova decisão.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D12 — Decisão em outra aba
**Dado:** Duas telas exibem mesma revisão; uma já decide.  
**Quando:** Outra tenta confirmar.  
**Então:** Revalidar, conflito claro ou recibo existente; sem ação duplicada ou mudança de destinatário.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D13 — Snooze e visto
**Dado:** Harness comprovadamente bloqueado com lembrete adiado/visto.  
**Quando:** Atualizar.  
**Então:** Permanece bloqueado; preferência não resolve pergunta e não autoriza retomada.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

### HST-T-D14 — Negação e expiração
**Dado:** Aprovação negada ou expirada, runtime ainda sem estado posterior.  
**Quando:** Projetar.  
**Então:** Não assumir cancelamento/Idle; expirado não aceita revisão antiga; ação de recuperação somente canônica.  
**Nível:** contrato + CLI/API/browser focal. **Estado:** NOT_RUN.

## E. Results e verificação

### HST-T-E01 — Turno simples sem tarefa
**Dado:** SUCCEEDED com saída capturada, sem handoff.  
**Quando:** Classificar.  
**Então:** Resposta disponível/Turno concluído; tarefa não aplicável, não Tarefa pendente.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E02 — Turno com tarefa aberta
**Dado:** SUCCEEDED ligado a handoff CLAIMED.  
**Quando:** Classificar.  
**Então:** Resultado do turno disponível e Tarefa ainda não concluída.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E03 — Entrega em verificação
**Dado:** Handoff atual VERIFYING com entrega.  
**Quando:** Atualizar Results.  
**Então:** Aguardando verificação; mesma entrega correlacionada, sem falso selo aprovado.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E04 — Concluído sem prova QA
**Dado:** Handoff COMPLETED, sem evidência independente de verificação.  
**Quando:** Classificar.  
**Então:** Tarefa concluída, sem Entrega verificada.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E05 — Verificado explicitamente
**Dado:** Conclusão e decisão positiva autorizada da mesma entrega/claim.  
**Quando:** Classificar.  
**Então:** Tarefa concluída + Entrega verificada com referência auditável.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E06 — Verificação de outro claim
**Dado:** Decisão positiva pertence à versão anterior.  
**Quando:** Classificar entrega atual.  
**Então:** Não herdar verificação; contexto histórico identificado.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E07 — Verificação negativa
**Dado:** Entrega atual rejeitada pelo verificador.  
**Quando:** Classificar.  
**Então:** Entrega não aprovada e estado da tarefa real; nenhuma reexecução/reabertura pela UI.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E08 — Turno falhou
**Dado:** FAILED produtivo com ou sem saída parcial.  
**Quando:** Montar Results.  
**Então:** Execução encerrada com falha; acesso à evidência, sem retry genérico.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E09 — Turno cancelado
**Dado:** CANCELLED confirmado.  
**Quando:** Montar Results.  
**Então:** Execução cancelada; saída parcial preservada se existir.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E10 — Handoff rejeitado
**Dado:** REJECTED do handoff sem resultado nativo equivalente.  
**Quando:** Montar Results.  
**Então:** Rejeição da tarefa/entrega, não sucesso nem cancelamento nativo por inferência.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E11 — Cleanup pendente
**Dado:** Produtivo SUCCEEDED e contenção/limpeza pendente.  
**Quando:** Classificar.  
**Então:** Sucesso/resultado separado da limpeza; não executar de novo.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E12 — Saída ainda não capturada
**Dado:** Recibo terminal confiável, output ausente.  
**Quando:** Montar card.  
**Então:** Execução encerrada + saída ainda não disponível; não afirmar entrega completa.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E13 — Reporte externo
**Dado:** Ocorrência explícita external_completion_unseen.  
**Quando:** Montar Results.  
**Então:** Término reportado, evidência externa identificada; não sucesso nativo nem verificação.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E14 — Silêncio e texto livre
**Dado:** Harness fica silencioso/Idle ou escreve terminei sem evento canônico.  
**Quando:** Projetar.  
**Então:** Nenhuma entrega inferida dessas condições.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E15 — Unknown não terminal
**Dado:** OUTCOME_UNKNOWN sem término comprovado.  
**Quando:** Projetar.  
**Então:** Não gerar novo resultado concluído; manter contexto/atenção autorizada, histórico confirmado intacto.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

### HST-T-E16 — Deduplicação e vistos
**Dado:** Uma entrega muda verificação e tem três artefatos, alguns itens fora da página.  
**Quando:** Atualizar e abrir Home.  
**Então:** Mesma entrega atualizada; artefatos por vínculo; não marcar itens invisíveis nem ACK de inbox; retenção canônica preservada.  
**Nível:** unidade + SQLite/HTTP + apresentação. **Estado:** NOT_RUN.

## F. Refresh, controller e contexto

### HST-T-F01 — Painel com polling idêntico
**Dado:** Painel aberto e dois snapshots semanticamente idênticos.  
**Quando:** Avançar dois intervalos de polling.  
**Então:** hasPendingUpdate não vira true por pausa sozinha; abrir atividade continua possível.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F02 — Mudança real durante leitura
**Dado:** Painel aberto e outro harness muda.  
**Quando:** Atualizar board.  
**Então:** Aviso discreto e revalidação apropriada; painel não fecha e sessão selecionada não muda.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F03 — Revisão igual com horário novo
**Dado:** generated_at/heartbeat muda sem mudança semântica.  
**Quando:** Publicar snapshot.  
**Então:** Não invalidar paginação nem anunciar novos resultados por isso apenas.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F04 — Mudança relevante de validade
**Dado:** TTL termina sem novo evento.  
**Quando:** Avançar relógio.  
**Então:** Reclassificar com novo estado; não depender exclusivamente de SSE.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F05 — Cursor muda
**Dado:** Página filha lida e relação muda.  
**Quando:** Pedir próxima página.  
**Então:** Conflito/releitura no mesmo painel, sem concatenar revisões nem exigir fechar/reabrir.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F06 — Formulário em edição
**Dado:** Usuário digita resposta e snapshots chegam.  
**Quando:** Atualizar.  
**Então:** Rascunho/foco/target/revisão revisada preservados; revalidação antes do envio.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F07 — Card muda de coluna
**Dado:** Painel mostra ocorrência; harness deixa Active.  
**Quando:** Publicar novo estado.  
**Então:** Uma identidade, painel independente da coluna, retorno de foco correto.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F08 — Burst de tokens
**Dado:** Muitos eventos de stream.  
**Quando:** Invalidar.  
**Então:** Atualizações agrupadas com teto, sem refetch completo por token e sem perder evento final.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F09 — Reconexão e lacuna
**Dado:** Cliente perde eventos e retoma SSE.  
**Quando:** Resincronizar.  
**Então:** Snapshot autoritativo cobre término/pendência; sem duplicar card ou decisão.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F10 — Falha de fonte alheia
**Dado:** Fonte externa indisponível, sessão nativa disponível.  
**Quando:** Abrir leitura da sessão.  
**Então:** Leitura exata permitida com revalidação; não bloquear toda Home por uma fonte.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F11 — 401/403 com pausa
**Dado:** Painel pausado e autorização revogada.  
**Quando:** Receber falha.  
**Então:** Limpar conteúdo protegido e desabilitar comandos, sem aguardar Apply updates.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F12 — Pausa manual
**Dado:** Usuário pausa apresentação.  
**Quando:** Tentar ação a partir de alvo conhecido.  
**Então:** Agentes seguem; leitura/ação revalidam, pausa não renova autoridade nem é runtime.pause.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F13 — Atualização normal não é erro
**Dado:** Revisão do board mudou sem falha.  
**Quando:** Renderizar notice.  
**Então:** Mensagem normal não entra em error/role alert persistente.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

### HST-T-F14 — Histórico do navegador
**Dado:** Abrir detalhe e usar voltar/avançar após refresh.  
**Quando:** Resolver rota.  
**Então:** Revalidar mesmo alvo; referência inválida não abre sessão mais recente.  
**Nível:** unidade com relógio/promessas + browser. **Estado:** NOT_RUN.

## G. Experiência e detalhes

### HST-T-G01 — Uma sessão única
**Dado:** Conjunto completo contém uma sessão elegível.  
**Quando:** Clicar Acompanhar no harness.  
**Então:** Abrir seu acompanhamento em um gesto, sem lista intermediária vazia.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G02 — Preview de um não é único
**Dado:** Preview tem uma sessão e has_more=true ou total desconhecido.  
**Quando:** Clicar.  
**Então:** Não escolher automaticamente; seletor/revalidação com cobertura explícita.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G03 — Várias sessões legíveis
**Dado:** Duas sessões conhecidas com títulos/estados.  
**Quando:** Abrir seletor.  
**Então:** Opções por objetivo/projeto/tempo; IDs disponíveis em detalhes.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G04 — Sem sessão ativa
**Dado:** Binding válido com política sob demanda.  
**Quando:** Abrir card.  
**Então:** Contexto e histórico, sem criar runtime/sessão ou consumir provedor.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G05 — Labels por projeto
**Dado:** All projects com IDs iguais.  
**Quando:** Renderizar harness/request/delivery.  
**Então:** Projeto aparece em todos os três tipos; projeto único pode omitir redundância.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G06 — Tempo honesto
**Dado:** Só created_at ou occurred_at disponível.  
**Quando:** Renderizar duração.  
**Então:** Usar recebido/atualizado há, não tempo de execução inventado.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G07 — Controles compactos
**Dado:** Home recorrente com atividade.  
**Quando:** Renderizar.  
**Então:** Três colunas, cabeçalho curto, sem Reconnect indisponível destacado ou novos menus/listas administrativas.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

### HST-T-G08 — Pedido e conversa
**Dado:** Usuário inicia interação básica.  
**Quando:** Escolher Pedir trabalho ou Conversar.  
**Então:** Rótulos orientados à intenção, handoff/message canônicos preservados e identidade operator.  
**Nível:** componente + navegador. **Estado:** NOT_RUN.

## H. Segurança e invariantes

### HST-T-H01 — Leitura sem efeitos
**Dado:** Snapshot, expandir card, abrir resultado.  
**Quando:** Inspecionar writes e comandos.  
**Então:** Nenhum grant, ACK, claim, turno, decisão, sessão ou teste criado; metadados de auth existentes documentados à parte.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H02 — Destino não é autoridade
**Dado:** URL/ID aponta a objeto de outro escopo.  
**Quando:** Resolver detalhe.  
**Então:** Negar conforme autorização; não vazar preview/contador pelo erro.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H03 — Campos privados
**Dado:** Prompts/segredos em origem não pública e labels hostis.  
**Quando:** Renderizar resumo/JSON.  
**Então:** Minimizar/redigir/escapar; sem executar HTML/ANSI nem expor credenciais.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H04 — Decisão do destinatário
**Dado:** Pergunta dirigida ao agente B, operador vê contexto.  
**Quando:** Interagir.  
**Então:** Não personificar B; somente ações permitidas ao usuário atual.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H05 — Uma ocorrência, dois atalhos
**Dado:** Mesmo pedido via badge e sino.  
**Quando:** Submeter concorrente.  
**Então:** Intenção/revisão canônicas impedem duplicação; badges não são filas novas.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H06 — Retry produtivo proibido
**Dado:** Resultado incerto ou falha com possível efeito.  
**Quando:** Abrir card.  
**Então:** Somente inspeção/recuperação existente; nenhum botão que reexecute às cegas.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H07 — Revogação de binding
**Dado:** Binding/sessão mudou após snapshot.  
**Quando:** Abrir/decidir.  
**Então:** Revalidar tupla/generation; não selecionar sucessor por nome.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H08 — Externo não altera runtime
**Dado:** Reporte idle/done externo.  
**Quando:** Projetar.  
**Então:** Não libera slot/claim, não conclui handoff nem renova grants.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H09 — Reconexão individual não simulada
**Dado:** Connector só oferece restart do daemon inteiro.  
**Quando:** Card de um harness.  
**Então:** Não executar restart como ação individual; limitação em detalhe.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

### HST-T-H10 — Raízes e daemon preservados
**Dado:** Atualização Home em instalação com trabalho CLI.  
**Quando:** Usar UI e reverter apresentação.  
**Então:** Nenhum remapeamento de diretório/identidade/checkpoint ou interrupção de daemon.  
**Nível:** API/SQLite + browser adversarial. **Estado:** NOT_RUN.

## I. Acessibilidade e responsividade

### HST-T-I01 — Teclado completo
**Dado:** Home com cards nas três colunas.  
**Quando:** Navegar sem mouse.  
**Então:** Badges acionáveis/buttons/painel têm foco e nome; nenhuma armadilha fora do modal.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

### HST-T-I02 — Retorno após movimento
**Dado:** Card origem mudou de Active para Needs You.  
**Quando:** Fechar painel.  
**Então:** Foco retorna ao mesmo ID canônico ou destino estável, não outro harness.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

### HST-T-I03 — Avisos sem ruído
**Dado:** Atualizações rápidas e relógios relativos.  
**Quando:** Usar leitor de tela.  
**Então:** Anunciar mudanças relevantes agrupadas, não tokens/segundos; sem mover foco.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

### HST-T-I04 — Estado não só por cor
**Dado:** Tema claro/escuro e percepção sem cor.  
**Quando:** Inspecionar badges.  
**Então:** Texto/ícone semântico distinguem Working/Idle/pendência/erro e estado não confirmado.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

### HST-T-I05 — Mobile e zoom
**Dado:** 360px e zoom 200% com nomes longos.  
**Quando:** Operar.  
**Então:** Colunas empilhadas, ações acessíveis sem overflow obrigatório de página; detalhe volta ao mesmo contexto.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

### HST-T-I06 — Modal e drafts
**Dado:** Pergunta em edição e Escape/troca de projeto.  
**Quando:** Fechar/trocar.  
**Então:** Guardar confirmação de descarte adequada; não copiar rascunho para outra ocorrência; logout limpa protegido.  
**Nível:** navegador + AT quando disponível. **Estado:** NOT_RUN.

## J. Contagens e desempenho

### HST-T-J01 — Unidades distintas
**Dado:** 2 harnesses, 3 ações, 2 entregas e trabalho compartilhado.  
**Quando:** Contar.  
**Então:** Contagem de cada unidade deduplicada; não somar como tarefas nem usar tamanho da página.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

### HST-T-J02 — Fontes parciais
**Dado:** Cobertura de operações incompleta.  
**Quando:** Contar Idle/connected/actions.  
**Então:** Totais desconhecidos/parciais explicitados; prova positiva não transforma ausência em zero.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

### HST-T-J03 — Sem N+1
**Dado:** Fixtures de 1,10,100 conexões.  
**Quando:** Medir queries.  
**Então:** Custo de consultas não cresce uma por card/sessão; sem fan-out de hosts/provedores.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

### HST-T-J04 — Histórico limitado
**Dado:** 1000 atividades abertas e 100000 eventos em fixture.  
**Quando:** Abrir overview e resultados.  
**Então:** Prévia/metadados paginados; sem carregar transcripts/payloads completos.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

### HST-T-J05 — Benchmark comparável
**Dado:** Mesmo hardware/dataset antes e depois.  
**Quando:** Executar amostras e calcular p50/p95.  
**Então:** Registrar números reais, query count, payload e comparação; amostra única não é p95.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

### HST-T-J06 — Expiração e revisão estável
**Dado:** Heartbeats sem mudança, depois stale real.  
**Quando:** Paginar e atualizar.  
**Então:** Sem churn de cursor por relógio irrelevante; expiração semântica invalida corretamente.  
**Nível:** SQLite instrumentado + benchmark. **Estado:** NOT_RUN.

## K. Compatibilidade, pacote e rollback

### HST-T-K01 — DTO e validator alinhados
**Dado:** Servidor adiciona novos estados/metadados.  
**Quando:** Consumir no frontend empacotado.  
**Então:** Backend/types/validadores concordam; apresentação pós-decisão nova não força blocks_harness=true; cliente antigo mantém distribuição histórica e fallback explícito.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

### HST-T-K02 — Recibos históricos intactos
**Dado:** Resultados/pedidos anteriores à feature.  
**Quando:** Projetar.  
**Então:** Não reescrever receipts/hashes/grants para adequar texto de UI.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

### HST-T-K03 — Fallback preservado
**Dado:** Flag/apresentação nova desabilitada com execução ativa.  
**Quando:** Reverter.  
**Então:** Home/controles antigos e sino acessíveis; sessões/IDs/dados continuam intactos.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

### HST-T-K04 — Artefato instalado
**Dado:** Wheel/sdist/frontend construídos do corte final.  
**Quando:** Instalar em home descartável.  
**Então:** Assets/schema corretos e smoke de leitura funcionando; não só dev server.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

### HST-T-K05 — CLI independente
**Dado:** Ciclo connect/work/answer/resultado já suportado.  
**Quando:** Executar sem abrir dashboard.  
**Então:** Nenhum passo web obrigatório nem alteração do preset/grant na reconexão.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

### HST-T-K06 — Ledger honesto
**Dado:** Fixtures/browser passam, AT/provedor não foram executados.  
**Quando:** Fechar relatório.  
**Então:** NOT_RUN/BLOCKED para o não executado, sem apagar pendências dos planos anteriores ou ativar default sem gate.  
**Nível:** contrato + instalação isolada. **Estado:** NOT_RUN.

## L. Campanhas integradas consentidas

### HST-T-L01 — Trio conectado
**Dado:** Codex, Pi e Claude suportados no ambiente, com consentimento.  
**Quando:** Executar e encerrar uma tarefa por conexão.  
**Então:** Resultados explícitos e cards Idle somente onde comprovado; reportar separadamente harnesses não executados.  
**Nível:** harness real / ambientes isolados. **Estado:** NOT_RUN.

### HST-T-L02 — Ciclo humano real
**Dado:** Harness com pergunta/aprovação nativa comprovada.  
**Quando:** Responder e acompanhar.  
**Então:** Bloqueio, decisão registrada, retomada confirmada e resultado correlacionados; sem inferir prova nativa de fixture.  
**Nível:** harness real / ambientes isolados. **Estado:** NOT_RUN.

### HST-T-L03 — Execução paralela real
**Dado:** Duas sessões compatíveis do mesmo harness.  
**Quando:** Bloquear uma e concluir a independente.  
**Então:** Active com request separado, depois Needs You, sem interrupção da irmã nem duplicação.  
**Nível:** harness real / ambientes isolados. **Estado:** NOT_RUN.

### HST-T-L04 — Fluxo remoto real
**Dado:** Server e Connector em hosts isolados autorizados.  
**Quando:** Acompanhar tarefa e decisão pela Home.  
**Então:** Mesmos badges/contextos e reconexão/falha honestas; sem tratar localhost sintético como prova multi-host.  
**Nível:** harness real / ambientes isolados. **Estado:** NOT_RUN.

# 16. Validação, qualificação e rollout

## 16.1 Comandos e provas

Ler scripts/CI do checkout antes de escolher comandos. Reusar suites Python de Home/ui_simplification e testes frontend existentes. A simples execução de testes Node não equivale a browser. Adicionar casos de interação ao harness de navegador já usado pelo projeto, com backend isolado e capture de rede/DOM. Nenhum comando deste plano autoriza usar credenciais reais ou inferência paga.

Estrutura sugerida de evidências, sob a pasta real de planos do repositório:

```text
plans/home_states/
  baseline.md
  source-map.md
  contracts.md
  adapter-blocking-matrix.md
  result-verification-evidence.md
  execution-ledger.json
  evidence/
  performance.md
  compatibility-report.md
  release-report.md
```

Manter evidências pequenas e sanitizadas. Não anexar DB pessoal, tokens, prompts privados, cookies ou artefatos com conteúdo confidencial. A campanha real exige autorização específica, teto de gasto e cleanup. Campo indisponível é registrado como lacuna de prova, nunca fabricado para passar um teste.

## 16.2 Desempenho

Medir o antes/depois no mesmo ambiente e dataset, com aquecimento e quantidade de amostras explícitos. Reportar p50/p95, tempo de query, número de queries, resposta em bytes e custo de refresh. Alvos iniciais propostos: primeira visão útil até 2 s e p95 de leitura até 500 ms em fixture/hardware documentados, preservando metas anteriores se mais rigorosas. Esses são alvos, não medições desta elaboração.

Usar fixtures 1/10/100 conexões, 1.000 atividades abertas e 100.000 eventos históricos. Evitar N+1, chamadas por host e transcript integral. Uma amostra rápida não qualifica p95 nem produção. Falhar uma meta exige diagnóstico e plano de correção ou decisão explícita do responsável; não apagar o alvo do ledger.

## 16.3 Compatibilidade e reversão

Conservar endpoints/consumidores atuais conforme o contrato. Extensões de DTO são negociadas ou aditivas; validar frontend antigo/novo. Caso algum índice/migration seja necessário, escolher a revisão correta do checkout e provar rollback lógico. Não restaurar banco antigo com executores em execução.

Desabilitar a nova apresentação mantém daemon, CLI, MCP, Attention, sessões, decisões e resultados. Uma preferência visual não renova autorização nem dispara execução. Manter acesso às perguntas/aprovações no fallback e no sino. Não ativar default ou publicar pacote automaticamente ao concluir testes.

## 16.4 Definição de pronto

Implementado: regras e caminhos funcionais, testes de domínio/HTTP/cliente e pacote no corte correto. Qualificado: jornadas reais e ambientes comprovados, identificados individualmente. Aprovado para default: decisão separada, com aceite humano e gates existentes respeitados.

O encerramento deve demonstrar J1–J8, ou registrar precisamente a parte não executada. São critérios eliminatórios: Idle por silêncio; todas as perguntas como bloqueantes; card de harness migrado para Results ao terminar; decisão registrada exibida como retomada; SUCCEEDED apresentado como tarefa verificada; refresh exigindo fechar/reabrir; nomes/IDs usados como autoridade; quarto menu/coluna para contornar a modelagem; testes sintéticos vendidos como prova nativa.

O relatório final identifica mudanças, fontes reaproveitadas, testes executados e não executados, dependências, migrações, performance, riscos, rollback e qualificação por adaptador/OS/topologia. Não declarar o plano inteiro concluído quando itens obrigatórios estão apenas documentados.

# 17. Instrução de entrada para o Codex

Usar `PROMPT_CODEX_NEXUS_HOME_ESTADOS_R1.md` deste pacote. O plano é consolidado e completo para esta evolução da Home; etapas incrementais são apenas a estratégia de implementação. Não depende de um patch de plano anterior.

# 18. Fontes fixadas e limites da análise

Fontes S01–S13 foram consultadas no SHA abaixo para preparar a especificação. Elas comprovam o conteúdo estático citado, não uma instalação funcionando. Relatos de testes no repositório pertencem aos autores e cortes desses relatórios. Fontes W01–W02 sustentam apenas as orientações de mensagens de estado/modal, não certificam acessibilidade do Nexus.

- **[S01] Versão e dependências:** `pyproject.toml`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/pyproject.toml

- **[S02] Quadro por harness, solicitações e entregas:** `src/okto_nexus/domain/home_harness_board.py`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/src/okto_nexus/domain/home_harness_board.py

- **[S03] Classificador corrente de bloqueio:** `src/okto_nexus/domain/home_harness_blocking.py`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/src/okto_nexus/domain/home_harness_blocking.py

- **[S04] Relações batch, bindings, sessões e metadados de pedido:** `src/okto_nexus/adapters/outbound/sqlite/home_entries.py`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/src/okto_nexus/adapters/outbound/sqlite/home_entries.py

- **[S05] Resultados de turnos e handoffs, resultados/vistos:** `src/okto_nexus/adapters/outbound/sqlite/home.py`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/src/okto_nexus/adapters/outbound/sqlite/home.py

- **[S06] Cards atuais, rótulos e botão de reconexão:** `frontend/src/components/home/HomeHarnessCard.tsx`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/frontend/src/components/home/HomeHarnessCard.tsx

- **[S07] Controller, pausa, revisões e avisos:** `frontend/src/homeController.ts`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/frontend/src/homeController.ts

- **[S08] Composição e painel de atividades:** `frontend/src/components/home/OperationalHome.tsx`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/frontend/src/components/home/OperationalHome.tsx

- **[S09] DTOs atuais do quadro:** `frontend/src/homeTypes.ts`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/frontend/src/homeTypes.ts

- **[S10] Contexto, seletor e controles de sessão:** `frontend/src/components/home/HomeEntryInspection.tsx`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/frontend/src/components/home/HomeEntryInspection.tsx

- **[S11] Relatório e limites da implementação corrente:** `NEXUS_UI_R1/execution/R3_IMPLEMENTATION_REPORT.md`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/NEXUS_UI_R1/execution/R3_IMPLEMENTATION_REPORT.md

- **[S12] Fixtures de bloqueio, paralelismo e decisão:** `tests/ui_simplification/test_harness_blocking.py`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/tests/ui_simplification/test_harness_blocking.py

- **[S13] Decisão anterior de composição por harness:** `NEXUS_UI_R1/execution/HARNESS_CARD_R3_AMENDMENT.md`.
  https://github.com/OktoLabsAI/okto-nexus/blob/f28a31a22436c366a4c8dbdf5e3b250d606a61be/NEXUS_UI_R1/execution/HARNESS_CARD_R3_AMENDMENT.md

- **[W01] W3C/WAI — Status Messages:** https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
- **[W02] W3C/WAI — Dialog (Modal) Pattern:** https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/

---
**Controle:** HOME-STATES-R1. Nenhuma alteração de repositório, teste do produto, campanha paga ou deploy foi efetuado ao elaborar este pacote. Todos os estados iniciais do ledger representam trabalho a executar e comprovar.
