# SI-031 · Recuperação da confirmação de recibo no Connector

Se o envio HTTP de um recibo já gravado retornar indisponibilidade ou resultado incerto, o Connector revalida o vínculo e republica a mesma operação, revisão e conteúdo uma vez. O Nexus confere o digest e reutiliza o recibo quando a primeira tentativa já foi gravada. Revogação, incompatibilidade, conflito e uma segunda falha preservam o registro no journal para a recuperação existente. O retry atua sobre a publicação do recibo e mantém uma única execução nativa.

A perda do recibo observada no ensaio anterior deixou um registro `SUBMITTED` no Connector e uma sessão `OPEN_PENDING` no Nexus. O ensaio atual reproduziu separadamente a falha HTTP após o commit com o Nexus e o Connector nesta máquina. O Connector recuperou o recibo no mesmo canal. A causa exata do incidente anterior continua indeterminada. [Ensaio anterior](si022-codex-remote-native-steer.md)

O ensaio final usou o Codex e o visualizador reais com respostas simuladas em loopback. Depois da recuperação, o visualizador reorientou o turno original. A mensagem em fila foi concluída em outro turno da mesma sessão. A auditoria comprovou uma abertura nativa, um único recibo de abertura no Nexus, dois resultados e um fechamento canônico. As rodadas anteriores também recuperaram o recibo. O roteiro exigiu correções na espera pelo resultado final e na preparação do visualizador.

Passaram o ensaio nativo, 73 testes do Connector e nove regressões do Nexus instalado. As verificações de dependências e dos pacotes passaram.

O marco dispensa migração e atualiza o wheel fixado do Connector. Para reverter, reverta a mudança no Connector e restaure o pin anterior no Nexus. Preserve o journal e os recibos durante a reversão. [Dados, comandos e hashes](si031-connector-receipt-http-recovery.json)
