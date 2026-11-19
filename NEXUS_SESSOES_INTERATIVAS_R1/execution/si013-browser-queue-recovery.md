# SI-013, SI-014 e SI-036 · Fila e recuperação de envio na Home

O ensaio usou o Nexus e o Connector instalados em loopback, um navegador Chromium e um processo real do Pi 0.87.1. O Pi executou com um provedor sintético e rede externa bloqueada.

Para SI-T-E07, mantive o primeiro turno em execução. A API aceitou os dois pedidos com HTTP 202. A Home mostrou os dois itens como “Queued for the next turn”. Os recibos e o SQLite confirmaram que a fila ainda tinha zero operações associadas. O conteúdo só apareceu como mensagem nativa depois da entrega ao Pi.

Para SI-T-E08, o Playwright deixou o segundo POST chegar ao Nexus e descartou a resposta depois do HTTP 202. A Home mostrou que o envio precisava de confirmação e guardou a referência. O recarregamento consultou a mesma intenção e recuperou a fila. Em uma aba descartável, restaurei a mesma referência e retive a resposta do GET para verificar o intervalo de recuperação. O editor e o botão de envio ficaram bloqueados até a chegada do recibo, e essa aba emitiu zero POSTs.

Depois de liberar o turno de teste, cada entrada foi entregue uma vez na mesma sessão. Os três turnos tiveram resultados canônicos, o SQLite passou na verificação de integridade e o fechamento canônico encerrou o Pi. Passaram também 44 testes instalados de fila, recibos e contrato e 19 testes de componente.

A primeira captura usava a rota de agente em vez da rota de gerenciamento da Home. No ensaio final, a verificação retomou a mesma fila já gravada e conferiu os IDs pela requisição e pelo SQLite. O descarte da resposta foi simulado. Outras falhas de rede, leitor de tela e aceite humano seguem pendentes.

Este marco atualiza as evidências e o ledger. O rollback reverte o commit de evidências no Nexus e dispensa migração. A próxima etapa do compositor é diferenciar o rótulo de envio quando o estado ocioso ou ocupado for comprovado pelo servidor.

[Dados e hashes dos ensaios](si013-browser-queue-recovery.json)
