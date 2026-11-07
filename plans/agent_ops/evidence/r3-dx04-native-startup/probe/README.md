# DX04: curadoria finita das duas tentativas

Status preservado: **UNCONFIRMED**. Não houve nova execução de CLI nativa, Server ou cofre nesta auditoria.

`runs/run-001/result.json` e `runs/run-002/result.json` são os bytes originais. A primeira falha foi o TypeError do harness antes de CreateProcess; seu checkpoint continua review. A segunda observou os rótulos fixos de login, mas nenhum initialize/tools/list aceito: a única observação MCP é o controle negativo401. O watcher registrou PermissionError, sem causa determinada. O Job próprio foi encerrado forçadamente125/active0; os relatórios preservam listener fechado e cofre próprio ausente. Esses fatos individuais não se tornam cleanup_confirmed=true agregado.

O diagnóstico benigno V2 confirma somente console/TTY/Job/cleanup com `--help`; não substitui a cadeia nativa. Os runners V1/V2, delta único, diagnóstico inicial, revisões independentes e preflights estão separados. `preflight/packages-before.json` é um registro resumido da verificação anterior (691/166/124 arquivos), sem inventar uma tabela de provas file-by-file ausente.

`audit/postmortem.json` compara todos os inputs registrados. No run001 o runner atual é V2; o hash original é comprovado pela cópia V1 preservada. As projeções de checkpoint contêm somente state/pid_hint. As leituras SQLite próprias retêm apenas contagens finais e presença da identidade/workspace sintéticos. Não há baseline canônico retido: não se alega preservação antes/depois, nem comparação de timestamps de autenticação.

A observação de login sem MCP vale para esta tentativa/versão/contexto. Não estabelece uma regra universal sobre ordem de startup, nem torna inferência um requisito normativo.

Copiar estritamente `artifact-manifest.json.files`. A pasta pública contém somente os payloads listados e o manifesto. Homes, DBs, configs, credenciais, logs de Server/nativo, screenshots brutos e arquivos pending não foram copiados. Nenhum DB ou segredo foi hasheado. A leitura de cofre não foi repetida; sua ausência é o fato reportado pelos runners originais.
