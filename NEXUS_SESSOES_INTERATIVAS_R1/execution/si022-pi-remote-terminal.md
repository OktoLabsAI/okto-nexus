# SI-022 e SI-025 — Terminal do Pi hospedado pelo Connector

`okto-nexus session attach` abre o renderizador da sessão exata. `--write` abre o editor para que Enter grave a mensagem na fila do Nexus. A sessão, a geração original e a intenção continuam sendo o escopo do recibo. O mesmo broker de sessões valida o login de operador, impede que uma credencial de agente abra o visualizador e mantém um único escritor autorizado.

O Nexus confirma o vínculo, a sessão, o lease e o renderizador no Connector antes de emitir o ticket. Cada visualizador remoto usa um canal negociado por sessão, com respostas correlacionadas e leitura sob demanda. Desanexar libera o renderizador e preserva o trabalho e a fila no host.

O teste de integração usou HTTP, dois WebSockets, SQLite e o daemon Connector reais com renderizador simulado. O Nexus recusou origem externa, credencial de agente e geração incorreta. O leitor exibiu o transcript, o editor não enfileirou ao digitar e Enter gravou um único pedido na fila. O recibo foi recuperado após detach e a operação original continuou.

Com os pacotes instalados, o ensaio Windows ConPTY usou Node e Pi 0.87.1 revisados, em perfis temporários e na mesma máquina. O editor abriu durante o primeiro turno. Enter gravou uma mensagem em `QUEUED`. Após Ctrl+C, o recibo foi recuperado e um leitor acompanhou o fim do primeiro turno e a resposta à mensagem enfileirada. O histórico confirmou as duas mensagens na mesma sessão e o PID permaneceu o mesmo até o encerramento canônico. As respostas eram simuladas e o ensaio bloqueou conexões do Pi a provedores externos.

Nas primeiras execuções, a janela de observação da abertura expirou antes de o Nexus receber o recibo e o roteiro aguardou a aceitação final da continuação antes de liberar a resposta simulada. O ensaio passou após ajustar esses dois pontos do roteiro. Passaram 73 testes de regressão com os pacotes instalados, além do ensaio nativo.

A alteração dispensa migração. Para reverter a etapa, use `git revert` no Nexus. As verificações e os hashes constam no [registro de evidências](si022-pi-remote-terminal.json).

SI-022 e SI-025 seguem em andamento. A reorientação e a interrupção no editor remoto ainda dependem de um controle de execução que carregue a referência exata do run Pi pelo Connector. As campanhas entre máquinas e a oferta de abertura no `connect` para Pi continuam pendentes.
