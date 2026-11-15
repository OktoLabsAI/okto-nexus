# HOME-R1 — entregas incrementais

## PR-00 — baseline, fontes e contrato

Resultado: checkout reconciliado, versão0.3.4 e branchfeature/v0.3.4; contrato
de projeção, mapa de origem/autorização/SSE e ADR de visto documentados. A Home
existente continua sem mudança funcional. Fonte do plano preservada por hash;
ledger separado com36tarefas/73cenários e10invariantes.

Core/Connector e protocolo permanecem iguais. Main foi recuperada e seus três
commits de testes foram integrados sobre o trabalho R3. O package.json foi
normalizado para remover a chave test duplicada pela integração.

### Validação executada

- Fixtures reais em SQLite descartável:6casos PASS, escopo e comandos em
  [qualification.json](evidence/pr00-fixtures/qualification.json); Ruff F PASS.
- `rtk proxy .venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/test_readme_error_table.py`:
  3PASS em1,03s, tool709e69.
- `rtk npm test` emfrontend:154PASS,0falhas, toolffcd71; lógica/SSR Node,
  não navegador ou73casos novos aprovados.
- `rtk proxy uv lock --offline --find-links vendor/wheels`: somente versão do
  Nexus alterada; Core0.0.14 continua vendorizado.
- `rtk proxy uv sync --offline --find-links vendor/wheels --extra dev --extra serve-lite --locked`:
  ambiente de desenvolvimento atualizado para0.3.4; cache cross-drive usou copy,
  diretório temporário antigo ignorado, sem alteração de configuração pessoal.
- `rtk proxy npm ci`: instalação pelo lock existente. Audit reportou7advisories
  de dependências dev/build; não se declara audit limpo nem se executou autofix.
  A avaliação estática não identificou esses caminhos no produto de assets
  servido pelo Python. Devserver não será tratado como servidor de produção.

Fixtures de A→B→C, multiworkspace/sessões/tentativas, OBS TTL, cleanup e revogação
estão disponíveis; escala100/1000/100001 e medidas de consultas existentes são
descritas emperformance.md. Erros iniciais de montagem das fixtures estão
preservados como antecedentes, sem promoção de falha de fixture a bug do produto.

### Limites, migrações e reversão

Não há migration, nova tabela, provider, browser, serviço pessoal, deploy ou
release nesta PR. Todos os73cenários HOME-R1 continuam NOT_RUN. A revisão manual
dos contratos desta PR qualifica sua documentação, não comportamento futuro.
Rollback é reversão dos arquivos de baseline/versão; dados não foram migrados.

Próximo incremento: PR-01, read model batch autorizado e APIs de leitura; depois
PR-02 consome esse contrato na Home. O fallback clássico será preservado no
controle de apresentação, sem efeitos no runtime.

## Foundation e apresentação — implementação incremental

Foundation commit/push `c5294a30`: DTOs, adapter GET compartilhado, navegação
tipada, apresentação, controller serial e hook. Qualificação final tem 26 testes
focais únicos e TypeScript PASS. Resultados originais e testes de deltas são
aditivos; não somar rodadas sobrepostas. Não há novo EventSource.

Interface PR-02/03/04 reutiliza composer Meta-harness, inspeção canônica e modal
nativo no modo drawer. Continuação fixa a sessão exata e revalida antes de agir.
Respostas tardias após logout/unmount não publicam artefato, envio ou checkpoint.
Qualificação Node/SSR: 28 casos únicos (16 novos e 12 regressões), sem alegação
DOM. Build TypeScript/Vite PASS; outputs pinados em
`evidence/pr02-04-ui/qualification.json`. O warning de bundle acima de500kB
permanece explícito. A regressão frontend integrada executou196 testes PASS,
sem falha/skip, tool31a86d,8,57s.

Os três cortes visuais compartilham a extração do composer/inspeção e são
submetidos juntos como marco coerente; a numeração das tarefas/aceites permanece
individual no ledger. O controle local começa OFF até a qualificação M3. Ainda
não há promoção dos73cenários, release, deploy ou campanha real nesta etapa.

Seis checks reais de navegador em fixture loopback descartável passaram,
incluindo escopo, alvo exato, rascunho/foco/seleção,360px, fallback e403. São uma
rodada preliminar contra o servidor iniciado antes das últimas mudanças backend;
repetição com fontes finais pinadas é necessária. Ver
`evidence/pr06-browser/preliminary.json`; não substituir por testes SSR.
