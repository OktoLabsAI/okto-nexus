# Transporte de escrita para a sessão hospedada do Pi

O Nexus pode conceder um ticket de escrita para a sessão hospedada e revisada do Pi. A conversa e a revisão da fila fazem parte da autorização desse ticket. O broker verifica novamente o login, a sessão, o canal e a geração do escritor dentro da transação que insere a mensagem. A transferência para outro escritor exige o epoch atual e consentimento explícito. O cliente substituído libera a conexão de renderização antes da abertura do sucessor.

O transporte separa os quadros binários do renderer e os pedidos estruturados de fila. O renderer privado continua emitindo somente saída. Um envio grava uma mensagem de texto na fila canônica com a intenção do cliente. Ele pode receber o mesmo recibo ao repetir a mesma intenção. Se a resposta do transporte se perder, o cliente marca o resultado como incerto, e a API permite consultar o recibo original sem criar outro envio.

O ensaio `--queue --queue-surface presenter` passou com o Nexus e o Pi instalados e um provedor sintético. Durante um turno, o cliente do protocolo abriu um ticket de escrita, enviou a mesma intenção duas vezes e fechou a conexão. A verificação recuperou o recibo com o mesmo login e acompanhou pelo ConPTY o segundo turno na mesma sessão. Passaram 44 testes com os pacotes instalados, incluindo transferência com renderer simulado e perda da resposta. [Evidência](si025-pi-writer-transport.json) [Instruções do ensaio](si025-pi-terminal-e2e.md)

Em um ensaio isolado, o editor nativo do Pi 0.87.1 mostrou texto em português colado em duas linhas e emitiu um único envio com Enter. Esse ensaio usou um terminal simulado e exercitou a captura de texto do editor.

A etapa dispensa migração. A reversão é o commit deste marco no Nexus. A SI-025 continua em andamento. O editor nativo ainda precisa enviar as mensagens pelo transporte. Aprovações, reorientação e inferência real também seguem pendentes.
