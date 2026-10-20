# M3r — interrupção durante a autorização local

Uma falha após `EmbeddedRuntimeHost.acquire`, mas antes de `EmbeddedExecutor.authorize_r4` retornar, deixava `session.executor` vazio. O Nexus escalava isso para recuperação do agente inteiro e encerrava uma sessão irmã saudável. O teste reproduziu o comportamento anterior.

Agora qualquer abertura sem executor retornado entra na contenção da sua própria sessão. A recusa durável só é publicada após o produtor terminar e o Core confirmar ausência de claim e nascimento nativo. Se essa prova faltar, a sessão continua contida; não há liberação baseada somente na exceção. O caso reproduzido terminou em `PREPARATION_FAILED`, manteve a sessão irmã ativa, aceitou outro turno e abriu uma nova sessão.

Validação: **41** testes relacionados passaram no checkout; o wheel Nexus 0.3.1 SHA-256 `a5212fe7724c07350a09d96dbd9044aa33444a5d4abfb13b5a3c58d7241264ce` passou **6** casos críticos com `pytest -o pythonpath=` e importação de `site-packages`. Os **20** testes instalados do contrato `test_r4_startup_refusal.py` no Core passaram, incluindo a precedência de intenção nativa sobre recusa tardia.

Este checkpoint cobre a interrupção durante autorização quando o Core comprova ausência de efeito. A convergência de uma abertura com claim/nascimento nativo e efeito incerto permanece como critério separado de L20. Não houve rollout global nem novo teste de UI neste checkpoint técnico; UI-A real já foi documentado em `ui-a-installed-restart-evidence.md`.
