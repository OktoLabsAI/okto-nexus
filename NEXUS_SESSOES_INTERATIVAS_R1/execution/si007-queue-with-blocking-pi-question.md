# SI-T-B07 — Mensagem na fila durante uma pergunta do Pi

O Pi 0.87.1 abriu uma pergunta bloqueante na sessão descartável. Uma mensagem comum com o texto “Sim” entrou pela API autenticada e permaneceu em `QUEUED`, sem operação vinculada, durante três avaliações reais do despachante. A pergunta continuou pendente e nenhuma resposta nativa foi enviada.

O operador respondeu três perguntas pelos controles dedicados, com o escopo da sessão validado na API, em Attention e na Home. A mensagem permaneceu na fila até o Pi registrar `agent_settled` no primeiro turno. Depois seguiu como um segundo turno na mesma sessão, com o texto original intacto. A auditoria do SQLite confirmou três operações de resposta, dois turnos aceitos e dois resultados na mesma sessão. O fechamento canônico concluiu o ensaio. [Relatório e hashes](si007-queue-with-blocking-pi-question.json)

O ensaio usou o Pi instalado, respostas determinísticas, HTTP via TestClient, SQLite e o despachante dos wheels instalados. A evidência do Edge em um candidato anterior fica registrada separadamente. Este marco acrescenta verificação ao ledger e dispensa alteração de produto ou migração. O commit pode ser revertido para retirar o registro da verificação. [Ensaio anterior no Edge](si025-pi-native-questions.md)
