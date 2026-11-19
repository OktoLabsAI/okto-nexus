# Anexar ao Codex gerenciado pelo Connector

O comando `okto-nexus session attach` seleciona a apresentação pelo executor da sessão exata. Para Codex hospedado pelo Connector, abre o visualizador nativo de leitura com o perfil humano do operador. O diretório e a thread exibidos vêm do Connector. O processo do visualizador roda com um diretório temporário próprio.

O broker usa um ticket de uso único, desafio de transporte e audiência específica. Uma reanexação pede um novo ticket e captura o histórico confirmado da mesma sessão. Cursores de outro visualizador são recusados. A saída por Ctrl+] libera a apresentação e devolve o console. O turno continua sob a concessão que já estava em uso.

O ensaio ponta a ponta cobriu a recusa de origem externa, credencial de agente, pedido de escrita e reuso de ticket. No Windows, o Codex 0.170.0 acompanhou o app-server Codex 0.157.0 hospedado pelo Connector. As duas anexações usaram o mesmo PID e a mesma thread. O segundo visualizador mostrou o resultado após uma única resposta de modelo simulada em loopback. A qualificação em máquinas distintas e o transporte remoto de escrita continuam em aberto.

A alteração dispensa migração. Reverter este commit retira o attach remoto e preserva o histórico canônico e as sessões. [Evidências](si022-codex-remote-attach.json)
