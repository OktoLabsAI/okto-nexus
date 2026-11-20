# SI-T-B01, SI-T-B06, SI-T-B09, SI-T-B22 e SI-T-C01 — Fila durante uma ferramenta do Pi

O Nexus abriu uma sessão local com Pi 0.87.1 e um provedor simulado.
Após um turno de preparação, a API confirmou que a sessão estava ociosa.
O envio seguinte recebeu HTTP 202 e iniciou um turno canônico para aquela
entrada na mesma sessão. O transporte registrou uma chamada `prompt` para
cada entrada entregue.

Durante esse turno, o Pi completou um fragmento de texto e iniciou uma
ferramenta de teste mantida aberta. A API ofereceu reorientação para o
turno ocupado. No Edge, Enter fez um único pedido `POST /inputs`, que
retornou HTTP 202 e exibiu a confirmação de fila. O recibo ainda não
tinha uma operação vinculada.

Três varreduras do dispatcher, com pelo menos três segundos sem novos
eventos nativos da sessão, mantiveram o estado ocupado e o recibo
enfileirado. O término da ferramenta também manteve o turno ocupado
enquanto a resposta estava retida. Depois que a resposta foi liberada,
o stream registrou `agent_end`, `agent_settled` e o início do turno
seguinte, nessa ordem. O Pi recebeu os três textos em mensagens separadas.
O transporte registrou zero chamadas `follow_up` e `steer`.

Passaram o ensaio com Edge e Pi, três regressões da API com os wheels
instalados e a auditoria SQLite. A auditoria encontrou três resultados
na mesma sessão, os dois recibos de envio vinculados a operações
distintas e um fechamento canônico. O provedor e a ferramenta eram
fixtures. O ensaio não reteve retry ou compactação entre `agent_end` e
`agent_settled`. Esse cenário específico continua pendente.
[Dados do ensaio e hashes](si007-pi-tool-boundary.json)

As primeiras execuções identificaram erros do observador. O marcador da
ferramenta foi correlacionado pelo stream e pelo identificador da chamada.
A varredura selecionou o agendador de entradas, e a checagem final esperou
a projeção de `agent_settled` chegar ao Nexus. Cada tentativa encerrou sua
sessão descartável pelo controle canônico.

O marco atualiza as evidências e o ledger. Reverter o commit remove esse
registro e dispensa migração.
