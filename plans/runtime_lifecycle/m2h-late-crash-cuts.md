# M2h — cortes tardios de handshake, receipt e ACK

Data: 2026-10-20 UTC. Testes direcionados com Nexus 0.3.1, Core 0.0.12 e Connector 0.0.10 instalados. O interpretador `-I` importou as wheels do ambiente descartável `build/m2g-nexus-verify`; nenhum Nexus global foi iniciado.

| Fronteira | Prova instalada |
| --- | --- |
| Após handshake do processo nativo, antes da submissão | `tests/test_owned_kernel_crash.py`, variante `after_spawn`: owner do Core morre após `READY`; o filho é parado, o receipt mantém efeito possível e o replay não reexecuta. |
| Após ACK da escrita nativa | Mesmo teste, variante `after_write`: marcador de efeito aparece uma vez, filho é parado e a operação não reexecuta. |
| Após receipt durável do Core | Variante `after_receipt`: receipt `SUBMITTED` persiste com efeito possível e a operação não reexecuta. As três variantes passaram em 3,76 s. |
| Após receipt do turno ou projeção do Server | `test_canonical_process_result_crash.py`, variantes `after_turn_receipt` e `after_projection_commit`: queda real do processo Nexus, processo nativo observado parado, recuperação sem novo `turn/start`, resultados/entrega conforme a prova durável. 2 passaram em 117,46 s. |
| Após commit do evento, antes do ACK ao Core | `test_embedded_dispatch.py::test_local_events_commit_and_reapply_lost_core_ack`: o novo host reaplica o ACK sem duplicar evento. 1 passou em 11,94 s. Este corte usa falha controlada de ACK e troca de owner, não morte do processo no instante do ACK. |
| Thread atrasada, cancelamento e revogação | Os seis casos de `tests/test_process_launch_control.py` passaram em 0,91 s, incluindo worker tardio impedido de iniciar, produtor cancelado mantendo slot e autoridade revogada antes/durante claim. |

M5y já qualificou a perda de resposta de receipt em um daemon Connector Windows separado: um único efeito/dispatch, receipt terminal e reconexão automática. UI-A já exercitou Pi, Claude e Codex reais após restart abrupto na interface. A combinação cobre as fronteiras locais de M2 sem afrouxar o fence de capacidade. Ainda não é uma afirmação de sucesso da matriz Nexus multiplataforma: a execução completa 39352913186 está em andamento no commit de código `c7006e2`; o rollout global controlado permanece pendente.
