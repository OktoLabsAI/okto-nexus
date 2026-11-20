# Ticket de anexação de uso único no visualizador Codex

O cenário SI-T-H04 usou o Nexus 0.3.8 instalado sobre WSS em loopback, o visualizador Codex 0.170.0 em Windows ConPTY e o app-server 0.157.0 com uma thread ociosa. O roteador e o broker SQLite eram os do pacote instalado. O catálogo de conexões era controlado pela fixture. A CA temporária foi confiada apenas pelo cliente do ensaio. [Resultados e hashes](si034-native-attachment-ticket-replay.json)

Com o ticket ainda disponível, três verificações foram recusadas. Elas usaram outra sessão, em outro executor e workspace com o mesmo ID curto, uma geração diferente da sessão correta e o protocolo local no lugar do remoto. O ticket continuou utilizável no escopo original. Na conexão legítima, o broker também recusou o mesmo ticket em outro canal durante o desafio, com o leitor ativo e após o detach. As seis recusas encerraram os sockets com código 4409, sem entregar nenhum frame de apresentação.

O único leitor autorizado executou `thread/read` e `thread/resume` para a thread exata. O detach restaurou os modos do terminal. A engine original e a thread continuaram acessíveis até o encerramento do ensaio. O SQLite confirmou um anexo `DETACHED`, hashes do ticket e do desafio limpos, zero entradas de fila, controles ou operações de trabalho, e integridade preservada.

Passaram a integração nativa com WSS e 13 regressões instaladas do broker e do transporte local e remoto. O ensaio dispensou inferência e contas de provedores. O marco acrescenta evidências e atualiza o ledger. O rollback consiste em reverter o commit, sem migração de dados.
