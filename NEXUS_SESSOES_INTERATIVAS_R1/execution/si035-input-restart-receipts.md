# SI-008 e SI-035 · Recibos de fila após reinício do Server

Reiniciei o ciclo completo de uma instância descartável do Server com os mesmos bancos SQLite e diário do Core. Uma falha injetada depois da escrita no peer impediu a publicação do recibo no primeiro Server. O segundo Server recuperou o recibo da operação original a partir do diário. O ensaio usou as rotas HTTP instaladas, o despachante real e um peer Codex sintético para observar as escritas.

Em uma variante, o Core registrou `OUTCOME_UNKNOWN`. Depois do reinício, a API devolveu `DELIVERY_UNKNOWN`, conservou o identificador da operação e indicou possível efeito, sem autorização para repetir o envio. Na outra variante, o diário já continha `SUCCEEDED`, e a API recuperou `ACCEPTED_NATIVE` para a mesma entrada. Cada variante registrou uma única escrita para a entrada testada e zero escritas após o reinício.

O recibo da mensagem seguinte ficou consultável com o login original. Após a sessão ser confirmada como encerrada, a API devolveu `BLOCKED_SESSION` com a mesma identidade, o texto preservado e nenhuma operação vinculada. Uma tentativa de enviar outra mensagem para a sessão encerrada foi recusada.

A primeira injeção usou um erro de integridade, que acionou o bloqueio do agente. Corrigi o roteiro para simular perda transitória na publicação e deixei a restauração automática da injeção em caso de falha do teste. Passaram as duas variantes e 20 regressões de recuperação, recibos e capacidade, com os pacotes instalados. O Ruff apontou duas ordenações de imports que já constavam no arquivo de testes.

O ledger registra SI-T-B13 e SI-T-B16 para o reinício isolado coberto. O teste reiniciou a aplicação e seus serviços em dois lifespans ASGI, com a falha de publicação injetada. A qualificação do encerramento abrupto de um processo do Server no sistema operacional segue em aberto. A etapa acrescenta testes e evidência e pode ser revertida sem migração. [Resultados e hashes](si035-input-restart-receipts.json)
