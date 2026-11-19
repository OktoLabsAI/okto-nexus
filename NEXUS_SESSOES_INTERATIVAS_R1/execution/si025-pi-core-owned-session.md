# Sessão do Pi iniciada e encerrada pelo Core

O ensaio executou o Pi 0.87.1 por meio do `PiRpcConnector` e do runtime R4 do Core 0.0.16. O Core registrou o nascimento do processo e o ID nativo no recibo de abertura. A prova de dono permaneceu válida durante a abertura, o detach e a reabertura do renderer. Uma consulta com outro ID nativo foi recusada.

Durante o turno, o Core recebeu novamente a mesma operação e devolveu o recibo original. O RPC do Pi recebeu um prompt, o renderer reaberto mostrou a resposta e o Core correlacionou um único `agent_settled` à operação. A confirmação de encerramento veio do Core após a saída do processo. O arquivo da sessão preservou uma mensagem de usuário e uma resposta. [Resultados e artefatos](si025-pi-core-owned-session.json)

O ensaio injeta o host de teste no ponto de construção do adaptador. Usa o renderer e o RPC da instalação examinada, um terminal de captura em memória, um provedor sintético do Pi e uma concessão R4 de teste. A abertura, os recibos, a deduplicação e o encerramento passaram pelo Core. A sessão foi lida por um canal interno do adaptador apenas para comparar o estado e o ID nativos com o recibo. A abertura por um terminal de operador no Nexus, o canal autenticado de apresentação, a entrada nativa e os testes com extensões continuam pendentes.

O ensaio passou com o código-fonte e com o wheel instalado do Core. Também passaram 35 regressões de inicialização, autorização R4 e transporte Pi.

O script em `579692681e7de650d17908ae595e5fa6a2834892` reproduz esta prova com o Core 0.0.16 original e `--core`. A versão atual do script também verifica a leitura interna do Nexus e exige o pin registrado na evidência seguinte. [Leitura da sessão pelo Nexus](si025-pi-owned-state.md)
