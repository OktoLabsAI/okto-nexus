Revisão16 — preparação offline finita

Fonte Nexusb90e6824, Core7810/d881 e Connector645d/f986. Pacote próprio,1002payloads;
probe canônico60 passou em0,770s.50 testes de autoridade nativa instalada,6 testes
da composição e14 deltas do controlador ficam separados, sem somar sobreposições.
O builder recompôs inicialmente Connector;131payloads instalados (sem RECORD)
foram comparados ao ZIPf986 anterior e revalidados, sem reinstalação ou mutação
de payload. O ZIP realmente instalado e direct_url continuam documentados.

Carry341276/13, quatro novos IDs, máximo17, preventiva500k/tolerância700k;
158724 até preventiva e358724 até tolerância, sem garantia de conclusão.
Oito registros máximos (4 históricos+4novos): snapshot1/init2/margem1,
poll19/fresh20/cadence24/alvo200ms; deadline600 e readiness5 permanecem.
São limites operacionais, não novos critérios R3.

Local útil14 em nova sessão, continuação15 somente após sucesso/settlement
canônico na mesma sessão. Remoto16/17 permanece bloqueado. A antiga continuação14
da revisão15 não é elegível; decisão nativa antiga e interrupt não são reexecutados.
Request13 CANCELLED, recibo interrupt SUBMITTED e falhas históricas preservados.

Roteiro workflow.json: prepare, upgrade-plan, seleção técnica exata, upgrade-apply,
install/start único45s, observação passiva180s quando permitida, watcher de3handles,
review de grant/apply somente expirado e selecionado, útil14/continuação15 condicional,
stop normal, cleanup, uninstall, finalpresence, closure direto. Native decision:
private/native-decision.json, somente decisão real revisada. Contenção normal
turn.interrupt exata se stop45 continuar draining, sem força/novo turno/replay.
Cancelamento/cleanup não implicam conclusão do recibo interrupt ou billing final.

Nenhum serviço, modelo, grant ou migração foi executado nesta preparação.
