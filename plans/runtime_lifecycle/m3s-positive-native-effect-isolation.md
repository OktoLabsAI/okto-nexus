# M3s — efeito nativo possível com sessão irmã saudável

No Windows, uma abertura local iniciou um processo real no Job identificado pelo Core e perdeu a resposta imediatamente após o spawn. O receipt do Core permaneceu `OUTCOME_UNKNOWN`, com `possible_effect=true` e `retry_safe=false`. A contenção registrou `CONTAINER_STOPPED`, observou o processo encerrado e só então liberou o slot físico. O Server devolveu erro com `possible_effect=true` ao chamador. Uma sessão irmã do mesmo agente continuou atendendo e uma nova abertura foi aceita, sem replay da operação original.

O fixture inicial criou o filho sem o `container_id` do launch e, corretamente, não representava o processo gerenciado: o filho continuou vivo mesmo com stop proof do Job vazio. O teste final usa o mesmo `container_id` que os adapters reais passam a `spawn_owned_process`, e encerra explicitamente qualquer filho residual no `finally` se falhar.

Validação final na versão Nexus 0.3.1 instalada (`a5212fe7724c07350a09d96dbd9044aa33444a5d4abfb13b5a3c58d7241264ce`, `pytest -o pythonpath=`): teste de sessão irmã e processo gerenciado **1 passed**; crashes descartáveis após spawn e após birth **2 passed**; recuperação de histórico `OUTCOME_UNKNOWN` com birth positivo **1 passed**. O teste de sessão irmã também passou no checkout. Ruff e `git diff --check` passaram. Não houve mudança de produção neste checkpoint.

Isto qualifica a fronteira embedded local no Windows. Connector em processo separado, Linux/macOS, rollout global e os demais critérios M2/M3 continuam nos itens próprios do ledger. Nenhuma validação adicional pela UI foi feita neste checkpoint técnico; os fluxos reais UI-A já estão em `ui-a-installed-restart-evidence.md`.
