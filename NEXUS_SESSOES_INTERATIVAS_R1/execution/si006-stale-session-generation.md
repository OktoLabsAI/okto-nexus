# SI-T-A05 — Envio com geração antiga

O teste obteve uma revisão válida para a geração original da sessão.
A fixture avançou a geração na projeção SQLite e manteve a revisão
antiga no pedido, como faria um painel já aberto. Consultar a geração
antiga retornou HTTP 404. Consultar explicitamente a atual retornou
HTTP 200 com a geração atual e o mesmo escopo canônico.

O envio antigo retornou HTTP 409 com instrução para reabrir o
contexto. O Nexus não criou recibo, operação ou despacho e o peer
Codex simulado não recebeu texto. O teste restaurou apenas o dado
da fixture e encerrou a sessão pelo controle canônico.
[Dados do ensaio e hashes](si006-stale-session-generation.json)

Passaram a nova regressão no repositório e a checagem de admissão
ao lado dela, ambas com o pacote instalado. O Ruff também passou.
A troca de geração foi injetada no SQLite para reproduzir o estado do
painel. Este ensaio cobre o contrato HTTP e o despacho, sem avaliação
do navegador durante a troca de geração.

O marco adiciona o teste e a evidência, sem migração. Reverter
o commit remove ambos.
