# SI-008 e SI-035 · Recibos após queda do processo do Server

A fila agora registra `DELIVERY_UNKNOWN` após a contenção comprovada da sessão quando o recibo canônico ainda indica possível efeito e falta confirmação de entrega. O recibo do Core conserva o estágio original. O Server mantém o mesmo ID da entrada e da operação, sem reenviar o texto.

No Windows, um processo descartável do Server terminou abruptamente em dois pontos. A fixture de protocolo Codex executou em um subprocesso e registrou um único `turn/start` por cenário.

| Ponto da queda | Entrada após o reinício | Recibo canônico |
| --- | --- | --- |
| Depois do envio ao peer e antes do recibo de submissão | `DELIVERY_UNKNOWN` | `SUBMISSION_STARTED` |
| Depois do resultado durável no Core e antes de sua publicação no Nexus | `ACCEPTED_NATIVE` | `SUCCEEDED` |

O próximo item ficou em `BLOCKED_SESSION`, sem operação vinculada. As consultas HTTP em loopback devolveram repetidamente o mesmo recibo da entrada. O processo substituto encerrou normalmente. O subprocesso de teste forneceu a resposta pelo protocolo nativo, com zero chamadas a provedores externos. [Resultados, versões e hashes](si035-server-process-crash.json)

A migração 191 atualiza o estado da fila em bancos existentes quando há prova persistida de contenção para a sessão e geração. A atualização preserva operações, recibos do Core, resultados e entradas posteriores. O teste aplicou a migração duas vezes a cópias de bancos produzidos pelo wheel anterior e confirmou que a segunda aplicação não mudou os dados. Para voltar a um wheel que desconhece a migração 191, é necessária uma cópia coerente do banco anterior à migração.

A campanha SI-T-G15 continua pendente.
