# M8 — checkpoint de backup e restauração offline

Data: 2026-10-19. Escopo: home **descartável** `build/runtime-uic-ui/home`,
usada no gate real UI-C. A instância global do Nexus permaneceu parada.
As portas 8202 e 8204 estavam livres antes do procedimento; nenhum owner ou
writer dessa home estava em execução. A home foi preservada sem alterações.

O primeiro backup e a restauração passaram, mas reabrir o banco da cópia fez
`validate` falhar: conexões SQLite ainda abertas tinham incluído `nexus.db-wal`
e `nexus.db-shm` transitórios no manifesto. A leitura posterior removeu esses
arquivos. Os registros do banco não mudaram; o problema era a estabilidade do
manifesto. O procedimento agora fecha explicitamente cada conexão de cópia e
lê o banco de destino em modo imutável. O teste de regressão reabre o banco e
valida novamente tanto o snapshot quanto a cópia restaurada.

Com Nexus instalado no ambiente isolado `build/m3k-owner-env`, o procedimento
corrigido produziu `build/runtime-uic-ui/m8-backup-fixed` e restaurou em
`build/runtime-uic-ui/m8-restored-fixed`. Backup, restauração e revalidação
após acesso SQLite retornaram `PASS`, sem iniciar processos nativos.

O manifesto v2 contém 112 arquivos duráveis e 44.502.002 bytes, sem `-wal` ou
`-shm`. O banco validado está
na migração 152 e contém sete agentes, 338 mensagens, 338 entregas, quatro
handoffs, 102 resultados de runtime e um artefato. A comparação de hashes do
manifesto e as verificações de integridade SQLite/journal passaram na cópia
restaurada. Um conjunto de migrações limitado à versão 151 recusou a cópia com
`MIGRATION_ERROR` (152 > 151), sem alterar o ledger; a validação do backup
continuou passando depois dessa recusa. O caso de regressão e dois testes
adjacentes passaram, 3/3, com os pacotes instalados no Windows. Os diretórios
de backup e restauração permanecem ignorados no workspace e não contêm dados
para commit.

O pacote Nexus instalado também iniciou a **cópia restaurada** em
`127.0.0.1:8204`, sem tocar na home original. O servidor anunciou startup
completo e a página raiz respondeu HTTP 200. Durante a execução, o banco
permaneceu na migração 152 com sete agentes, 338 mensagens e um artefato.
Após a parada da instância descartável, a porta 8204 ficou livre e não restou
processo com o caminho dessa cópia na linha de comando. O snapshot original
continuou validando `PASS`. Essa inicialização verifica leitura e bootstrap;
não é uma nova campanha de mensagens reais pela UI.

Este checkpoint comprova cópia, restauração, integridade, recusa de esquema
mais novo e inicialização da cópia com o pacote instalado. A matriz instalada,
o gate UI-C no artefato final e o rollout controlado ainda precisam terminar
antes de aceitar M8.
