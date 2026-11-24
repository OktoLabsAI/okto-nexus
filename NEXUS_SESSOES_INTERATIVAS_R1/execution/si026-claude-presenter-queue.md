# SI-026 · Entrada canônica na apresentação do Claude

A apresentação do Claude gerenciado pode assumir a escrita para a sessão exata. O Nexus verifica o vínculo, a geração, o login humano, a titularidade de escrita e a revisão da capacidade. O visualizador recebe a saída do terminal existente. O envio de texto entra na fila compartilhada com a Home. O Core entrega o prompt pelo fluxo autorizado da instância gerenciada.

Os testes do transporte confirmaram a ordem da fila, a troca explícita de escritor e a recusa de mensagens do escritor substituído. Também confirmaram que repetir a mesma intenção devolve o recibo original e que o recibo pode ser consultado após sair. Na primeira rodada, a instalação sintética sem arquitetura explícita não habilitou escrita no ensaio remoto. O mesmo teste passou com esses metadados.

Com os wheels instalados nesta máquina Windows, o cliente de teste abriu a apresentação do Claude Code 2.1.328 via Connector e enfileirou uma mensagem enquanto o turno anterior estava ativo. Consultou o recibo pendente depois de desanexar. O Claude recebeu a mensagem após concluir o turno anterior. A auditoria comprovou dois resultados na mesma sessão, uma única abertura nativa, o fechamento canônico e a integridade dos bancos. O modelo foi simulado em loopback. [Cenários, comandos e hashes](si026-claude-presenter-queue.json)

O compositor interativo no `session attach --write` e os controles de turno dentro do visualizador são as próximas etapas. O CLI público mantém o acompanhamento em leitura, com os comandos de controle existentes. Este marco dispensa migração e pode ser revertido pelo commit do Nexus. [Matriz de capacidades](si027-session-capability-matrix.md)
