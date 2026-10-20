# M8 — ensaio offline da migração do backup global

Data: 2026-10-20 UTC. O Nexus global permaneceu parado, sem listener nas portas 8202/8204. A wheel instalada Nexus 0.3.1 restaurou o backup validado da geração 73, `build/m8-global-preupgrade-backup-20261019`, em um novo diretório descartável `build/m8-global-rehearsal-20261020`. O comando de restore retornou `PASS` e `native_processes_started=0`.

Na cópia restaurada, `MigrationRunner.apply()` da mesma wheel aplicou as versões de schema 146–152, sem iniciar Server, Connector ou harness. A leitura SQLite antes/depois registrou:

| Registro | Antes | Depois |
| --- | ---: | ---: |
| Schema | 145 | 152 |
| Agentes | 7 | 7 |
| Mensagens | 325 | 325 |
| Entregas | 337 | 337 |
| Handoffs | 6 | 6 |
| Artefatos | 3 | 3 |
| Violações de chave estrangeira | 0 | 0 |

O mesmo ambiente instalado iniciou depois o Nexus a partir da cópia migrada em `127.0.0.1:8204`, com integrações de harness desativadas. O dashboard respondeu HTTP 200; o processo PID 17664 foi encerrado e a porta 8204 ficou livre. O backup original permanece validável e imutável; somente a cópia foi migrada. O ensaio comprova migração estrutural e boot HTTP, não startup com harnesses nem disponibilidade pós-upgrade. A matriz Nexus instalada e o rollout global controlado ainda são gates separados. O script e o estado do ensaio ficam apenas em `build/`, ignorados pelo Git.
