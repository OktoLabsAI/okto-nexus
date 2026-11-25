# SI-025 · Fila e fronteira de turno do Pi

No Windows, o Pi 0.87.1 executou pelo Connector enquanto o editor em ConPTY e a API autenticada da Home enviavam à mesma sessão. Cada superfície registrou uma entrada comum. Repetir o pedido da Home recuperou a entrada original. A reorientação pelo editor foi aplicada ao turno ativo, e as duas entradas comuns seguiram uma vez cada, na ordem registrada. O journal do Connector confirmou uma única abertura nativa, e o mesmo processo continuou depois de desanexar o editor. O fechamento canônico encerrou a sessão.

A auditoria do banco confirmou três resultados e preservou a distinção entre envio e efeito da reorientação. O recibo do comando ficou em `SUBMITTED`. Os eventos `queued` e `consumed`, vinculados ao mesmo run e à operação original, confirmaram a aplicação da instrução. A sessão e o journal passaram nas verificações de integridade e chaves estrangeiras.

No executor local, o teste reteve um evento real `agent_settled` após a chegada de `agent_end`. Durante três varreduras, o dispatcher deixou a mensagem pendente sem criar uma operação. Ao receber o evento retido, enviou um único próximo turno na mesma sessão. A primeira rodada da fixture esperava `SUBMITTED` para entradas produtivas do Pi. A repetição aguardou `ACCEPTED`, o estágio observado no pacote atual.

Passaram os dois ensaios com Pi real e 72 regressões nos wheels instalados. Um teste de pseudoterminal POSIX foi pulado no Windows. Ambos os ensaios nativos usaram modelo simulado, com zero chamadas a provedores. A qualificação de campanha dos cenários SI-T-G01, G04 e G18 continua pendente. O commit registra evidências e pode ser revertido por Git, sem migração. [Resultados, auditorias e hashes](si025-current-native-queue.json)
