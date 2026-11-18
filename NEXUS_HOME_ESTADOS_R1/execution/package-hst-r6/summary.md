# R6 instalado — pacote e equivalência

Candidato `90b94ca9673c087554b7dc4a226490ef5417bd32`, wheel Nexus 0.3.7 `8ab8f08e8f5e06b428ed4642045ad5e4069d93891a869d4dc61fcaa5bb3ffa19`. Novo prefixo próprio: `nexus-hst-r1-package-vmoup3wt/venv`. Nenhum prefixo anterior ou instalação pessoal foi reinstalado.

Build/install, bootstrap Core sem Connector/Torch, serve-lite sem Connector/Torch antes do Connector exato, ci-smoke, Twine dos quatro artefatos, pip-check e auditoria de origens/bytes/entrypoints passaram. Os 1.031 payloads correspondem aos wheels e à instalação, e os bytes Nexus também correspondem à fonte isolada/checkout/sdist. Os 1.824 pins permaneceram sem drift. O sdist não é apresentado como distribuição integral de docs/tests/plans.

O live HTTP/MCP instalado passou uma vez, com SDK real, duas identidades sintéticas locais, 54 ferramentas expostas, mensagem/eventos/handoff/artefato/shared.md e zero provider. Stop canônico 0 e saída física 0, sete processos observados ausentes, sem timeout, sinal ou force. Logs brutos ficam no Temp próprio; o repositório contém metadados e hashes sanitizados. Polling não é apresentado como inventário completo de filhos curtos.

## Reuso limitado da execução R5

`runtime-equivalence-vs-r5.json` compara bytes exatos de 729 arquivos Nexus fora de `http/static`, 168 Core e 127 Connector: 1.024 arquivos de runtime. Python, versões das dependências instaladas, pyproject e uv.lock também coincidem. A comparação das dependências de terceiros é de versões, não de todos os seus bytes.

Os **251 PASS / 0 SKIP / 0 FAIL / 0 NOT_RUN** foram executados no pacote R5 e permanecem identificados como tal. O R6 **não executou pytest**. O reuso abrange somente os escopos idênticos de backend Python/SQLite/ASGI Home e mantém todos os limites de fixtures e plataforma. Não qualifica modelos reais, pessoa, AT ou todos os cenários do plano por contagem.

Somente os estáticos index HTML e bundle JS mudaram em relação ao R5; CSS e logos permaneceram iguais. Não há alegação de equivalência byte a byte do frontend da worktree nem reuso da validação de browser anterior. O build Original e a validação real de browser R6 pertencem a evidências separadas do Root/owner do browser.
