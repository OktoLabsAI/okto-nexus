# SI-T-H10 e SI-T-H11 — Interrupção e desanexo no Codex

O banner do visualizador Codex com escrita e o guia do terminal descrevem
`Esc` ou `Ctrl+C` para revisar a interrupção do turno ativo. O console
mostra `Ctrl+Y` para confirmar, `Ctrl+N` para cancelar e `Ctrl+]` para
desanexar. O atalho de desanexo varia conforme o visualizador.
[Guia do terminal](../../docs/terminal-work.md)

O ensaio usou o wheel Nexus reconstruído, os pins atuais de Connector e
Core, o Codex 0.170.0 em Windows ConPTY e o app-server Codex 0.157.0
hospedado pelo Connector. As três anexações usaram a mesma sessão, o
mesmo turno e um único processo nativo.

1. `Ctrl+C` abriu a revisão para o ID exato do turno. `Ctrl+N` cancelou
   a revisão e manteve o turno e a fila ativos. O app-server recebeu
   zero chamadas de interrupção.
2. Em outra anexação, `Ctrl+]` descartou uma revisão pendente e fechou
   o visualizador. O CLI recuperou o recibo `DETACHED` e restaurou os
   modos do console. O turno continuou no app-server original, que
   recebeu zero chamadas de interrupção, fechamento ou unsubscribe.
3. O terceiro visualizador abriu o mesmo turno em andamento. Depois
   da revisão por `Ctrl+C`, `Ctrl+Y` enviou uma única interrupção nativa.
   A fila já estava pausada no momento do envio. O turno original
   registrou `CANCELLED`. O fechamento canônico posterior encerrou
   o app-server.

Passaram o ensaio no pacote reconstruído e 20 regressões instaladas. O
wheel e o pacote fonte passaram pela validação estrita de metadados.
Uma tentativa anterior exigiu corrigir a carga do pywin32 no ambiente
descartável. Uma anexação foi recusada em outra tentativa, antes de
qualquer gesto de controle. O roteiro confirmou o fechamento daquela
sessão antes de repetir. O ensaio concluído usou um pedido ao simulador
e zero chamadas a provedores externos.
[Comandos, hashes e observações](si032-codex-interrupt-and-detach.json)

O ledger registra `PASS` para SI-T-H10 e SI-T-H11. A alteração dispensa
migração. A reversão restaura o texto anterior do banner e do guia.
