# SI-035 · Queda do Server e disputa pela escrita no pacote instalado

Os ensaios usaram Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 instalados no Windows. A matriz de quedas usou processos descartáveis do Server e um peer do protocolo Codex. A disputa de terminais usou Pi 0.87.1 real com um executor remoto pelo Connector em loopback e respostas simuladas. [Pacotes, resultados e hashes](si035-current-faults-and-writer-contention.json)

Dois terminais em ConPTY confirmaram a transferência a partir da mesma revisão de escrita enquanto o primeiro turno do Pi estava ativo. Um recebeu o próximo epoch. O outro foi recusado e o editor anterior saiu desativando a colagem delimitada. O rascunho sem envio ficou fora da fila. Recuperar o recibo da entrada original devolveu o mesmo ID. As duas entradas aceitas chegaram em ordem, uma vez cada, ao processo Pi que já executava o turno inicial. O SQLite registrou uma sessão, três turnos, três resultados e um fechamento canônico.

Repeti a disputa com três logins independentes. Os dois concorrentes receberam HTTP 404 ao consultar o recibo do autor anterior. O vencedor registrou sua entrada em nome do próprio login, e a primeira entrada preservou seu autor.

A matriz interrompeu o Server em dez cenários nas fronteiras de gravação da saída, do recibo ou da publicação. Em cada caso, o registro do peer contou um único `turn/start`. Ao reiniciar, o Server recuperou o resultado somente quando a conclusão já estava durável. Os dois casos de fila confirmaram os seguintes estados.

| Fronteira da queda | Entrada original | Recibo preservado | Entrada seguinte |
| --- | --- | --- | --- |
| Escrita no peer antes de confirmar submissão | `DELIVERY_UNKNOWN` | `SUBMISSION_STARTED` | `BLOCKED_SESSION`, sem operação |
| Conclusão gravada no Core antes da publicação | `ACCEPTED_NATIVE` | `SUCCEEDED` | `BLOCKED_SESSION`, sem operação |

Passaram 46 regressões de arbitragem, cancelamento, reorientação, pausa, recuperação e mudança de geração. A migração 191 e seus requisitos para voltar a um wheel anterior permanecem descritos no ensaio original. [Queda do processo e migração](si035-server-process-crash.md) [Reconexão com Pi ativo](si035-pi-reconnect-candidate.md) [Transferência produtiva](si035-codex-productive-transfer.md)

Este marco atualiza o ledger e as evidências. O rollback consiste em reverter o commit. A qualificação de campanha de SI-T-G06, SI-T-G07 e SI-T-G15 permanece aberta. A etapa seguinte é SI-036, experiência no navegador e acessibilidade.
