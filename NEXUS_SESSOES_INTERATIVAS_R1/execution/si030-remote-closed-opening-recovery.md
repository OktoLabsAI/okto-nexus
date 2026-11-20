# SI-030 · Recuperação de abertura encerrada após reconexão R4

O Nexus recuperou o recibo original da abertura remota com estado SUBMITTED. A reconciliação da geração seguinte encerrou a sessão e a concessão. No CLI anterior, a consulta do mesmo recibo continuava retornando abertura pendente porque a sessão já havia deixado de aceitar controle.

O CLI agora distingue uma abertura confirmada cuja sessão terminou de um efeito ainda incerto. Confere a operação, o hash, o escopo e a geração da sessão. Com a sessão e a concessão encerradas, resolve o checkpoint e mostra os IDs originais no diagnóstico OPENING_CLOSED. Efeito incerto, geração divergente e sessão ainda recuperável conservam o checkpoint pendente.

Comparei os wheels anterior e atual em cópias da base do ensaio remoto. O anterior conservou o checkpoint pendente. O atual resolveu o mesmo checkpoint usando as duas consultas canônicas. Ambas as execuções preservaram a base de origem. Os testes também exercitam a recusa de concluir o checkpoint com resultado incerto ou prova de outra geração.

No novo ensaio, o CLI instalado solicitou uma abertura vazia pelo Connector. O Pi 0.87.1 real iniciou em um perfil temporário no Windows. Depois que o Core gravou o recibo e antes da publicação no Nexus, a fixture interrompeu apenas o WebSocket de controle do ensaio. Na geração seguinte, o Connector publicou o recibo original. O processo anterior saiu. Repetir o comando exibiu a sessão encerrada, resolveu o checkpoint e preservou uma única operação de abertura. O ensaio fez zero turnos e zero anexações.

Passaram 45 testes do CLI no código-fonte, 123 regressões com os wheels instalados, os dois testes da cópia da base e o ensaio nativo. O lock offline e a validação estrita do wheel passaram. O Ruff reproduziu um aviso de ordenação de imports da referência. As primeiras rodadas corrigiram a identificação do recibo na fixture e a hipótese de que toda queda preserva uma janela de retomada rápida.

A reversão usa o wheel anterior. Os checkpoints já resolvidos conservam seus identificadores e o formato atual. A alteração dispensa migração de banco.

O ensaio cobre a substituição completa da geração do Connector com a sessão encerrada em loopback. A campanha e a qualificação entre máquinas continuam pendentes no ledger. [Resultados e hashes](si030-remote-closed-opening-recovery.json)
