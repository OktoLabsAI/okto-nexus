# SI-030 · Abrir outra sessão vazia no terminal

`okto-nexus session open` seleciona a conexão pelo Harness ID ou pelo perfil existente. A confirmação usa Não como padrão. O comando registra uma abertura canônica independente e apresenta o novo ID quando o servidor confirma que a sessão aceita controle. O operador usa esse ID se quiser anexar o terminal. O comando mantém a autorização da conexão, o checkpoint de trabalho e as filas sob as sessões que já os possuem.

O checkpoint de abertura no formato 2 guarda a intenção explícita de criar uma sessão. A recuperação volta ao recibo original. Um checkpoint anterior no formato 1 conserva a forma anterior do pedido. O teste com o CLI instalado antes desta mudança confirmou a recusa do novo formato pendente sem requisições e com o checkpoint preservado. Para reverter, reconcilie aberturas em andamento com o CLI atual e restaure o wheel anterior. A reversão dispensa migração de banco. [Comando e opções no guia de terminal](../../docs/terminal-work.md)

O ensaio com o wheel instalado abriu duas sessões reais do Pi 0.87.1 em Windows ConPTY, com respostas simuladas. O operador descartável manteve Não na primeira confirmação. Em seguida confirmou a abertura enquanto a sessão de origem tinha um turno em curso e uma mensagem na fila. A fixture descartou a resposta do POST depois que a API gravou a operação. Repetir o comando recuperou o mesmo recibo e mostrou o novo ID. O servidor registrou um único POST de admissão e a abertura vazia não disparou um turno.

O operador abriu e desanexou o visualizador da segunda sessão. O Ctrl+C devolveu o código 130 e o broker gravou o detach. A primeira mensagem da nova sessão foi entregue ao Pi da nova sessão. Quando o turno da sessão anterior terminou, o Pi original recebeu a entrada pendente uma única vez. Os dois históricos permaneceram separados e os dois encerramentos canônicos tiveram sucesso.

Passaram 134 testes no código-fonte e 134 no wheel instalado, além do ensaio embutido. O lock offline e a validação estrita do wheel passaram. O Ruff repetiu um aviso de ordenação de imports da referência.

No ensaio com o Connector remoto, o Core registrou a segunda abertura e o Connector perdeu o canal R4 durante a publicação do recibo. O Nexus conservou a abertura como pendente e a fila permaneceu com a sessão de origem. A geração do canal mudou na reconexão e a confirmação ficou pendente na janela observada. SI-T-G20 recebe a evidência local da abertura canônica e continua aberto para a qualificação do caminho remoto, dos comandos internos do harness e da campanha. [Resultados e hashes](si030-cli-empty-new-context.json)

O ensaio posterior confirmou que a reconexão recuperou o recibo e encerrou a sessão original. O CLI passou a resolver o checkpoint nesse estado. [Recuperação após reconexão R4](si030-remote-closed-opening-recovery.md)
