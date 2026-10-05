# Incremento: fechamento canônico com política

Data: 30 de setembro de 2026. Parte de M01/M04/M07/M11, sem fechamento desses
marcos ou dos gates G0–G3. Evidências detalhadas ficam em
[test_runs_20260930_close_policy.json](test_runs_20260930_close_policy.json).

## Implementação

- Core `0.2.27.dev0`: `CloseOperation.policy`, helper público
  `r4_close_operation`, razão 0–1024, drain 0–30 e interrupt 0–15. Schemas e
  projeção verificam todos os campos. Chamadas legadas sem política mantêm
  o hash anterior; contexto R4 instalado exige razão e política.
- Um producer por sessão sobrevive ao cancelamento do caller. Mesmo ID/hash
  observa o mesmo fechamento; ID concorrente ou política divergente recusa.
  Drain impede novo trabalho produtivo e conserva contenção. Deadline de
  observação não cancela o producer nem cria recibo fictício.
- Nexus: close passa pela resolução/admissão/reserva/dispatch existentes,
  preserva razão fornecida e usa política canônica 30/15. Não exige novo
  inventário nem lease produtiva não expirada para conter sessão existente;
  ação concedida, grant, lane, geração e demais escopos continuam obrigatórios.
- Recibo terminal de close do owner corrente fecha sessão/lease na mesma
  transação de receipt/outbox. Progresso/unknown preservam estado. O teste
  injeta falha SQL na projeção e comprova rollback e recuperação pelo mesmo
  recibo sem segundo efeito nativo.
- Connector consome a projeção do Core pelo publisher HTTPS existente;
  política divergente não pode corresponder ao hash do journal original.

## Artefato

Mesmo wheel em Core/artifacts e vendor/wheels dos dois consumidores:
`nexus_connector_core-0.2.27.dev0-py3-none-any.whl`, SHA-256
`f0a3203d3d6faa50ecdbcf98614cc9fdf121e0dfafb1be1d3f0b84d0f4c39af6`.
Pins, lock e versão de inventário foram alinhados. R3 permanece histórico,
R4 continua `development-partial` e Server não anuncia prontidão remota.

## Prova e limites

Passaram geradores R3/R4 com `--check`, verificador do wheel em venv limpo,
imports/recursos/smokes de consumidores e `uv lock --check`. O comparativo de
instalação verificou byte a byte 91 arquivos Core, 316 Nexus e 51 Connector
contra a fonte usada, com imports exclusivamente de `site-packages`.

Core completo de fonte: 908 passes, 74 skips. Nexus R4: 69 passes. Core
instalado (close/projeções): 21 passes. Nexus/Connector/Core instalados fora
dos clones (controles, embedded, receipts e vertical): 19 passes. Há
sobreposição. O manifesto registra também a regressão completa Connector.

A primeira regressão Core detectou export público sem documentação; a
documentação foi corrigida antes da regressão final e do build. A primeira
coleta Core instalada percorreu a raiz do drive e falhou em `D:/WpSystem`;
`--rootdir`/`--confcutdir` passaram a restringir a coleta ao diretório dos
testes, mantendo o Core instalado. Nenhum erro foi convertido em PASS.

As fixtures fornecem qualificação e metadata aprovada; peer nativo é
sintético. Não há prova de daemon, loop de outbox, provider, hosts separados
ou interface de produto. Assets HTTP previamente alterados pelo usuário
foram preservados, sem rebuild nem aceite de UI. Mensagens novas são US
English; auditoria integral de idioma permanece em M10.

Contenção durante CAS pendente continua aberta. A operação pública de close
aguarda seu frontier de journal; shutdown independente do recurso possuído
permanece o caminho de contenção quando admissão durável está bloqueada.
Esses limites não reduzem os requisitos de robustez do plano.
