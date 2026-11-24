# SI-011 · Controle da fila pelo terminal

`session queue` consulta a fila da sessão selecionada. `--pause` e `--resume` exibem o alvo e pedem confirmação interativa. O servidor aplica a ação pelo controle canônico com a geração, a revisão da fila e a autorização vigentes. Consultas aceitam `--json`. Uma mudança com resposta perdida ou interrompida orienta a consultar o estado da mesma sessão antes de solicitar outra mudança. [Comandos](../../docs/terminal-work.md#control-the-session-queue)

O ensaio passou com Claude Code 2.1.328 no Windows ConPTY e Connector nesta máquina. O visualizador interrompeu o turno exato e pausou a fila. O comando público pediu confirmação enquanto o item permanecia pendente. Após a confirmação, o item original foi entregue uma única vez ao mesmo processo. A auditoria encontrou a concessão original, um único processo nativo e o fechamento canônico. O modelo respondeu em loopback.

Passaram 96 regressões no código-fonte e 96 nos pacotes instalados. Um teste exclusivo de POSIX foi ignorado no Windows. A prova nativa cobre a retomada com um item pendente. Consulta, pausa, revisão divergente e resposta incerta foram exercitadas nos testes focados.

O marco dispensa migração. A reversão do commit do Nexus restaura a superfície de CLI anterior. [Resultados, artefatos e limites](si011-terminal-queue.json)

Na demonstração com dois processos Pi no Windows, o CLI consultou e controlou a fila de Beta sem alterar a revisão da fila de Alpha. Recusar a confirmação manteve a pausa. Confirmar a retomada revalidou a autorização do envio pendente, que ficou bloqueado após o vencimento. [Demonstração de escopo entre sessões](si041-two-session-native-ack.md#duas-sessões-com-a-fila-pelo-cli)
