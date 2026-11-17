# R5 instalado — qualificação Home

Candidato `8df456d1079313cc38e3cfe674ae4cc2b04fb64b`, Nexus 0.3.7, wheel `db73f1a3fbdae390ea3b36f93076391de64538ce599a3fc178ef37678628e21d`. Novo prefixo próprio: `nexus-hst-r1-package-n5k24oky/venv`. Nenhum prefixo anterior ou instalação pessoal foi reinstalado.

Build/install/bootstrap Core sem Connector/Torch, serve-lite sem Connector/Torch antes da adição do Connector exato, ci-smoke, Twine dos quatro artefatos, pip-check e auditoria de origens/bytes/entrypoints passaram. Os 1.031 payloads correspondem aos wheels e à instalação; os bytes Nexus também correspondem à fonte isolada/checkout/sdist. Os 1.824 pins de fonte/testes permaneceram idênticos no corte. Core/Connector e schemas não mudaram. O sdist não é apresentado como distribuição integral de docs/tests/plans.

O live HTTP/MCP instalado passou uma vez: SDK real, duas identidades sintéticas locais, 54 ferramentas expostas, eventos/mensagem/handoff/artefato/shared.md, zero provider. Stop canônico 0 e saída física 0, sem timeout ou force; sete processos observados ausentes ao curar. Logs brutos ficaram no Temp próprio.

## Regressão instalada efetivamente executada no R5

**251 PASS, 0 SKIP, 0 FAIL, 0 ERROR, 0 NOT_RUN**, entre 251 nodes de 22 arquivos, expandindo os nove escopos de `installed-selection.json`. Shard único, sem fail-fast, prazo externo 900 s. Pytest stdout: 438,29 s; JUnit: 438,186 s. O browser funcional e a suíte source do Root rodaram em paralelo: não há alegação de benchmark.

O pytest usou o Python instalado `-I -B`, fora do checkout, com stdin PIPE fechado, HOME/TMP próprios, testes/helpers copiados sem `src`, helper externo comparado ao Git blob do candidato e à cópia. Todas as origens Nexus/Core/Connector carregadas foram verificadas no prefixo no início e no fim. Fonte/payload/helpers e cópias dos testes tiveram drift zero. Nenhum sinal, timeout, force ou processo próprio conhecido remanescente. Polling não é apresentado como inventário completo de filhos curtos.

`installed-qualification.json`, `installed-shard-0/phase-inventory.json` e JUnit sanitizado preservam node IDs, fases e resultados literais. Logs/diagnósticos brutos ficam em `nexus-hst-installed-gweb2v6c`, referidos por hashes. Asserções e argv dos testes não foram reescritos, não houve rerun automático nem promoção de resultados coletados a PASS.

O delta R5 altera três arquivos Home. A execução histórica R3 de 746 PASS/8 SKIP continua identificada como R3; não é uma suíte completa executada no R5. Este corte qualifica os escopos Home/SQLite/HTTP/fixtures selecionados, incluindo prova SQL sintética separada da integração canônica Core. Não qualifica modelos reais, AT, pessoa, cenários POSIX/PTY ou todos os 116 cenários completos por contagem.
