# SI-T-B08 — Fila aguarda a confirmação de término do Pi

O ensaio usou o Pi 0.87.1 instalado no executor local. A fixture reteve
a entrega de um evento real `agent_settled` no transporte do processo
de teste. O Nexus recebeu `agent_end` antes dessa confirmação, com
uma entrada humana já na fila da sessão.

Três varreduras do dispatcher durante a retenção não criaram operação
para a entrada. O transporte continuou com os dois envios anteriores.
Depois que a fixture entregou o evento original, o dispatcher enviou
a entrada uma vez. O turno seguinte terminou na mesma sessão.

A leitura do SQLite confirmou a ordem `agent_end`, `agent_settled`,
início do turno seguinte. O banco conservou três resultados, duas
entradas entregues por operações distintas e uma sessão encerrada
pelo controle canônico. Passaram o ensaio com os wheels instalados
e a auditoria de integridade.
[Resultados e hashes](si025-pi-delayed-settlement.json)

O atraso foi introduzido no transporte. O teste usou respostas
simuladas e não induziu retry ou compactação no provedor. O marco
atualiza as evidências e o ledger. Reverter o commit remove esse
registro e dispensa migração.
