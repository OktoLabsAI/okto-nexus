# M8 — checkpoint de backup e restauração offline

Data: 2026-10-19. Escopo: home **descartável** `build/runtime-uic-ui/home`,
usada no gate real UI-C. A instância global do Nexus permaneceu parada.
As portas 8202 e 8204 estavam livres antes do procedimento; nenhum owner ou
writer dessa home estava em execução. A home foi preservada sem alterações.

O procedimento `tools/offline_runtime_backup.py`, importando Nexus instalado
no ambiente isolado `build/m3k-owner-env`, produziu
`build/runtime-uic-ui/m8-backup` com o reconhecimento explícito de owners e
writers parados. Ele validou o snapshot ao término. A restauração para o novo
diretório `build/runtime-uic-ui/m8-restored` e a validação independente dessa
cópia também retornaram `PASS`, sem iniciar processos nativos.

O manifesto v2 contém 114 arquivos e 44.534.770 bytes. O banco validado está
na migração 152 e contém sete agentes, 338 mensagens, 338 entregas, quatro
handoffs, 102 resultados de runtime e um artefato. A comparação de hashes do
manifesto e as verificações de integridade SQLite/journal passaram na cópia
restaurada. Os diretórios de backup e restauração permanecem ignorados no
workspace e não contêm dados para commit.

Este checkpoint comprova cópia, restauração e integridade com a home parada.
Ainda falta inicializar a cópia restaurada com o artefato final, demonstrar
recusa segura de downgrade incompatível, concluir a matriz instalada e o
rollout controlado antes de aceitar M8.
