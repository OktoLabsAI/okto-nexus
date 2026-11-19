# SI-022 e SI-032 — Concessão produtiva na retomada do canal do Connector

No ensaio inicial com Pi real, o socket R4 foi substituído com a mesma identidade e geração. O banco marcou a concessão aplicada como `SUPERSEDED` ao limpar o proprietário durante a desconexão. A regressão no wheel anterior reproduziu a alteração de estado.

A migração 186 preserva a concessão nas duas transições da retomada autenticada do mesmo canal. O servidor grava a prova temporária e solta o proprietário na mesma transação. Para reassumir o canal, o Connector precisa apresentar a identidade, a geração e o ticket original vigentes. Durante o intervalo sem proprietário, o servidor recusa os efeitos daquele canal. Uma concessão revogada permanece revogada. Uma abertura com geração nova aplica a invalidação normal das concessões anteriores.

A prova de migração aplicou o wheel em uma cópia SQLite de schema 185, reaplicou a inicialização e verificou a integridade. As linhas de sessão, concessão, operação, recibo e fila permaneceram iguais. O rollback de código mantém a migração conhecida pelo pacote e restaura a invalidação anterior por migração à frente. Para instalar diretamente um wheel anterior, use um backup compatível com o schema anterior.

No wheel corrigido, o teste cortou o WebSocket R4 enquanto o Pi 0.87.1 executava um turno sob ConPTY. O primeiro editor saiu e o Connector reconectou com a mesma geração. O segundo editor abriu a mesma sessão sem assumir uma sessão nova, acompanhou a conclusão e recuperou o recibo da entrada que já estava na fila. O Pi registrou uma mensagem para a solicitação inicial e outra para a entrada enfileirada. O encerramento da sessão passou pelo controle canônico. O Pi e o Connector eram processos reais na mesma máquina, e as respostas do modelo vieram de uma fixture local. [Evidência do ensaio](si022-r4-resume-lease.json)

Passaram 21 testes de continuidade, reinício e recuperação no wheel do Nexus e 12 testes de continuidade e reconexão no wheel do Connector. A cobertura do Nexus inclui geração divergente, ticket revogado, prova expirada e rejeição de recibo enquanto o canal está sem proprietário. [Regressão do canal](../../tests/execution_r4/test_connection_continuity.py)

Um ensaio posterior cobriu a reconexão fora da janela de retomada e a recuperação da fila da sessão encerrada em loopback. A validação entre máquinas distintas continua aberta. [Reconexão completa com Pi](si022-pi-full-reconnect.md)
