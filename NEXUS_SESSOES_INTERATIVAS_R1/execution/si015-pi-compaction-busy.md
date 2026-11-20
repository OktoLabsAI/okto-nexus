# Recusa de compactação durante um turno ativo do Pi

Na Home, o catálogo do Pi 0.87.1 agora informa que a compactação interromperia o turno em andamento. A ação fica indisponível enquanto o servidor confirma atividade na sessão e no stream consultados. O motivo usa o comportamento observado no Pi instalado, cuja compactação nativa chama `abort()` antes de resumir o contexto.

O ensaio com o wheel instalado abriu uma sessão do Pi e reteve a resposta de um único turno em um provedor determinístico local. No Edge, selecionar `/compact` exibiu o motivo, manteve o rascunho após Enter e não enviou POST de sessão. A API recusou uma tentativa com a revisão atual com HTTP 409. Após concluir o turno, a Home mostrou o resultado na mesma sessão e manteve o rascunho ao atualizar o catálogo. Em repouso, a compactação continua sem implementação qualificada. A API respondeu 422 para a revisão atual e 409 para a revisão anterior. Um corpo com argumento extra recebeu 422.

O Pi recebeu somente o prompt de teste antes do fechamento canônico. A auditoria de leitura do SQLite encontrou uma abertura, um turno, um resultado na sessão original e um fechamento. Nenhuma entrada de fila, controle ou anexo foi criado. Os processos temporários e o listener de loopback foram encerrados. O primeiro ensaio aguardava apenas o recibo `SUBMITTED`. A fixture foi corrigida para aceitar o recibo `ACCEPTED` emitido pelo Pi durante o turno retido. [Dados e hashes](si015-pi-compaction-busy.json)

Passaram 22 testes de contrato no checkout, 23 testes no wheel instalado com a regressão de reorientação do Codex e a integração Pi/Edge. Twine estrito, Ruff e a comparação dos 810 arquivos do wheel passaram. A evidência verifica a recusa de SI-T-D03 no Pi revisado, com simulação apenas do provedor de resposta.

A mudança é no catálogo e na recusa HTTP. O contrato do Connector, o Core e a base de dados mantêm suas versões. O rollback consiste em reverter o commit e reconstruir o wheel do Nexus com os mesmos pins.
