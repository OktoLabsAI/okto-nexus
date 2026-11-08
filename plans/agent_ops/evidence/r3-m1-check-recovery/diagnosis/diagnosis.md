# M1 v8: verificação de instalação commitada, resposta HTTP indisponível

Diagnóstico somente leitura de 2026-11-07. Nenhum HTTP, replay, import de produto, probe, provedor, processo ou serviço foi executado. SQLite aberto com `mode=ro`, uma transação de leitura; SHA do DB antes/depois idêntico. Os seis arquivos relevantes do produto instalado são byte a byte iguais às fontes examinadas. Projeção e hashes em `diagnosis.json`; nenhum perfil completo, payload, segredo ou log privado foi copiado.

**Requisição identificada:** `POST /api/v1/runtime-management/runtime/executors/exe_49873f8c3d4f05bc6f4229e6fab9576a/installations:check`. O perfil `m1v8-local` permaneceu `check_submitted`, `version_check_required=true`, sem `version_check_confirmed`, teste ou resultado. O request é `connect_6e132838911b4805b20dcf0d992e5fce`. Em `application/terminal_connection.py:226–244`, esse estado é salvo antes do POST; `setup:test` só aparece depois, em 246–249. O erro `OUTCOME_UNKNOWN` com texto “The Server response is unavailable” identifica a exceção de transporte anterior à leitura do corpo, em `adapters/outbound/terminal_http.py:37–43`, cujo timeout padrão é 30s (linha 18).

Evidência cronológica:

* Checkpoint `check_submitted`: mtime **23:50:36.701411Z**.
* Observação canônica da instalação: **23:50:56.166442Z**, mesmo executor/candidato, Core 0.0.14, Windows, versão **0.157.0**, ator operator.
* Snapshot de inventário 14: **23:51:02.115Z**, candidato exato `selected/READY_FOR_RUNTIME/0.157.0`.
* Saída CLI `OUTCOME_UNKNOWN`: mtime **23:51:06.776121Z**, aproximadamente **30.075s** após o checkpoint. Stderr vazio.
* Snapshot 15: **23:51:10.319Z**, mesma revisão e estado pronto.
* O resultado público inclui o período de contenção, terminando **23:51:16.356893Z**; seus 42.5s não são a duração de um único POST. Stop retornou 0; lifecycle público reportou DRAINED. Root informou uninstall concluído posteriormente.

Os mtimes são evidência auxiliar, não tracing interno de requisições. Não foi retida a classe exata da exceção de socket nem o instante de término de `refresh`; portanto timeout de 30s é a causa **fortemente sustentada**, não uma medição instrumentada desse await.

**Mecanismo provável:** `execution_local_observations.py:150–184` faz probe, redescoberta/revalidação e commit da observação. Depois `bootstrap/embedded_inventory.py:235–249` ainda aguarda `refresh(adapter)` antes de responder. Esse refresh espera uma nova tentativa e a publicação (`122–160`); Core `inventory_observer.py:138–170` exige `_started+1`, mesmo quando uma observação já está em andamento. Assim, uma observação válida já commitada/publicada não garante que esse POST retorne dentro dos 30s do cliente. Não há prova de rejeição de autoridade ou incompatibilidade do executável: a observação e ambos os snapshots confirmam a versão selecionada.

**Limite de efeito:** `execution_operations`, `execution_receipts`, `execution_sessions` e `connection_setup_commits` têm zero linhas. Não existe journal do teste de conexão e o monitor não viu runtime.start. Isso localiza a interrupção antes de `setup:test`, sem afirmar billing final nem autorizar apagar reservas/faults. O controller retém 45.843 tokens observados de carry-in e a nova reserva não resolvida; este diagnóstico não redefine sua contabilidade.

## Correção mínima proposta, ainda não aplicada

No cliente, tratar **somente** `OUTCOME_UNKNOWN` daquele POST de verificação como resposta incerta recuperável e usar o caminho GET já existente para o **mesmo** candidato/adapter/executor/Server. Nunca repetir POST, `--version`, criar outro request ou enfraquecer hashes/seleção. Se a leitura canônica confirmar `READY_FOR_RUNTIME` da seleção exata e autoridade corrente, atualizar a revisão de inventário como já faz o fluxo. Enquanto faltar confirmação, permanecer `check_submitted`; nenhum `setup:test` ou Finish. Usar prazo monotônico comum a essa verificação e suas leituras, em vez de timeout novo por repetição. Falha de leitura não deve transformar a incerteza do POST em ausência de efeito.

O state `check_submitted` já permite recuperação GET-only numa retomada (`terminal_connection.py:228` pula o POST quando não é `approved`). O ajuste proposto evita abandonar desnecessariamente a mesma invocação após uma resposta perdida. Adiar a publicação no Server e responder logo após commit pode reduzir latência, mas não substitui a recuperação correta no cliente e não é necessário ao patch mínimo desta falha.

Testes focais sem provedor: (1) POST commitado seguido de OUTCOME_UNKNOWN, GET exato pronto: uma única verificação e continuação; (2) GET não pronto/deadline: checkpoint conservado e zero setup:test; (3) Server/seleção/autoridade divergente ou GET indisponível: não avançar; (4) retomada de check_submitted: zero POST de verificação; (5) erro definitivo do POST continua recusado. Capturar comandos/contadores e relógio falso, sem sleeps longos.

Nenhum patch, replay, restart ou nova admissão foi realizado por esta revisão. Recuperar ou continuar a campanha exige decisão separada da raiz sobre o checkpoint/controller e a autorização aplicável; não apagar o fault existente como consequência deste parecer.
