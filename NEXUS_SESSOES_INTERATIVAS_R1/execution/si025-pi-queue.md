# Fila canônica para o Pi hospedado

O Nexus já aceitava mensagens para a sessão correta enquanto o Pi trabalhava. No ensaio, a mensagem continuou pendente depois do fim do turno. A observação usada pelo Core para reservar o próximo turno informava apenas se o processo estava vivo.

O Core agora combina a leitura validada do estado do Pi hospedado com seu próprio marcador de conclusão do turno. Uma sessão que está gerando resposta, compactando, com mensagens internas pendentes ou aguardando `agent_settled` continua ocupada. Estados ilegíveis e respostas de outra sessão não autorizam a reserva. O RPC comum conserva sua observação de processo.

O modo `--queue` do ensaio abriu o mesmo Pi no Nexus instalado. Ele enviou uma mensagem pela API da fila do painel durante o primeiro turno e repetiu o pedido com a mesma chave. A fila devolveu o mesmo recibo e o Pi continuou sem mensagens pendentes no protocolo nativo. O fluxo durável registrou a conclusão do primeiro turno antes do início do segundo. Os dois resultados apareceram no visualizador e no histórico da mesma sessão. Passaram 110 testes de regressão com os wheels instalados. [Resultados e hashes](si025-pi-queue.json) [Instruções do ensaio](si025-pi-terminal-e2e.md)

A etapa cobre a fila pelo painel e a observação de seus resultados no terminal com provedor sintético. A escrita pelo visualizador, as aprovações, o redirecionamento e a campanha com inferência real seguem pendentes. A alteração dispensa migração. A reversão coordenada restaura o pin anterior do Core nos dois consumidores.
