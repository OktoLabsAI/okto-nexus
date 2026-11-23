# SI-036 · Ensaio do ambiente para o participante

O ensaio automatizado usou um wheel construído a partir da branch publicada `feature/v0.3.8`, na revisão `e286762f`. Um pedido de revisão de remessa foi enviado pela API normal antes de o navegador abrir. O projeto já estava selecionado na Home e o Pi já atendia o pedido quando a primeira tarefa começou. Essa preparação evita que participante tenha de escolher uma versão da Home, configurar um harness ou criar o trabalho inicial.

A automação no Edge encontrou o texto do pedido pelo card, colocou o pedido de conferir o endereço na fila e retornou pelo mesmo card. O Nexus registrou um único envio para o próximo turno. As duas respostas apareceram na ordem na mesma sessão, e o processo Pi saiu após o encerramento canônico. O ambiente descartável usou Pi 0.87.1 e respostas determinísticas, sem chamadas externas. [Resultados e hashes](si036-participant-rehearsal.json)

Na rodada humana, o facilitador abre a Home já preparada e apresenta uma tarefa por vez. A primeira pede que a pessoa explique o que o colaborador está atendendo. A segunda pede que envie **Confira também o endereço de entrega** e diga o que a tela indica sobre o momento da resposta. A terceira pede que volte à Home, encontre a conversa e identifique os dois resultados. A primeira resposta fica retida até a pessoa relatar o que entendeu da fila e retornar à conversa. O texto do pedido inicial só aparece no cenário, para que a pessoa o encontre na interface.

O aceite humano continua pendente. Esta etapa atualiza evidências, dispensa migração e pode ser revertida pelo commit de registro.
