# SI-024 e SI-027 — Recusa de um visualizador Codex incompatível

O CLI orienta a usar `--viewer-executable` com o Codex 0.170.0 revisado. A instrução passou para o início da mensagem depois que a primeira captura no console cortou o nome da opção. O guia do terminal mostra como tentar novamente na mesma sessão.

Com o Nexus instalado e o app-server Codex 0.157.0 real em perfis descartáveis no Windows, uma resposta de modelo em loopback manteve o turno em curso. O CLI recebeu esse mesmo executável 0.157.0 como visualizador explícito. Os pedidos de leitura e de escrita retornaram código de saída 3, com diagnóstico `VIEWER_BUILD_UNAVAILABLE`. O ensaio verificou zero lançamentos de visualizador, zero registros de anexação e zero mudanças na fila, nas operações e no alvo exato do turno durante as recusas.

O visualizador revisado 0.170.0 abriu a mesma thread enquanto o turno estava ativo. Quando o simulador liberou a resposta, o visualizador mostrou o resultado e saiu com Ctrl+]. Os modos do console foram restaurados, o recibo registrou `DETACHED` e o mesmo app-server encerrou apenas com o fechamento canônico. O ensaio teve um início de turno, uma resposta em loopback e zero chamadas a provedores. [Dados e hashes](si027-codex-viewer-refusal.json)

Passaram 30 testes do CLI no código-fonte e 32 testes com o wheel instalado, incluindo a recuperação da conexão após falha do visualizador. Ruff, lock e validação estrita dos artefatos passaram. O ensaio cobre a apresentação local no Windows com operador descartável e seleção do servidor de teste injetada. A campanha exigida no nível de SI-T-G12 segue aberta. O marco dispensa migração e pode ser revertido pelo commit do Nexus.
