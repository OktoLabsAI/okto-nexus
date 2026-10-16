# M3e — Falha de lease isolada no Connector

Sessões remotas já abertas agora são cercadas individualmente quando o Core
recusa a renovação por expiração/revalidação. O fence precede a liberação do
gate: comandos em espera recebem falha durável sem chegar ao harness. A tarefa
de contenção continua retida até comprovar a liberação, enquanto sessões irmãs
continuam operando. A recuperação publica o resultado original sem replay.

Em 2026-10-16, **138 testes instalados passaram**: 43 Core, 71 Connector e
24 Nexus. Sem falhas, erros ou skips. O Nexus M3d foi qualificado com os novos
Core/Connector, preservando a recusa inicial estrita e a liberação negociada
de sessões. Os manifests confirmam bytes instalados e inputs estáveis nos
consumidores; hashes e resultados estão em `m3e-results.json`. As falhas iniciais
de invocação/fixtures estão documentadas nos relatórios dos outros repositórios.

A instalação global permanece no M3c já testado pelo Meta-harness. Não foi
reiniciada por este checkpoint intermediário. A abertura inicial sem fato de
abertura ainda usa a reconciliação conservadora do host; esse limite e o
isolamento de inventário seguem pendentes. M3 e M5 não estão concluídos.
