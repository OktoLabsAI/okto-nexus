# M04/M06 — loop de dispatch remoto com owner persistido

Status: **integração parcial verificada**, sem fechamento de milestone ou gate.

## Entrega

O handler WSS inicia um único `ExecutionDispatchPump` após aceitar a
reconciliação. O loop reserva capacidade no outbox antes de esperar o writer,
revalida credencial e autoridade depois da espera e envia o envelope somente
após o commit de `SENDING`. Leitura do socket e respostas de lease continuam
independentes, com escrita serializada e timeout de cinco segundos.

A migração 079 persiste conexão e geração da reserva. O owner atual pode
recuperar reservas comprovadamente não enviadas de conexões substituídas;
tokens antigos não conseguem enviar nem liberar a nova reserva. No shutdown,
o owner aguarda o produtor de banco, libera apenas `RESERVED` e marca envios
sem recibo como `RECONCILING`. Cancelar quem aguarda o shutdown não abandona
o produtor. Envio no socket não é ACK durável do executor.

Falhas definitivas de autorização antes do envio resolvem a operação com erro
estruturado do Server, sem fabricar receipt Core. A consulta mostra o escopo
canônico completo, distingue erro de dispatch e receipt, e informa efeito
possível quando o envio já foi iniciado e ainda não há receipt.

A decisão está na [ADR 0006](../../docs/adr/0006-owned-remote-dispatch.md).

## Prova executada

O teste público cria pré-condições de identidade e usa as rotas de registro,
inventário, realização, consentimento delegado, binding, grant, tickets,
resolve/admit/query e receipts. O loop real do Server entrega pelo WSS as
cinco operações open/submit/steer/interrupt/close. Core instalado executa
contra peer nativo sintético; o helper Connector instala a lease pelo WSS.
O teste não chama manualmente reserve/begin para substituir o loop.

O cenário de desconexão após receber a abertura confirma uma única operação,
uma tentativa, efeito possível, retry proibido e consulta pelo mesmo ID.
Reconectar solicita reconciliação; um relatório vazio não resolve a pendência
nem provoca uma segunda abertura. Testes com barreiras verificam revogação
durante espera do writer, falha após possível escrita, cancelamento enquanto
a reserva está sendo persistida e substituição do owner antigo.

| Campanha | Resultado | Alcance |
|---|---|---|
| R4 completa, rerun final | 102 passes | Fonte Nexus, contratos e integração técnica |
| Migrações | 7 passes | Schema novo e regressão de migração |
| Pacotes instalados | 70 passes | Python 3.13 isolado, fora dos clones, bytes conferidos contra wheels |
| Ciclo de vida dirigido | 6 passes | Jornada pública e quatro testes de ownership; sobrepõe as demais campanhas |

Os resultados não são somados como casos únicos. As primeiras tentativas foram
preservadas: três testes assíncronos falharam por ausência do plugin no ambiente
de desenvolvimento; foram convertidos ao padrão `asyncio.run` já usado pelo
projeto, e os quatro testes passaram. A regressão seguinte teve 101 passes e
uma falha: o teste antigo esperava `possible_effect=False` para `SENDING` sem
receipt. A expectativa foi corrigida para efeito possível e retry proibido;
o caso dirigido e o rerun completo passaram. Há um warning de depreciação
do TestClient, sem skips nas campanhas finais.

O [manifesto](test_runs_20260930_dispatch_pump.json) registra hashes de fonte,
XMLs, comandos e build/instalação. Nexus foi construído a partir de staging
novo, preservando os assets preexistentes do usuário. Core permanece em
`0.2.28.dev0`, SHA-256
`27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c`.
Connector e Core não receberam alterações neste incremento.

## Pendências de aceite

- Integrar o daemon Connector, StateStore, reader/multiplexação e resolver
  físico de realização. O teste usa peer, gate de qualificação e mapeamento
  físico controlados; ainda não qualifica o daemon nem provider.
- Compor execução embedded com o owner de `serve`, usando a mesma admissão.
- Implementar reconciliação não vazia/paginada e recuperação de receipts;
  neste incremento a pendência permanece bloqueada, sem reenvio cego.
- Completar ingresso WSS de receipts, decisões/input, UI/CLI e governança.
- Qualificar filas, watchdog, retenção, métricas e orçamento total de shutdown.
  O limite atual de reservas é 4 regulares/2 de controle, com 256/128 KiB;
  o frame Server continua limitado a 64 KiB. Os defaults normativos de
  32/8 itens e frame de 1 MiB precisam ser reconciliados e testados em M00/M11.
- Executar providers reais, Windows/Linux, hosts independentes, auditoria
  US English, migração/rollback e aceite sobre artefatos finais.

Reservas legadas sem owner conhecido não são automaticamente liberadas.
Espera de banco indefinida ainda exige supervisão e orçamento de shutdown.
`R4_BUNDLE_EXECUTABLE` e `remote_execution_ready` continuam falsos.
