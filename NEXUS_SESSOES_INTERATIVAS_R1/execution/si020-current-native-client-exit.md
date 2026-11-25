# SI-020 e SI-032 · Continuidade após a saída abrupta do terminal

No Windows, o app-server Codex 0.157.0 manteve o mesmo processo, a mesma thread, o turno ativo e a fila após o fechamento do console ConPTY e após o encerramento do processo de apresentação. Cada cenário usou o visualizador Codex 0.170.0 com o hash revisado, recuperado do cache local de pacotes.

O turno original e a entrada enfileirada terminaram enquanto nenhum visualizador estava anexado. Um novo terminal abriu a mesma sessão, exibiu o resultado e recebeu a permissão de escrita sem tomada de controle. A auditoria de SQLite confirmou uma abertura, dois turnos na sessão selecionada e um encerramento canônico por cenário. As duas anexações de cada cenário terminaram em `DETACHED`. [Resultados e hashes](si020-current-native-client-exit.json)

Os dois cenários passaram com os wheels instalados e um simulador de respostas em loopback. Nenhum processo do teste ficou ativo. Os cenários de campanha SI-T-G03 a SI-T-G05 continuam pendentes.
