# SI-T-H17 — Continuidade após fechar o navegador

O Edge abriu a conversa exata de um turno Codex pendente. Os três wheels
instalados serviram a Home, a API e a conexão de acompanhamento por SSE.
O Connector executou o app-server Codex 0.157.0 em Windows, com R4 e um
simulador de respostas em loopback.
[Comandos, hashes e checkpoints](si020-browser-exit-preserves-work.json)

1. O teste fechou o navegador descartável com o turno em andamento.
   O servidor observou as desconexões e ficou sem conexões SSE para
   aquela conversa. O mesmo processo do app-server continuou vivo.
   A concessão manteve a revisão e a contagem de usos. A lease efetiva
   preservou a autorização, o proprietário e a geração.
2. O simulador liberou a resposta com o navegador fechado. O Nexus
   gravou a conclusão e o resultado do turno original. Uma nova
   instância do Edge abriu a mesma conversa e exibiu o pedido original
   e a resposta, uma vez cada.
3. O SQLite e o journal confirmaram um único lançamento do app-server,
   um turno, um resultado, uma concessão vigente e zero entradas
   enfileiradas. O fechamento canônico posterior encerrou o processo.

Passaram o ensaio no Edge e 24 regressões instaladas de autorização,
anexação, stream e fila. As primeiras tentativas ajustaram a observação
do SSE, a correlação da resposta pelo registro canônico e a leitura da
lease efetiva durante a renovação. Uma preparação falhou antes de
lançar o app-server. O journal confirmou zero lançamentos e a
repetição usou outro projeto descartável. A execução concluída usou
um pedido ao simulador e zero chamadas a provedores externos.

O ledger registra `PASS` para SI-T-H17. A alteração registra evidências,
dispensa migração e pode ser revertida pelo próprio commit.
[A parada explícita foi verificada separadamente](si037-controlled-connector-stop.md)
