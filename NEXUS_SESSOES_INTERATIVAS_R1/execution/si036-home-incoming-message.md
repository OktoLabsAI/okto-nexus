# SI-036 · Mensagem recebida e continuidade pela Home

A conversa da sessão agora mostra o pedido recebido como **Incoming message** quando o Nexus confirma que o eco nativo pertence à entrega canônica daquela sessão. A projeção conserva o evento original e o cursor. Entradas diretas, ecos ambíguos e mensagens sem o vínculo exato mantêm a apresentação anterior.

No Edge, o ensaio enviou um pedido pela Home e encontrou a conversa pelo card do colaborador. Com o primeiro turno em andamento, colocou uma segunda mensagem na fila, fechou o painel e voltou pelo mesmo card. A fila aparecia como pendente antes do despacho. A conversa exibiu os dois pedidos e os dois resultados na ordem, uma vez cada, com o texto do pedido inicial livre das instruções de transporte. O banco e o processo Pi confirmaram uma sessão, dois turnos e o encerramento canônico. [Resultados e hashes](si036-home-incoming-message.json)

O primeiro roteiro abriu o card enquanto a sessão ainda iniciava. Na rodada concluída, o navegador voltou à Home depois que o painel devolveu o foco ao card. A retomada usou a mesma sessão e conservou a mensagem já enfileirada. A automação usou uma instância de Edge descartável.

Passaram 25 regressões da transcrição no código e no wheel, 423 testes Node, o build do dashboard e as verificações do wheel e do sdist. O Edge usou Pi 0.87.1, Connector R4 em loopback e respostas determinísticas. O aceite humano, a campanha e o teste em outra máquina têm gates próprios.

## Tarefas para o participante

1. No projeto de teste, encontre o pedido que o colaborador está atendendo e diga em uma frase sobre o que ele está trabalhando.
2. Peça para conferir mais um detalhe depois do pedido atual. Diga o que na tela indica quando a sua mensagem será atendida.
3. Volte à Home, encontre a conversa novamente e diga se conseguiu distinguir a primeira resposta da segunda.

Esta mudança dispensa migração. Para reverter, reverta o commit do Nexus com a projeção e o dashboard e use o wheel anterior.
