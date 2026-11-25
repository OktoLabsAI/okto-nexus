# SI-036 · Resultados da sessão encerrada e navegação por teclado

O ensaio usou Edge 158 no Windows, Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 instalados. O Pi 0.87.1 rodou pelo Connector em loopback com duas respostas simuladas. O navegador abriu o projeto **Projeto Remessas**, encontrou o pedido em andamento pelo card do colaborador e registrou uma mensagem para o próximo turno. [Ambiente, resultados e hashes](si036-current-closed-results-keyboard.json)

- **Fila e conversa.** A Home confirmou a fila e permitiu voltar à conversa pelo mesmo card. A mensagem apareceu na conversa após a primeira resposta. As duas respostas apareceram uma vez cada e na ordem esperada.
- **Resultados após encerrar.** O encerramento canônico terminou o Pi antes da inspeção dos cards. A Home exibiu os dois resultados. Cada card abriu o texto da operação correspondente acima da mesma conversa. A ação **Continue this exact session** ficou ausente nos dois painéis.
- **Teclado.** Fechar o primeiro painel devolveu o foco ao seu botão. Tab alcançou o segundo resultado, Enter abriu seu painel e Escape devolveu o foco ao segundo botão. A auditoria comparou os dois controles e os conteúdos exibidos com as operações exatas no SQLite.

O pacote instalado passou no ensaio com navegador e Pi. Também passaram 425 testes de frontend. O SQLite confirmou uma sessão encerrada, uma abertura, dois turnos, dois resultados e uma entrada `ACCEPTED_NATIVE`, com integridade e chaves estrangeiras válidas. O ambiente descartável foi encerrado.

O aceite humano e a verificação de fala com leitor de tela no Windows continuam pendentes. A prova de fala existente cobre Orca e Chromium. A SI-036 fica em andamento. Este marco atualiza o ledger e as evidências, e sua reversão dispensa migração. [Roteiro para o participante](si036-participant-rehearsal.md) [Prova com Orca](si017-orca-live-turn-announcements.md)
