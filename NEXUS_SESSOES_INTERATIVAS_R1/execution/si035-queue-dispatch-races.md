# SI-035 · Disputas entre despacho e controles da fila

O teste coordena o despachante automático do Nexus e pedidos HTTP autenticados para a mesma entrada. Ele usa SQLite e o protocolo de capacidade do Core com um peer Codex sintético. Os pontos de espera ficam após a reserva e após o consumo da capacidade, antes do envio ao peer.

Quando o cancelamento chega primeiro, a API devolve HTTP 200 e conserva o recibo `CANCELLED` sem operação vinculada. O despachante resolve a reserva pendente, e a próxima entrada é entregue uma vez. O registro de envios do peer confirma zero ocorrências da entrada cancelada.

Quando o despacho chega primeiro, o recibo já está em `DISPATCHING` antes de qualquer escrita no peer. Remover ou reorientar a entrada devolve HTTP 409, inclusive ao usar as revisões atuais da entrada e da fila. Depois que o despachante prossegue, a entrada original chega uma vez como próximo turno, e a seguinte mantém sua posição. O banco conserva apenas as operações de envio esperadas.

Passaram 15 testes de concorrência e cancelamento e 14 de capacidade e controles, executados com os pacotes instalados. O ledger registra SI-T-B19 e SI-T-C09. A recuperação de envio incerto após reinício do Server segue para outro ensaio. Esta etapa acrescenta testes e evidência, com reversão pelo commit e sem migração. [Dados e hashes](si035-queue-dispatch-races.json)
