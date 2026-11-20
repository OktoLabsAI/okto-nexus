# SI-T-H18 — Encerramento explícito do Connector

O Nexus, Connector e Core instalados abriram um turno no app-server
Codex 0.157.0. O R4 usou loopback no Windows e o provedor simulado reteve a
resposta. Um processo separado do CLI executou `daemon stop` contra o
estado descartável do daemon.
[Comandos, verificações e hashes](si037-controlled-connector-stop.json)

1. O CLI entrou em `stopping` com o mesmo daemon. O app-server e o turno
   admitido continuaram vivos durante a drenagem. O ensaio liberou a
   resposta e o Nexus registrou a conclusão do turno original.
2. O CLI retornou `DRAINED`. O handle do processo confirmou a saída do
   app-server, e o daemon liberou a instância. O journal registrou um
   lançamento e o Nexus reteve o resultado original. A drenagem foi normal.
3. Depois da parada, a API ainda entregou o resultado da sessão exata.
   O catálogo apresentou o controle, o envio e a reorientação como
   indisponíveis, assim como a interrupção. A linha de sessão e a lease
   permaneceram registradas no primeiro ensaio. A API combina o registro da sessão e da lease com o estado da conexão. Com o host desconectado, os controles ficam indisponíveis.

Passaram os dois ensaios de processo e 23 regressões instaladas de
drenagem e ciclo de vida. Cada ensaio usou um único pedido ao simulador
e zero chamadas a provedores externos. O teste rodou o daemon em processo
descartável com o IPC real e o app-server em processo próprio. A
qualificação de uma tarefa do Agendador ou de um desligamento do Windows
continua fora deste ensaio.

O ledger registra `PASS` para SI-T-H18. A alteração registra evidência,
dispensa migração e pode ser revertida pelo próprio commit.
