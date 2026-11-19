# SI-017 e SI-036 · Pausa visual com fila ativa

Com a Home em **Pause display**, abri a conversa de uma sessão Pi ativa e coloquei uma mensagem na fila. A API respondeu HTTP 202, e a mensagem permaneceu enfileirada até o turno original terminar. O mesmo processo Pi recebeu a mensagem uma única vez. A fila do servidor permaneceu habilitada durante a pausa visual.

Ainda com a Home pausada, revisei a reorientação dessa entrada. O Chromium segurou a requisição de confirmação até o turno original terminar e a entrada passar para o turno seguinte. A API recusou as revisões anteriores com HTTP 409 e informou que a entrada ou a fila havia mudado. Nenhuma operação de reorientação foi criada. A conversa mostrou os dois turnos concluídos enquanto a composição e a ordem dos cards da Home ficaram estáveis. Ao retomar a atualização, a coluna Results passou de zero para dois resultados.

O teste executou Nexus, Connector e Core de wheels instalados e usou o Pi 0.87.1 real com respostas sintéticas e rede externa bloqueada no Pi. Passaram o ensaio no Chromium, 28 testes de componentes e 30 testes da API e do armazenamento. O encerramento canônico da sessão foi confirmado pela saída do processo Pi. A primeira preparação foi interrompida quando o ambiente ainda estava subindo. A tentativa seguinte ajustou o roteiro para observar a entrada do segundo turno no Pi antes de liberar sua resposta, usando o recibo final apenas depois.

O ledger registra SI-T-E16 como aprovado no cenário observado. O commit registra apenas a evidência e sua reversão dispensa migração. [Resultados e hashes](si036-visual-pause.json)
