# SI-032 · Saída abrupta do visualizador Claude com escrita

O ensaio passou com o CLI instalado no Windows, um Connector na mesma máquina e Claude Code 2.1.328 em ConPTY. Enquanto o primeiro turno estava em andamento, a API web e o compositor colocaram duas mensagens na fila. O roteiro encerrou somente o processo do visualizador. O servidor liberou a escrita e recuperou o recibo original, ainda pendente na mesma sessão.

Um segundo visualizador recebeu a escrita sem transferência manual. O turno original terminou enquanto ele estava anexado. As duas mensagens pendentes chegaram em ordem ao mesmo processo. A auditoria confirmou três resultados distintos, uma abertura nativa, um fechamento canônico e a integridade dos bancos. O modelo recebeu pedidos apenas em loopback.

As rodadas anteriores tiveram recusas de abertura ou confirmação do canal. Uma delas completou a fila e a reanexação, mas a captura do terminal ficou sem uma correspondência literal para o primeiro resultado. A rodada final verificou os quadros retidos do terminal e conferiu o texto de cada resultado nos recibos canônicos e no SQLite. [Comandos, resultados e limites](si032-claude-abrupt-writer-exit.json)

A prova complementa SI-T-H09 para a combinação executada. SI-T-G03 conserva o gate de campanha. A atualização de evidências dispensa migração e pode ser revertida pelo commit do Nexus.
