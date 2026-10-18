# M7c — Intervalo de abertura remota Pi medido em receipts duráveis

Data: 2026-10-18 UTC. Diagnóstico read-only da execução real M6d pela UI do Nexus, com wheels instaladas. Não altera código nem fecha o gate de latência M7.

Consulta read-only ao SQLite do home descartável `build/runtime-m6d-ui/home/nexus.db`, tabelas `execution_operations` e `execution_receipts`, filtrada apenas ao agente `m6d-pi`. A consulta não leu nem publicou payloads, credenciais ou conteúdo das mensagens. Os horários de criação e receipt usam o relógio UTC persistido pelo Nexus.

| Operação | Criada | Primeiro `SUBMITTED` | Intervalo | Terminal `SUCCEEDED` |
| --- | --- | --- | --- | --- |
| Primeira `runtime.open` (`op_65722d16…`) | 00:25:34.196 | 00:27:08.694 | 94,498 s | não há receipt terminal de open; o terminal da UI mostrou harness pronto às 00:27:09 |
| Primeiro `turn.submit` (`op_5e6a0581…`) | 00:25:34.216 | 00:27:11.046 | 96,830 s desde criação | 00:27:17.298 |
| Pós-restart `runtime.open` (`op_243893ad…`) | 00:29:59.233 | 00:31:43.755 | 104,522 s | não há receipt terminal de open; o terminal mostrou harness pronto às 00:31:45 |
| Pós-restart `turn.submit` (`op_9df6281e…`) | 00:29:59.250 | 00:31:46.287 | 107,037 s desde criação | 00:31:51.742 |
| Reuso de sessão `turn.submit` (`op_3451aef3…`) | 00:33:00.665 | 00:33:02.645 | 1,980 s | 00:33:07.612 |

As duas chamadas de `turn.submit` foram criadas junto com `runtime.open` e esperaram a abertura da respectiva sessão. O terceiro turno reutilizou `ses_0bbc3b316b2e66d9274bc44564f25c63` após a substituição do owner embutido e não precisou de novo open. Em todos os casos a UI mostrou a resposta e ACK 1/1.

O intervalo de 94–105 s termina no primeiro receipt de open e pode conter espera na entrega, autorização, preparação, verificação da instalação, spawn e handshake. Os receipts atuais não marcam essas fronteiras internas; logo, esses números **não** atribuem os 94–105 s ao processo Pi ou ao hash da instalação. A medição anterior de 14.097 arquivos e o custo de identidade completa continuam hipóteses parciais, não causa estabelecida desta execução. O próximo passo M7 é acrescentar observação de fases sem payload sensível e comparar várias aberturas sob a mesma instalação/carga antes de otimizar o caminho dominante.
