# SI-031 · Oferta do terminal Claude pelo Connector

O ensaio usou os entrypoints instalados do Nexus e do Connector em Windows ConPTY e um Claude Code 2.1.328 gerenciado pelo executor. `connect --no-interactive` pulou a oferta e, sem flag, Enter aceitou o padrão Não. Com `-i`, o Connector abriu o visualizador em leitura no terminal atual. O CLI consultou o login humano associado ao Server e recebeu o resultado do turno da sessão remota exata. Ctrl+C desanexou o visualizador, e o Connector recebeu o recibo `claude_remote_read`.

Antes do fechamento canônico, as três escolhas preservaram o vínculo, a concessão e as operações já admitidas. O mesmo processo produziu o resultado. A auditoria SQLite confirmou uma abertura nativa, um envio, um resultado, um anexo encerrado e um fechamento. O teste usou um login Nexus descartável e uma implementação de cofre restrita à fixture. O launcher filtrou a variável fictícia de credencial antes de iniciar o processo filho do Nexus. [Resultados, auditoria e hashes](si031-current-claude-connect-offer.json)

Passaram 92 regressões do Connector e 23 do Nexus instalado. Nas rodadas de preparação, o roteiro precisou aguardar o anexo ativo depois do banner, interpretar o texto com sequências de controle do terminal e validar o registro estruturado da única requisição de modelo. O modelo respondeu apenas em loopback. [Oferta do Codex](si031-connector-connect-terminal.md) · [Oferta do Pi](si031-connector-pi-offer.md)

A etapa atualiza evidências e pode ser revertida por Git, sem migração. A operação em máquinas distintas continua adiada, e o cenário de compatibilidade SI-T-I02 conserva o gate de campanha.
