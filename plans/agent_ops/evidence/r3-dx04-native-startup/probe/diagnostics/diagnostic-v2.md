# Correção do harness após a primeira tentativa

`run-001` permanece intacto. O runner SHA `9bf238a2f0088ddf65259da61bfd27004fb0afd35cfed823e556215aec0c91ea` está preservado em `failure-001-snapshot/dx04_probe.py`.

A tentativa terminou UNCONFIRMED/TypeError. O Server fechou seu listener e o registro próprio do cofre foi removido. O checkpoint de lançamento foi conferido diretamente: `state=review`, sem pid_hint. A reprodução benigna localizou a exceção em `win32job.CreateJobObject(None, None)`, antes de CreateProcess; não se deduziu a ausência do nativo apenas pela falta de logs.

O binding pywin32 instalado exige uma string no segundo argumento. O único delta no runner é substituir `None` por `'dx04-probe-' + uuid.uuid4().hex`. O Job continua exclusivo por execução e é possuído pelo handle retornado.

A reprodução inicial usou somente o caminho benigno de CLI `--help`; não chegou a criar o worker. Traceback original: `C:/Users/jpamb/AppData/Local/Temp/dx04-console-signature-dff9k6kq/result.json`.

A rechecagem usou o mesmo caminho benigno `--help`, sem Server, cofre ou Codex. Resultado em `C:/Users/jpamb/AppData/Local/Temp/dx04-console-signature-v2-32srqykd/result.json`:

- Job associado e membership confirmado antes de ResumeThread.
- Owner PID 21996 e filho Python PID 42588: stdin/stdout/stderr TTY=true.
- CLI exit0, watcher joined=true, leader exit0.
- ActiveProcesses=0; sem terminação forçada; sem erro de fechamento de handles.

Esta rechecagem qualifica somente a criação/ownership/TTY/cleanup do harness com execução benigna. Não comprova login, trust ou MCP do cliente nativo. Nenhuma nova tentativa Codex foi executada; o restante do contrato do runner permaneceu igual.
