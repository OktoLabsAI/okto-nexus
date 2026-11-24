# SI-016 / SI-027 / SI-037 · Envio literal do Pi em Linux

O catálogo e o despacho da fila reconhecem a instalação revisada do Pi 0.87.1 com Node 24.15.0 em Linux x64. **Send as text** continua exigindo a capacidade literal negociada pelo dono atual da sessão. O catálogo também mantém a compactação indisponível enquanto o Pi está trabalhando, pois esse comando pode abortar o turno ativo. [Identidades e resultados](si037-linux-pi-literal.json)

Os ensaios usaram os wheels instalados, o Pi real e um modelo simulado no Ubuntu 24.04.5 em WSL2. O primeiro turno ficou em andamento enquanto a API autenticada da Home recebia o texto `/skill:literal-fixture café  `. O próprio Pi listou a skill do ensaio entre os comandos disponíveis. O envio comum com esse prefixo recebeu HTTP 422. A revisão desatualizada do catálogo recebeu HTTP 409.

O envio literal explícito recebeu HTTP 202 e ficou em `QUEUED`. Repetir a intenção devolveu o mesmo ID e a mesma sequência. Após o turno inicial, o mesmo Pi recebeu uma única ocorrência do texto original, com a barra, o acento e os espaços finais. O corpo da skill ficou ausente da entrada do modelo. A fila marcou `ACCEPTED_NATIVE`, os resultados ficaram na sessão original e o fechamento canônico encerrou o Pi. O Connector transportou a marca literal no R4. O executor incorporado fez a mesma validação com Secret Service descartável.

Passaram os dois ensaios integrados e 81 regressões instaladas no Windows e no Linux. A primeira tentativa do caso incorporado consultou os resultados antes de a projeção publicar o segundo. A repetição aguardou a publicação dos dois resultados. A validação Linux usou a API autenticada. O cenário de navegador previsto no plano tem evidência no Windows. [Evidência de navegador](si016-pi-literal-ui.md)

O marco dispensa migração. Para revertê-lo, conclua ou cancele as entradas literais Linux pendentes e reconcilie recibos de envios em trânsito. Depois, reverta o commit do Nexus. A prova em outra máquina, macOS, campanhas com provedores e aceitação humana seguem pendentes.
