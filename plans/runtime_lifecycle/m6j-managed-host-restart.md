# M6j — lease expirada e restart do host com processo nativo gerenciado

Data: 2026-10-20 UTC. Corte local Windows do item 4 do ADR M6; Nexus HTTP e dois Connectors em processos separados, com Core/Connector instalados.

O handoff selecionou um único Connector e iniciou uma sessão cujo peer sintético também possuía um processo nativo real de longa duração, criado por `spawn_owned_process` no Windows Job identificado pelo `process_launch` do Core. O envio nativo ocorreu uma vez, mas a resposta do provider foi perdida de modo controlado; o Server registrou `OUTCOME_UNKNOWN` com efeito possível, sem autorização de replay. O teste matou somente o processo Connector selecionado, observou a saída do filho do Job, aguardou a expiração da lease original e iniciou um novo Connector no mesmo estado local.

Antes da queda, o slot físico estava ocupado. Na reconciliação após o restart, o journal do Core registrou `spawn_claimed=1`, `producer_fenced=1` e `stop_proof=CONTAINER_STOPPED`; o slot passou a `released=1`. O novo host alcançou uma geração maior e voltou a `CONTROL_READY`, sem abrir ou enviar outro trabalho nativo. O dispatch do turno original permaneceu com `attempt_no=1`, e o handoff continuou vinculado ao mesmo consumo. A observação antiga não pôde reassumir capacidade nem substituir a nova geração.

Um primeiro fixture sem processo nativo real falhou corretamente em modo fechado: após matar o host não havia prova de parada física e a reconciliação recusou liberar a reserva. Essa tentativa foi revertida; nenhum relaxamento de autoridade foi introduzido. O peer gerenciado também foi usado no corte `unknown_reconnect` no Windows, eliminando a dependência de uma prova física inexistente sob lease curta. O novo caso passou isolado em 50,12 s; os nove casos de seleção/recuperação passaram juntos em 309,19 s com Nexus 0.3.1, Core 0.0.12 e Connector 0.0.10 instalados.

Este checkpoint qualifica o corte local com Job do Windows e host Connector separado. Não prova outro host físico nem upgrade/rollback de pacote. A comparação de disponibilidade/custo ainda é necessária antes da decisão de adoção M6.
