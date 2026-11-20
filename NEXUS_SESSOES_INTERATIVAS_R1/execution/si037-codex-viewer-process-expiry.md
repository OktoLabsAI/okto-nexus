# SI-T-H09 — Saída do processo de apresentação e expiração

Os ensaios de Windows usaram os wheels instalados, o app-server Codex 0.157.0 no Connector e o visualizador Codex 0.170.0 em ConPTY. A fixture encerrou o processo descartável de apresentação pelo handle que abriu ao criá-lo. O teste reteve a notificação de desconexão do WSS e adiantou apenas o relógio do broker de apresentação. O turno e as respostas determinísticas rodaram em loopback. [Resultados, versões e hashes](si037-codex-viewer-process-expiry.json)

1. A primeira rodada observou a expiração com a engine original ativa e a mensagem ainda na fila. Um conflito de capacidade impediu a revisão do escritor substituto.
2. Na segunda rodada, outro escritor abriu a mesma sessão sem transferência. O SQLite confirmou que a mensagem foi aceita pelo processo nativo, com um turno para a entrada original e um para a entrada enfileirada, ambos concluídos com sucesso. A captura do terminal substituto não mostrou o segundo resultado.
3. Na terceira rodada, o processo descartável saiu, mas a fixture não observou a desconexão no ponto em que deveria retê-la. O ensaio parou com a entrada ainda enfileirada. O encerramento do runtime de teste também reportou falhas. A inspeção posterior confirmou os listeners fechados, as chaves TLS temporárias removidas e nenhum executor do ensaio em execução.

Passaram 14 regressões instaladas de expiração do escritor silencioso e fila. Estas três rodadas contribuíram evidências parciais. O ensaio posterior confirmou SI-T-H09 com dois sockets independentes e o fechamento canônico no mesmo fluxo. [Qualificação concluída](si037-codex-transport-expiry.md)
