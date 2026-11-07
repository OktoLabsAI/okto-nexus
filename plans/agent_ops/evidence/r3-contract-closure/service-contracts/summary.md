# SVC-T26 / SVC-T28 — proposta literal finita

Recomendo **VERIFIED para ambos**, somente nos escopos descritos na matriz. Nenhum status foi editado.

- **SVC-T26:** os dois hosts têm retomada do mesmo plano em cada fronteira de persistência, resposta nativa perdida, recusa de downgrade e upgrades reais de ambientes instalados preservando DB/journal. O relatório instalado retém 200 PASS. Recuperação é documentada como repetir o mesmo arquivo/revisão; não exige executar downgrade histórico nem atualizar uma tarefa Windows real.
- **SVC-T28:** Connector tem dois PASS reais sob Job Object Windows restritivo (detached recusado; foreground funciona). Nexus possui quatro PASS instalados próprios: processo foreground real iniciado, observado, sinalizado e unido por um pai externo de teste, com HTTP/owner mantidos até shutdown. O wrapper supervisionado com Mock é evidência contratual separada, não substituto desse processo real.

Para T28, “supervisor externo” significa precisamente esse pai que controla a vida do processo foreground. Nenhum produto de supervisão específico é qualificado. Não há requisito adicional de POSIX/container quando essa alternativa foi observada. Caso o ledger queira uma campanha de Docker/Task Scheduler, mantenha-a como subscope distinto e não como pendência literal genérica destes dois cenários.

Limites: Windows/local; nenhum registro de tarefa, container, login/reboot, provedor pessoal ou nova execução. Interrupções do upgrade e efeitos de Task Scheduler são injetados. Os dois upgrades instalados e os processos foreground são reais. Os XMLs históricos não são rotulados como execução do wheel atual; Nexus foreground usa a qualificação instalada SVC-07 já retida.

matrix.json contém literal, implementação, assertions, nodes PASS, SHA e limites separados por componente. input-manifest.json e artifact-manifest.json delimitam o pacote público.
