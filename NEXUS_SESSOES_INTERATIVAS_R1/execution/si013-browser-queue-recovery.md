# SI-013, SI-014 e SI-036 · Fila e recuperação de envio na Home

O ensaio usou o Nexus e o Connector instalados em loopback, um navegador Chromium e um processo real do Pi 0.87.1. O Pi executou com um provedor sintético e rede externa bloqueada.

Para SI-T-E07, mantive o primeiro turno em execução. A API aceitou os dois pedidos com HTTP 202. A Home mostrou os dois itens como “Queued for the next turn”. Os recibos e o SQLite confirmaram que a fila ainda tinha zero operações associadas. O conteúdo só apareceu como mensagem nativa depois da entrega ao Pi.

Para SI-T-E08, o Playwright deixou o segundo POST chegar ao Nexus e descartou a resposta depois do HTTP 202. A Home mostrou que o envio precisava de confirmação e guardou a referência. O recarregamento consultou a mesma intenção e recuperou a fila. Em uma aba descartável, restaurei a mesma referência e retive a resposta do GET para verificar o intervalo de recuperação. O editor e o botão de envio ficaram bloqueados até a chegada do recibo, e essa aba emitiu zero POSTs.

Depois de liberar o turno de teste, cada entrada foi entregue uma vez na mesma sessão. Os três turnos tiveram resultados canônicos, o SQLite passou na verificação de integridade e o fechamento canônico encerrou o Pi. Passaram também 44 testes instalados de fila, recibos e contrato e 19 testes de componente.

A primeira captura usava a rota de agente em vez da rota de gerenciamento da Home. No ensaio final, a verificação retomou a mesma fila já gravada e conferiu os IDs pela requisição e pelo SQLite. O descarte da resposta foi simulado. Outras falhas de rede, leitor de tela e aceite humano seguem pendentes.

Este marco atualiza as evidências e o ledger. O rollback reverte o commit de evidências no Nexus e dispensa migração. A próxima etapa do compositor é diferenciar o rótulo de envio quando o estado ocioso ou ocupado for comprovado pelo servidor.

[Dados e hashes dos ensaios](si013-browser-queue-recovery.json)

## Escolha explícita e recuperação no pacote atual

No Edge, a Home ofereceu duas sessões Pi no mesmo vínculo. O compositor
só apareceu depois da seleção explícita da sessão mais antiga. Enter
enviou o texto exato por um único POST. O Server devolveu HTTP 202 com
o item na fila, antes de vincular uma operação. O Playwright descartou
essa resposta depois do commit.

O editor preservou o rascunho e bloqueou novos envios durante a consulta
do recibo. A Home recuperou o item original com um GET. O Pi recebeu
uma única mensagem com papel `user` e texto idêntico. O SQLite confirmou
um resultado para essa operação, zero entregas pelo barramento Operator,
zero trabalhos na outra sessão e dois fechamentos canônicos.

Passaram o ensaio com Edge e Pi 0.87.1 no Windows, a auditoria somente
leitura e 425 testes de frontend em Node. O Pi usou respostas simuladas
com rede externa bloqueada. A recuperação por recarregamento e os casos
de IME e foco conservam as evidências dos seus candidatos. O registro
pode ser revertido pelo commit, sem migração.
[Relatório, versões e hashes](si013-current-composer.json)
