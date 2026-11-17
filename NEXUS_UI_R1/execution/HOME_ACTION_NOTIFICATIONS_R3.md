# Solicitações e notificações na Home

Esta composição incorpora o esclarecimento do usuário: um pedido só desloca
o harness para Needs you quando há evidência de que o harness está parado
aguardando aquela resposta. Caso ele continue executando, o harness permanece
em Active e a solicitação aparece separadamente em Needs you.

| Coluna | Unidade visível | Acesso principal |
|---|---|---|
| Active | Harness registrado, com estado factual e prévia curta de eventos | Inspecionar execução; reconectar pelo fluxo canônico disponível |
| Needs you | Harness comprovadamente aguardando o usuário, com pedidos dentro; ou pedido independente quando o harness continua | Responder pergunta, revisar aprovação/handoff ou inspecionar recuperação, conforme ações permitidas |
| Results | Entrega com término reportado, identificada pelo harness/origem comprovada | Ver entrega, arquivos e estado de verificação |

O mesmo harness pode ter uma execução em Active, um pedido em Needs you e uma
entrega anterior em Results. São entidades distintas com IDs próprios. Não há
duplicação de um card de trabalho/sessão para preencher as colunas. A UI não
deduz o estado de execução pela existência de uma pergunta.

Limitação atual de reconexão: abrir o contexto registrado é leitura, não uma
reconexão. A UI/HTTP atual não oferece uma capacidade de reconectar somente
aquela instância. O comando reconnect do Connector reinicia o daemon inteiro
e afeta todas as suas conexões. O card não o executa como ação individual nem
inventa alias/perfil/sessão; a indisponibilidade individual é explícita e
acessível. Inspeção continua disponível pelo contexto exato.

## Conteúdo de um pedido

Um pedido informa quem está pedindo, projeto, resumo da ação esperada e se o
bloqueio é confirmado, não bloqueante ou desconhecido. O botão abre o contexto
canônico exato para revisão; não aprova ou executa por abrir o card. IDs, revisão,
escopo e permissões permanecem no protocolo/detalhe, sem poluir o overview.

| Origem | Quando entra em Needs you | Ação apresentada |
|---|---|---|
| Pergunta nativa | Destinatário humano atual e ocorrência vigente com ação permitida | Revisar/responder a pergunta exata |
| Aprovação | Aprovação atual dirigida ao usuário, com autoridade válida | Revisar a solicitação antes de decidir |
| Handoff | Encaminhamento, verificação ou escalonamento que admite ação do usuário atual | Abrir o handoff ou revisar a verificação canônica |
| Erro/resultado incerto/recuperação | Há uma ação canônica de inspeção ou recuperação para o usuário | Inspecionar o registro retido; nunca repetir automaticamente |
| Handoff entre agentes ou aviso informativo | Não vira pedido humano apenas por existir | Evento informativo no contexto/sino, sem fabricar autoridade |

Nenhuma categoria visual concede autoridade. Handoff OPEN, sem responsável ou
antigo não é automaticamente um pedido de aprovação humana. `allowed_actions`,
destinatário, resolução, freshness e revisões canônicas continuam determinantes.

## Ciclo e notificação

1. Um pedido vigente aparece na Home e no sino com o mesmo ID/revisão. Atualização
   compartilhada invalida o snapshot; não cria uma fila ou polling por card.
2. Abrir é leitura. Visto e adiar são preferências, não aprovação, aceite de
   resultado ou prova de que o harness voltou a executar.
3. Resposta/decisão passa pelo inspetor canônico e CAS. Resposta recebida pelo
   Nexus não prova aplicação nativa ou retomada: a interface pode aguardar
   confirmação, sem anunciar RUNNING ou sucesso por inferência.
4. Resolução, expiração ou revogação atualiza as duas superfícies. Resposta
   perdida conserva o mesmo pedido e sua recuperação, sem replay automático.
5. Adiar um lembrete não muda o estado factual de um harness ainda bloqueado.
   Ele continua identificado como aguardando resposta, com a preferência de
   lembrete explícita quando disponível.

Notificações de ação e atualizações informativas permanecem distinguíveis.
Um contador de pedidos não é um contador de harnesses nem de resultados. Os
totais vêm do backend completo/autorizado, não do número de cards carregados.

## Evidência de bloqueio e conclusão

A classificação usa metadados seguros já persistidos, sem ler prompts, segredos
ou transcripts no carregamento inicial. Uma pergunta de uma sessão não bloqueia
outra execução produtiva da mesma instância. Só cobertura completa e provas
compatíveis de escopo/turno/revisão permitem declarar o harness aguardando o
usuário. Ausência ou conflito dessa prova é desconhecido.

Término reportado permite listar a entrega, mantendo separados reporte externo,
sucesso nativo, limpeza pendente, verificação e aceite. Um resultado não inicia
outro trabalho e não renova grant. Origem sem vínculo comprovado não é atribuída
ao último harness usado: permanece alcançável no básico/sino com essa limitação.

## Cenários necessários para qualificar a composição

- Uma execução com pergunta bloqueante confirmada: harness em Needs you.
- Duas sessões do mesmo harness, uma bloqueada e outra produtiva: harness em
  Active e pedido em Needs you, com contexto próprio preservado.
- Pedido não bloqueante ou bloqueio desconhecido: não declarar o harness parado.
- Pedido de uma conexão não bloqueia outra conexão do mesmo agente/Codex.
- Handoff dirigido ao usuário oferece apenas a ação canônica; handoff informativo
  entre agentes não ganha aprovação humana fictícia.
- Visto, adiado, decisão 202, expiração e revogação não produzem execução ou
  confirmação falsa; incerteza não causa replay.
- Término com outra execução ativa: entrega em Results e harness em Active,
  sem afirmar aceite nem sucesso nativo para reporte externo.
- Paginação e mudança de revisão não duplicam pedidos/entregas ou misturam
  projeto, principal, instância e sessão; fontes parciais mantêm totais incertos.

Os cenários acima são critérios a exercitar. Este documento não declara PASS,
aceite humano, campanha real, release ou ativação padrão.
