# SI-032 · Saída do visualizador com o turno ativo

Em Windows ConPTY, o frontend Codex 0.170.0 acompanhou um turno ativo do app-server Codex 0.157.0. Ctrl+C abriu a revisão para aquele turno. Ctrl+] desanexou o visualizador enquanto a revisão ainda estava aberta, sem executar a interrupção. Em outro ensaio, `/exit` encerrou o frontend durante um turno ativo. O CLI devolveu o controle ao shell com os modos originais de entrada e saída nos dois casos.

Em cada ensaio, o mesmo app-server manteve a thread e a concessão produtiva. O turno e a mensagem enfileirada terminaram sem visualizador. Uma nova anexação mostrou o resultado e obteve escrita sem pedir transferência. A auditoria SQLite confirmou uma abertura, dois resultados na sessão selecionada, dois anexos encerrados e um fechamento canônico. O guia registra os atalhos do Codex e aponta para a tecla exibida no banner do Pi e do Claude. [Guia do terminal](../../docs/terminal-work.md)

Passaram os dois ensaios nativos e 37 regressões com os wheels instalados. Os ensaios usaram respostas de modelo simuladas em loopback. A campanha de SI-T-G03, G04 e G05 continua pendente. O commit atualiza documentação e evidências e pode ser revertido por Git, sem migração. [Resultados, auditorias e hashes](si032-current-console-exit.json)
