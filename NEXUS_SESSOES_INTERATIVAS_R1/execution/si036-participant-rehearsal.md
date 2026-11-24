# SI-036 · Ensaio do ambiente para o participante

O ensaio automatizado usou um wheel construído a partir da branch publicada `feature/v0.3.8`, na revisão `e286762f`. Um pedido de revisão de remessa foi enviado pela API normal antes de o navegador abrir. O projeto já estava selecionado na Home e o Pi já atendia o pedido quando a primeira tarefa começou. Essa preparação evita que participante tenha de escolher uma versão da Home, configurar um harness ou criar o trabalho inicial.

A automação no Edge encontrou o texto do pedido pelo card, colocou o pedido de conferir o endereço na fila e retornou pelo mesmo card. O Nexus registrou um único envio para o próximo turno. As duas respostas apareceram na ordem na mesma sessão, e o processo Pi saiu após o encerramento canônico. O ambiente descartável usou Pi 0.87.1 e respostas determinísticas, sem chamadas externas. [Resultados e hashes](si036-participant-rehearsal.json)

Na rodada humana, o facilitador abre a Home já preparada e apresenta uma tarefa por vez. A primeira pede que a pessoa explique o que o colaborador está atendendo. A segunda pede que envie **Confira também o endereço de entrega** e diga o que a tela indica sobre o momento da resposta. A terceira pede que volte à Home, encontre a conversa e identifique os dois resultados. A primeira resposta fica retida até a pessoa relatar o que entendeu da fila e retornar à conversa. O texto do pedido inicial só aparece no cenário, para que a pessoa o encontre na interface.

O aceite humano continua pendente. Esta etapa atualiza evidências, dispensa migração e pode ser revertida pelo commit de registro.

## Revalidação do candidato atual

A revisão `579bdef6` passou no Edge com o dashboard do wheel e o Connector em loopback nesta máquina. A Home abriu com o projeto selecionado e mostrou **Revisão de remessa** em andamento. O ensaio colocou a mensagem seguinte na fila, saiu do painel e voltou pelo mesmo card. A conversa exibiu as duas respostas, cada uma uma vez. O banco confirmou uma sessão, dois resultados e nenhuma violação de chave estrangeira. O encerramento confirmou a saída do Pi, o fechamento do listener descartável e a remoção do arquivo temporário de autenticação do navegador. [Resultados e hashes](si036-participant-rehearsal.json)

O roteiro humano foi sincronizado com os mesmos wheels e a mesma preparação do projeto. A revalidação acima é automatizada. O aceite do participante continua pendente.

## Revalidação em `b4bb0031`

O Edge repetiu a jornada com o dashboard empacotado, Pi 0.87.1 e Connector na mesma máquina Windows. O roteiro selecionou **Projeto Remessas** e confirmou que **Assistente de remessas** já exibia atividade na Home. A automação encontrou o pedido, enfileirou a mensagem seguinte, reencontrou a conversa pelo mesmo card e conferiu as duas respostas na ordem esperada.

A auditoria verificou uma abertura nativa, dois resultados da mesma sessão e um fechamento canônico. O servidor descartável saiu e o arquivo temporário de autenticação foi removido. A primeira rodada abriu o navegador, mas o processo de lançamento bloqueou o roteiro. Na rodada aprovada, a abertura do Edge e as interações ocorreram em processos separados.

O cenário usa respostas simuladas em loopback. O aceite do participante e a validação com leitor de tela no Windows permanecem em aberto. A atualização de evidências dispensa migração. [Comandos, resultados e hashes](si036-participant-rehearsal.json)
