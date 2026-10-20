# M7p: one-shot ilimitado pela interface, com limite de recursos observado

Em 2026-10-18, o Nexus 0.3.1/Core 0.0.12 instalado foi iniciado em fixture
descartável em `127.0.0.1:8204`; o Nexus global permaneceu parado. Pela UI
Agents > Connections, o Pi 0.87.1 embedded foi alterado de sessão compartilhada
para one-shot com `max_parallel=0` (ilimitado), `warm_instances=0`, fila padrão
32 e prazo de 300 s. O teste de conexão respondeu, Finish salvou, e Agents
mostrou `0/Unlimited available`. A política durável da chamada confirmou
`max_parallel=0`; não houve alteração de outros agentes.

Pela UI Meta-harness, três mensagens privadas curtas ao Pi no workspace M5V
pediram marcadores distintos A, B e C. Todas retornaram exatamente
`M7P_UNLIMITED_A/B/C`, com ACK 1/1 e chamadas `SUCCEEDED` em sessões one-shot
distintas. Os tempos UTC lidos do banco durável foram:

| Chamada | Enfileirada | Execução iniciada | Resultado final |
| --- | --- | --- | --- |
| A | 11:59:22.776 | 11:59:47.871 | 11:59:56.124 |
| B | 11:59:42.609 | 12:00:13.116 | 12:00:20.837 |
| C | 12:00:02.112 | 12:00:28.416 | 12:00:38.140 |

As operações `runtime.open` começaram às 11:59:23.098, 11:59:43.030 e
12:00:02.458; as duas primeiras se sobrepuseram, assim como a segunda e a
terceira. Não houve três aberturas simultâneas, portanto este teste não prova
capacidade acima do limite finito de duas instâncias usado em M7o.

A memória física livre medida antes dos envios era 10,77 GiB e, ao final,
4,58 GiB. A inspeção posterior não encontrou processo Pi/Node remanescente
do fixture, e as três sessões estavam fechadas. Por cautela, não fiz outra
rajada com apenas 0,58 GiB de margem sobre o piso de 4 GiB usado no protocolo
M7o. Após encerrar somente o Nexus descartável, a memória livre voltou a
10,68 GiB; as portas 8202/8204 e os processos do fixture ficaram livres.
Não há amostragem contínua nem atribuição comprovada da variação de RAM a um
processo específico. O critério de modo ilimitado acima de duas instâncias
permanece aberto para uma medição com orçamento físico controlado.
