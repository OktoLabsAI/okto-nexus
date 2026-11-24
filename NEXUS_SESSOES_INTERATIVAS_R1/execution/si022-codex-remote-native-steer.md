# SI-022, SI-024 e SI-031 · Reorientar pelo visualizador Codex via Connector

No Windows, o Nexus, o daemon Connector e o Core foram carregados dos wheels fixados. O visualizador Codex 0.170.0 abriu em ConPTY a thread que o app-server Codex 0.157.0 já executava. O teste manteve a resposta inicial em espera e enfileirou outra mensagem pela API usada pela web.

Digitar a instrução no visualizador abriu a revisão com o texto e o identificador do turno. A revisão ainda não tinha criado um envio. Ctrl+Y despachou um único `turn/steer` para o turno original. O app-server confirmou o mesmo identificador. Ctrl+] desanexou o visualizador e restaurou o console. O CLI recuperou a mesma intenção com estado `ACCEPTED_NATIVE` enquanto a mensagem da web ainda aguardava na fila.

Ao liberar a resposta inicial, a instrução reorientada apareceu na próxima requisição de inferência do turno original. A mensagem da web seguiu em outro turno da mesma thread e do mesmo processo. A auditoria em modo somente leitura encontrou dois resultados associados às respectivas operações, uma abertura nativa, um fechamento canônico e zero violações de chave estrangeira no Nexus e no journal do Connector.

O ensaio nativo e oito regressões instaladas passaram. Na primeira tentativa, o journal do Connector reteve o recibo `SUBMITTED` da abertura, mas o Nexus aguardou até o fim da janela sem recebê-lo. A causa dessa falha de publicação segue indeterminada. A repetição usou consultas de recibo menos frequentes e uma janela de observação maior no roteiro descartável. [Comandos, hashes e resultados](si022-codex-remote-native-steer.json)

A prova cobre as versões descritas nesta máquina, com três respostas de modelo simuladas em loopback. A campanha com provedor e o aceite humano seguem pendentes. A medição adicional no macOS e a prova entre máquinas ficam adiadas. Este marco altera a matriz e o ledger, dispensa migração e pode ser revertido pelo commit. [Matriz](si027-session-capability-matrix.md) [Qualificação](si041-qualification-checkpoint.md)
