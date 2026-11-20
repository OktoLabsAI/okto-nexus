# SI-T-B20 e SI-T-C08 — Cancelamento isolado e promoção da fila

Com o Pi 0.87.1 executando uma ferramenta retida pela fixture, o Nexus
recebeu dois envios pela API. O cancelamento do primeiro retornou HTTP 200.
O turno original continuou ocupado e terminou com sucesso. A entrada
seguinte conservou sua posição e chegou uma vez ao Pi depois que o turno
original terminou. A auditoria SQLite confirmou que o item cancelado nunca
ganhou uma operação e que os três resultados pertenciam à sessão original.
O controle canônico encerrou a sessão ao fim do teste.

Quatro regressões com os wheels instalados também passaram. No peer Codex
simulado, promover uma entrada com a revisão atual removeu sua elegibilidade
para a fila e enviou uma única reorientação ao turno revisado. Repetir o
pedido recuperou a mesma operação. Quando o dispatcher já tinha consumido
a reserva da entrada, cancelar ou promover devolveu HTTP 409 e o envio
original seguiu uma única vez. O teste também cobriu o cenário em que
o cancelamento vence a disputa com o dispatcher.
[Resultados e hashes](si009-isolated-cancellation-and-promotion.json)

O cancelamento usou o Pi instalado com respostas de modelo simuladas.
O ensaio da promoção usou HTTP, SQLite, dispatcher e peer de protocolo
simulado. Essa evidência cobre a transação e a concorrência no servidor.
A qualificação da promoção pelo frontend nativo fica em aberto.

O marco atualiza as evidências e o ledger. Reverter o commit remove esse
registro e dispensa migração.
