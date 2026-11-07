# SVC-T22 — filho físico pertencente e restart pendente

Fonte final: **1/1 PASS**, 52,54 s, exit 0. O único caso é `tests/execution_r4/test_service_surviving_child.py::test_restart_pending_keeps_real_connector_child_claim_and_slot`. O root é responsável pela qualificação instalada posterior; este pacote não antecipa seu resultado.

O Server é um processo real separado. O filho Python pertence ao Core hospedado no Connector, com `process_launch.produce`, container Windows normal, birth journal, claim e reserva reais. Seu comando LF grava exatamente uma linha física. O CLI `restart --timeout .2` retorna `stopping`/`UNCONFIRMED`; a inspeção local canônica confirma `DRAINING_PENDING`, mesma geração/PID e ownership, enquanto o filho permanece vivo e claim/slot/birth permanecem idênticos. O teste não chama isso restart concluído.

Depois de terminal e close explícitos, o filho aceita STOP e sai com código **0**. O watchdog usa 88 e, portanto, não pode satisfazer o oráculo. A reserva somente então aparece liberada; o Server termina com `DRAINED`, exit 0, e nenhuma substituição automática. `owned-child-proof.json` contém apenas os metadados dessa associação e os resultados. `server-owner-proofs.json` é o snapshot inicial do helper; o estado final está na prova do filho e em `cleanup.json`.

`cleanup.json` compara o nascimento exato dos processos. Os PIDs foram reutilizados depois do teste por outros nascimentos; isso não significa filho sobrevivente e nenhum processo alheio foi sinalizado. O runner de fonte também terminou com exit 0.

O histórico está integralmente preservado em seis XMLs e snapshots do novo teste: uma comparação errada do PID do launcher Windows, uma falha de coleta por `psutil` ausente, um oráculo estrito demais para resposta de timeout e duas correções de rota/contexto do observador. O helper foi corrigido pelo seu responsável com stdlib e prova de HANDLE/nascimento/ancestralidade. Nenhuma dessas tentativas estabeleceu defeito de produto. Há **uma identidade final qualificada**, não seis testes novos.

O manifesto é uma allowlist: fontes, snapshots, XMLs fechados byte-exatos, comandos/resultados sanitizados, script, patch, Ruff e metadados físicos. Não contém DB/WAL/SHM, logs brutos, homes, arquivos de vault ou material de credenciais. Produto, ledger e relatórios anteriores não foram alterados por este trabalho.

Limites: Windows; Python LF sintético, sem provider; nenhuma instalação de serviço/tarefa nativa ou uso de serviço pessoal. O filho não pertence ao Server e não foi mantido vivo artificialmente após morte do dono. Job containment e política de ownership permanecem intactos.
