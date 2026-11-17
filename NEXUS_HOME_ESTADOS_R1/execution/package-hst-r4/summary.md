# R4 instalado — pacote e smoke finais

Build, bootstrap Core sem Connector/Torch, serve-lite sem Connector/Torch, instalação posterior do Connector exato, smoke de instalação, Twine dos quatro artefatos, pip-check e auditoria de origens/bytes/entrypoints passaram no novo prefixo `nexus-hst-r1-package-mwu_9e4g/venv`.

Wheel Nexus 0.3.7: `9204183fcb00628b311f417d9cc601bbc6060f2c1347d200cf433cb8e32773a8`. Candidato: `92529cf4d4d3660ac98e1c415fb60151aefaa9a7`. Os 1.031 payloads correspondem aos wheels e à instalação; todos os bytes Nexus também correspondem à fonte isolada/checkout/sdist. Os 1.821 pins de fonte/testes não tiveram drift no corte. Os wheels Core/Connector não foram reconstruídos nem houve reinstalação de prefixos anteriores. O sdist não é apresentado como distribuição integral de docs/tests/plans.

O live HTTP/MCP real passou uma vez nesse Python instalado, com SDK, duas identidades locais sintéticas, 54 ferramentas expostas, eventos/mensagem/handoff/artefato/shared.md. Provider calls: zero. Stop canônico retornou 0, Server saiu fisicamente com código 0 e os sete processos observados já não existiam ao curar. Nenhum timeout, sinal ou force. Logs brutos ficaram no Temp próprio; o repositório contém metadados/hashes e relatórios sanitizados.

## Reuso limitado de evidência R3

`runtime-equivalence-vs-r3.json` prova igualdade byte a byte de 729 arquivos Nexus fora de `http/static`, 168 Core e 127 Connector: 1.024 arquivos de runtime. Python 3.13.1, versões de dependências instaladas, pyproject e uv.lock são iguais. Não há alegação de igualdade byte a byte de todos os arquivos de dependências de terceiros.

Os **746 PASS / 8 SKIP** foram executados no pacote **R3**, não no R4. São reutilizáveis apenas para o runtime idêntico e conservam seus limites de fixtures/SQLite/HTTP/CLI sintéticos. Não houve pytest R4 nem repetição dos cenários POSIX/PTY ignorados. Assets mudaram: bundle JS e index HTML, com CSS/logos iguais. Validação real do browser R4 e evidência Node/build do Root são camadas separadas, não inferidas pela equivalência do backend.
