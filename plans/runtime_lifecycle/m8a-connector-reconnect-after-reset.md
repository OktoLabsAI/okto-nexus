# M8a: Connector reconecta após reset e reinício do Nexus

## Falha e correção

Depois de um reset com preservação de agentes, o Server apagou o histórico de
execução, mas o journal durável do Connector continuou a declarar sessões antigas
já liberadas. A reconciliação procurava cada claim no histórico canônico; a
ausência de qualquer sessão levantava `ValueError` e fechava o controle WebSocket
com `4406`. Por isso o Connector permanecia em Recovering após reiniciar o Nexus.

O Server agora distingue claims de sessões anteriores ao reset de claims atuais.
Somente após um reset com preservação, para um Connector remoto autenticado, ele
aceita um claim sem sessão canônica quando o estado é `RELEASED`, o processo está
`EXITED` ou `NOT_STARTED`, há prova SHA-256 sintaticamente válida e exatamente um
watermark correspondente. A sessão antiga não altera o estado atual nem libera
operações novas. Claims não liberados ou malformados continuam bloqueando a
reconciliação. Sem reset, a recusa antiga permanece. O endpoint registra tipo,
código, estágio e localização da falha protocolar sem registrar o payload.

## Validação delimitada

- Testes direcionados de reconciliação: 16 passaram, incluindo claim válido
  após reset, três variantes inválidas e rejeição de relatório malformado.
- O Nexus 0.3.1 foi empacotado e instalado em `build/m6d-env`, com Core 0.0.12;
  o processo executado veio de `site-packages`, sem `PYTHONPATH` de source.
- No fixture descartável em `127.0.0.1:8204`, o Connector local 0.0.10
  reconectou automaticamente após encerramento forçado e reinício do Server
  instalado, alcançando `CONTROL_READY`, `CONNECTED` e `authorized=true`.
- Pela interface Meta-harness, uma nova mensagem ao Pi real retornou exatamente
  `M8_INSTALLED_RESTART_OK` com ACK `1/1`.

Durante uma tentativa intermediária, a autorização de runtime com duração de
60 minutos expirou pelo relógio e impediu a renovação da lease. A autorização foi
ajustada pela interface para prazo ilimitado antes da prova instalada. Esse evento
não foi atribuído à falha `4406`; uma resposta da tentativa anterior também foi
recuperada, com ACK `1/1`, após a retomada do Connector.

Este checkpoint cobre o Connector na mesma máquina e um Pi real após reset e
reinício do Nexus instalado. Não fecha a matriz completa de M8 nem equivale a
teste em host remoto físico.
