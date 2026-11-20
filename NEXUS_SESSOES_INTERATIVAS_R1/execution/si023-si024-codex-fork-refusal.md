# SI-023 e SI-024 · Recusa de fork e de nova thread

O visualizador Codex 0.170.0 abriu a thread selecionada pelo Nexus em ConPTY no Windows. O Core operava duas threads ociosas no mesmo app-server real 0.157.0. O ensaio usou o relay e o broker SQLite do produto, WSS em loopback e um catálogo de sessões de teste.

No visualizador anexado, os comandos **/fork** e **/new** enviaram pedidos nativos. O relay respondeu com erro -32601. A engine recebeu somente leituras da thread selecionada durante a observação. O mesmo processo e a thread original continuaram disponíveis, inclusive após o detach. O dono também manteve acesso à segunda thread. A auditoria confirmou zero operações de trabalho e os recibos dos leitores encerrados.

Em outra execução, o visualizador real iniciou sem o ID exato. Ele pediu **thread/start** duas vezes durante o handshake. O relay recusou ambos os pedidos, o visualizador saiu com erro e a thread original permaneceu legível. A primeira rodada deste teste esperava um único pedido. O teste final conferiu a recusa de todos os pedidos até a saída do visualizador e confirmou que nenhuma criação chegou à engine.

Para retomada salva, um segundo app-server real recebeu o ID exato de uma thread vazia da fixture, depois de o processo de origem ter saído. O app-server recusou a retomada sem histórico com erro -32600. O Core manteve zero sessões admitidas na sucessora e emitiu somente os pedidos de inicialização, conta e retomada. Os dois processos tiveram a saída confirmada.

A regressão do Core exercita um peer JSON-RPC que recusa **thread/resume** com -32601 e aceitaria **thread/fork** ou **thread/start**. O Core propagou a recusa, registrou apenas a tentativa exata e encerrou o processo de teste. Passaram 11 testes do Core no código-fonte, os mesmos 11 com o wheel instalado, 104 regressões instaladas do Nexus e os ensaios nativos. O Ruff repetiu os dois avisos de imports da referência. A primeira rodada da regressão confundiu encerramento normal do teste com saída espontânea do subprocesso. A repetição observou a saída do processo pelo handle.

Os ensaios usaram perfis temporários e zero chamadas a provedores. SI-T-G16 e SI-T-G19 registram esta evidência de execução controlada no Windows e seguem pendentes de campanha. Os commits acrescentam teste e evidências. A reversão é por commit e dispensa migração. [Resultados, métodos e hashes](si023-si024-codex-fork-refusal.json)
