# M3q — falha de persistência da recusa local

Uma falha injetada em `persist_r4_startup_refusal` manteve a sessão que falhou em `OPEN_PENDING`, sem receipt no Server nem liberação prematura. Uma sessão irmã permaneceu ativa e concluiu outro turno. Após restaurar a gravação, a recuperação automática publicou `PREPARATION_FAILED` e aposentou a sessão afetada.

O teste focado passou no checkout e no wheel Nexus 0.3.1 instalado com `pytest -o pythonpath=` (1/1 em cada). Nenhuma mudança de produção foi necessária após M3p. Falhas com efeito nativo incerto continuam sob contenção conservadora e ainda exigem a qualificação separada prevista no L20.
