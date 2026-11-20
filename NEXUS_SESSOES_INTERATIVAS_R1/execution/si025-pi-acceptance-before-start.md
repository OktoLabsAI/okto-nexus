# SI-T-A11 — Aceite do Pi antes do início do turno

No pacote anterior, o Pi 0.87.1 confirmou o preflight de `prompt`
antes de iniciar o agente. O Nexus registrou `SUBMITTED` e deixou
a entrada em `DISPATCHING`, apesar da resposta positiva do Pi.

O Core agora registra `ACCEPTED` após uma resposta positiva,
correlacionada pelo RPC do Pi hospedado e revisado. A Home usa
`ACCEPTED_NATIVE` para a entrada. A operação canônica continua
carregando o desfecho do turno. O Connector reconhece o aceite
ao atualizar seu diagnóstico. O Nexus preserva a projeção de
entrega de coordenação para o build Pi verificado e mantém o
recibo em andamento na reconciliação e nas leases de trabalho.

No Edge, uma mensagem recebeu HTTP 202 e apareceu como
“Accepted by the harness” com o início do turno retido na
fixture. A API ainda não tinha um resultado e o painel não
mostrou texto novo do modelo. A liberação iniciou o mesmo
turno uma vez. O SQLite registrou `ACCEPTED` antes de
`SUCCEEDED`, e o controle canônico encerrou a sessão.
[Dados, hashes e relatório do navegador](si025-pi-acceptance-before-start.json)

Passaram 84 testes de Core, 36 de Connector, 69 na rodada de
integração e 15 na revisão de recibos do Nexus. O teste de
desligamento com agendador lento excedeu o prazo tanto no
baseline quanto no primeiro candidato. Os wheels finais foram
montados a partir de cópias limpas. Um ajuste final de
formatação no Nexus foi comparado com o wheel verificado por
igualdade da árvore sintática.

A regressão foi reexecutada com os wheels finais depois de
alinhar a expectativa do teste ao desligamento cooperativo.
Os cenários cooperativo e de parada explícita passaram.
[Relatório de desligamento](si037-retained-handoff-shutdown.md)

O ensaio usou Pi instalado, perfil descartável e respostas
simuladas. A integração entre máquinas e os gates de versões
mistas seguem abertos. O marco dispensa migração. O rollback
coordenado restaura os commits e wheels anteriores depois de
resolver os recibos ainda em curso.
