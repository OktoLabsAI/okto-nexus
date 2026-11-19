# SI-015, SI-016 e SI-036 · Comandos exclusivos do terminal na Home

O catálogo da sessão passou a incluir a versão registrada na abertura. Ao selecionar `/resume`, a Home mostra de onde vem a ação, a versão quando conhecida e a orientação para verificar a disponibilidade no terminal Codex. A informação se refere à sessão aberta. Sessões antigas sem esse registro mantêm o aviso. A versão integra a revisão do catálogo usada nas confirmações.

No Chromium, segui uma sessão ativa do Codex 0.157.0. Pressionar Enter com `/resume`, `/comando_inexistente` ou `/tmp/file` preservou os respectivos rascunhos e gerou zero pedidos ao runtime. A opção de envio literal permaneceu indisponível neste adaptador. A consulta **Show session status** enviou uma única ação tipada, identificada como Nexus, recebeu HTTP 200 e ficou na auditoria da sessão.

Em chamadas diretas autenticadas, a API tipada devolveu HTTP 422 para as três entradas recusadas. O catálogo exigiu login, e a base conservou as duas operações originais e nenhuma entrada na fila. O turno de controle concluiu usando a única resposta sintética em loopback. A sessão encerrou pelo fluxo canônico e o processo saiu. A primeira preparação expirou durante a abertura. A repetição aguardou o recibo e completou o ensaio.

Passaram 421 testes do frontend, uma regressão focada no código-fonte, 45 testes Python com o wheel instalado e o ensaio com o app-server real no Chromium. O lock, a compilação, a verificação estrita dos pacotes e o Ruff dos módulos alterados passaram.

O ledger registra SI-T-D01, D02, D04, D05, D07, D08 e D11 no cenário observado. Envio literal qualificado, leitor de tela e aceite humano seguem em aberto. A reversão deste commit restaura o catálogo e o bundle anteriores, sem migração. [Resultados e hashes](si016-browser-terminal-only.json)
