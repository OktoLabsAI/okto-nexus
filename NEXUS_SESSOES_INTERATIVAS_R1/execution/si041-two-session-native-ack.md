# Perda da confirmação nativa em duas sessões Pi

O ensaio manteve duas sessões do mesmo agente no mesmo projeto, cada uma com seu próprio processo Pi 0.87.1. Na primeira sessão, a fixture descartou uma resposta positiva do RPC `prompt` após o Pi receber a escrita. O wheel anterior registrou `OUTCOME_UNKNOWN`, acionou a recuperação e deixou o processo indisponível para a apresentação (`SESSION_UNKNOWN`). O Core já podia reconciliar a operação pelo evento de conclusão correlacionado.

O Nexus passou a publicar o recibo durável da operação exata enquanto mantém o processo Pi hospedado disponível. No wheel corrigido, a consulta repetida e a reapresentação da mesma intenção devolveram a operação original, com `possible_effect=true` e `retry_safe=false`. O SQLite registrou `OUTCOME_UNKNOWN` seguido de `SUCCEEDED` na mesma operação, e o recibo da fila mudou de `DELIVERY_UNKNOWN` para `ACCEPTED_NATIVE`. A primeira sessão recebeu um único `prompt` e produziu um único resultado.

No Edge, a Home mostrou o turno da primeira sessão após o detach no ConPTY e o resultado uma vez na mesma conversa. Durante o turno, a fila, a reorientação e a interrupção continuaram restritas à segunda sessão. A entrada com autorização expirada ficou em `BLOCKED_AUTH`, sem operação vinculada. O terminal somente leitura voltou à primeira sessão e exibiu seu resultado. O fechamento canônico das duas sessões deixou o SQLite íntegro e encerrou os processos e o listener do ensaio. [Observações e hashes](si041-two-session-native-ack.json)

Passaram a integração instalada e 12 regressões focais. A primeira rodada com o wheel corrigido confirmou a transição no SQLite, mas o auxiliar do teste recusava o estado intermediário e encerrava o fluxo antes da checagem final no navegador. A rodada conclusiva permitiu aguardar `OUTCOME_UNKNOWN` apenas para `turn.submit` com efeito possível e sem reenvio seguro. O ensaio usou Edge, ConPTY e dois processos Pi nativos com respostas determinísticas e rede externa bloqueada. Campanhas com provedores e qualificação entre hosts continuam pendentes.

O marco altera apenas o Nexus e dispensa migração. Para reverter, reconcilie recibos em andamento, reverta o commit e restaure o wheel anterior. Os pins do Connector e do Core permanecem os mesmos.

## Duas sessões com a fila pelo CLI

O Nexus 0.3.8 foi revalidado no Windows com Edge 158, ConPTY e dois processos Pi 0.87.1. As sessões compartilhavam o Harness ID e o projeto. O CLI selecionou cada sessão pelo ID exato. Em Beta, recusar a retomada manteve a mesma revisão de fila e o envio pendente. Em seguida, o operador confirmou retomada, pausa e retomada no terminal. O envio cuja autorização venceu ficou em `BLOCKED_AUTH`, sem operação vinculada. Alpha preservou o processo, a revisão da fila e o turno ativo durante os controles de Beta.

A Home exigiu a escolha da sessão e exibiu o resultado de Alpha uma vez. O terminal voltou à mesma sessão. Em Beta, `/export` apresentou a indisponibilidade e preservou o rascunho. A API recusou o comando com HTTP 422. A rodada anterior parou porque esperava indisponibilidade genérica para `/compact` durante um turno ativo. O catálogo explica nesse caso que a compactação interromperia o Pi.

A confirmação nativa perdida de Alpha foi reconciliada na operação original. O SQLite confirmou a sequência de recibos, uma única entrega em Alpha, os controles de Beta e dois fechamentos canônicos. Em dois lotes, passaram 126 regressões dos wheels instalados e um caso exclusivo de POSIX foi ignorado no Windows. O ensaio usa respostas simuladas e dispensa migração. A reversão deste registro consiste em reverter o commit. As campanhas com provedores seguem pendentes. [Resultados e hashes](si041-two-session-native-ack.json)
