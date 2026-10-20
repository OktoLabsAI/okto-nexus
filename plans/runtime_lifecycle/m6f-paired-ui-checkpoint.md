# M6f — comparação local pareada pela interface

Data: 2026-10-20 UTC. Checkpoint parcial do critério M6 do ADR do Connector; sem decisão de adoção.

## Instalação e configuração

- Nexus 0.3.1 instalado de wheel em `build/m2g-nexus-verify`, Core 0.0.12 do wheel da CI 39336889894 (SHA-256 `fe0659ec366029a72475cdf300b0be1705e796d32044bf9c0ab0bc81d3b574b5`) e Connector 0.0.10 do wheel da CI 39343006146 (SHA-256 `a25fcda8dffeefa05da5d47656b41c29a8975e988c04c820f1b42ec5e46f4bd9`).
- Nexus descartável em `127.0.0.1:8204`, home persistente `build/runtime-m6d-ui/home`; Connector instalado em processo separado com IPC experimental `named_pipe`, estado em `C:\Users\jpamb\AppData\Local\okto-nexus-connector-m6e-20261019`.
- Pi 0.87.1, workspace M6D. Agentes `m5m-pi-new` (embedded) e `m6e-pi` (Connector), ambos one-shot com 2 instâncias paralelas e 1 aquecida. A UI do remoto ainda mostrava sessão compartilhada apesar dos limites preenchidos; nesta execução selecionei explicitamente one-shot e salvei em Finish. Depois disso, ambos os cards exibiram `Live instance pool 1/2 available`.
- Memória física livre observada: 8,58 GiB antes das chamadas e 8,78 GiB depois do reinício. Processo HTTP do Nexus PID 30032: 183.775.232 bytes de working set; daemon Connector PID 6944: 96.055.296 bytes. São observações isoladas, não custo total dos filhos Pi nem benchmark de adoção.

## Exercício pela UI real

No Meta-harness do workspace M6D, enviei a mesma tarefa curta de resposta exata, sem alterar arquivos:

| Caminho | Assunto | Resposta visível | ACK |
| --- | --- | --- | --- |
| Connector separado | `M6E_REMOTE_PI_01` | `M6E_REMOTE_PI_01_OK` | 1/1 |
| Embedded | `M6E_LOCAL_PI_01` | `M6E_LOCAL_PI_01_OK` | 1/1 |

Em seguida interrompi apenas o Nexus e o reiniciei com o mesmo home; o Connector permaneceu vivo. O status do Connector passou por `PUBLISHING_INVENTORY`/`CONNECTION_ERROR` durante a queda e voltou automaticamente a `CONTROL_READY`/`CONNECTED`. O erro de transporte foi registrado às 00:26:46.659 UTC e a reconexão às 00:27:00.167 UTC; intervalo observado de cerca de 13,5 s entre esses pontos. A UI voltou a aceitar mensagem privada ao remoto; `M6E_REMOTE_AFTER_RESTART` recebeu `M6E_REMOTE_AFTER_RESTART_OK` com ACK 1/1. Nenhuma aprovação, recriação de agente ou reinício do Connector foi necessária.

## Limite do checkpoint

Isto comprova respostas reais pareadas com configuração one-shot quente, pool recomposto e recuperação após reinício do Nexus. Não comprova equivalência de latência: a instrumentação desta passagem só preservou timestamps da interface para envio e observação, não monotonic timestamps de todas as fronteiras. Continuam pendentes os cortes fixos do ADR: interrupção de controle com trabalho em voo, expiração/revogação de lease e geração, replay/receipts sem duplicação, parada nas três fases, upgrade/rollback e comparação completa de disponibilidade/custo. Nenhum critério novo foi acrescentado.
