# SI-022, SI-032 e SI-035 · Retomada do WebSocket com Pi ativo

Com os wheels atuais, abri uma sessão Pi 0.87.1 pelo Connector e enfileirei uma mensagem no editor em ConPTY enquanto o primeiro turno estava ativo. Interrompi o WebSocket de controle desse Connector. O editor anterior saiu e restaurou o modo do console. O Connector retomou o canal com a mesma identidade e geração. A sessão e o processo Pi continuaram ativos, com a mesma concessão produtiva e a fila preservada.

Um segundo editor entrou na mesma sessão e acompanhou o resultado do turno original. O despachante entregou a mensagem enfileirada uma vez. A consulta recuperou o mesmo recibo, e o histórico nativo registrou exatamente os dois prompts esperados. O fechamento canônico encerrou o processo Pi.

Passaram o ensaio nativo e oito regressões da API de continuidade e retomada. O corte ocorreu na conexão isolada em loopback no Windows e o Pi usou respostas simuladas. SI-T-H12 ficou aprovado nesse cenário. A validação entre máquinas distintas com TLS segue pendente. [Dados e hashes](si035-pi-reconnect-candidate.json)

O caso anterior fora da janela de retomada permanece como evidência de reconexão em nova geração. Esta etapa atualiza o ledger e pode ser revertida sem migração. [Reconexão após expiração](si022-pi-full-reconnect.md)
