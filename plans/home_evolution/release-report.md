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

## PR-01 — projeção autorizada e fronteiras

APIs Homev1 paginam trabalho/resultados/atividade/agentes/observação e resolvem
alvos exatos. Um UoW de leitura fixa relógio e configuração; consultas batch
reutilizam a ocorrência Attention e sua autorização. A projeção não depende de
mensagem operator, preserva claims históricos e distingue aceitação, início
confirmado, resultado, verificação e cleanup. No overview, uma materialização
SQL local à statement compartilha Attention; falha mantém os blocos honestos.

Qualificação backend:30 casos únicos PASS (28 Home +2 regressões Attention),
Ruff/diff-check PASS, conforme `evidence/pr01/qualification.json`. Outros5 casos
SQLite/ASGI em `evidence/pr06-boundaries/qualification.json` verificam visto
isolado, autorização e entrega de artefato ativo. A falha real inicial de HTML
inline foi corrigida nos headers canônicos: attachment para HTML/SVG/XHTML,
sandbox, nosniff e no-store; storage e autorização existentes preservados.

Não há migration, novo scheduler, chamada de provedor ou efeito de runtime.
O estado filtrável corresponde a Work state; workspace/agente valem para todos
os blocos, cujas dimensões nativas não são traduzidas arbitrariamente. A medida
ampliada ainda excede500ms p95; os relatórios de custo não declaram SLO aprovado.
Esses testes usam SQLite real e HTTP ASGI em processo, não harness ou browser.

## Qualificação instalada e correções encontradas na integração

O wheel/sdist0.3.4 do corte `bff71b13` passou Twine, instalação isolada e17
testes de terminal/pacote, sem mudança dos inputs durante a rodada. Foram
verificados origem site-packages/bytes de três pacotes, bootstrap sem
Connector/torch e ciclo CLI com peers nativos sintéticos, sem visitar Home.
`evidence/pr06-package/qualification.json` identifica esse artefato e seus limites;
ele antecede as correções abaixo e não será apresentado como wheel final.

Testes adicionais encontraram e corrigiram: título genérico de resultado quando
há tarefa canônica; operador humano contado como worker; texto de segredo
reconhecível em preview de resultado manual; aviso aria-live que só mudava no
primeiro lote; e grade de zeros no estado ocioso. As falhas anteriores ficam em
`evidence/pr06-semantics/` e `evidence/pr06-browser-extra/`. O resumo usa a política
de redação existente, com IDs exatos; não se promete detector universal de PII.

As correções visuais passaram18 focais Node e build TypeScript/Vite; seis checks
de Chromium confirmaram estado vazio/ocioso, teclado,360px, guard de fontes
desconhecidas e dois lotes aria-live com cancelamento ao trocar escopo. A prova
aria-live é DOM; fala de leitor de tela e teste humano de10segundos permanecem
distintos. A tentativa de zoom real no browser isolado não alterou escala e
Settings não estava disponível;200% permanece NOT_RUN, sem substituto CSS.

Há37cenários qualificados no menor nível indicado por suas evidências; os36
restantes mantêm NOT_RUN, incluindo partes de integração que ainda exigem prova.
Uma instalação e rodada final devem incorporar as correções posteriores ao
wheel inicial. Campanha HOME-033 continua sem consentimento/execução paga nesta
fase; nenhum orçamento R3 foi reaproveitado. O controle de apresentação segue OFF.

## Revisão de namespace e último corte instalado

O corte `f948c5d7` passou33 testes instalados de consulta/semântica/pacote, sem
mudança de2.109 inputs, mais Twine. Evidência em `evidence/pr06-package-final/`.
Após essa rodada, a revisão de identidade detectou uma colisão de operation_id
entre executores: a segunda atividade podia desaparecer ao paginar e herdar a
referência Attention do primeiro executor. Três falhas reproduzidas em SQLite
foram corrigidas com namespace executor/sessão na chave direta e no join.
Sete focais passaram; `evidence/pr06-namespaces/` preserva antes/depois.

O delta é exclusivamente de projeção, sem migrations, protocolo, alteração de
IDs canônicos ou efeitos. Uma qualificação instalada focal incorporará esse
último corte; não se atribuem esses novos bytes ao wheel anterior. O benchmark
final1/10/100workers em `measurement-final-workers.json` permanece vinculado ao
fonte `f948c5d7`:46queries/GET constantes e500ms p95 não atingido em quatro casos.
O workload só contém handoffs; não foi usado para afirmar latência de operações
diretas ou de execuções nativas reais.

## Consolidação após namespace e qualificação visual

A qualificação instalada focal do namespace passou4 testes no wheel
`c41f00cb…`, com2.110 inputs imutáveis e bytes dos3 pacotes conferidos; ver
`evidence/pr06-package-namespaces/`. Uma correção de import relativo no próprio
teste permite coleta isolada `-I`. Outros23 casos canônicos executados em
`evidence/pr06-canonical-reuse/` qualificam APIs/CAS com peers sintéticos,
sem serem apresentados como decisões de modelo real.

A contagem atual substitui os totais históricos anteriores:50PASS/23NOT_RUN,
com o menor nível e os limites indicados no test-ledger. Zoom real200% agora
passou no Chrome em perfil de teste próprio. Foram corrigidos o overflow de
título longo em360px e a marcação global de desatualizado quando somente uma
fonte falha. As seções frescas preservam ações; uma seção parcial mantém suas
ações bloqueadas.18 focais Node e build passaram; evidência em
`evidence/pr06-browser-final/`. A fala de leitor de tela e a compreensão humana
em10segundos continuam sem prova. O último wheel ainda será recomposto com
esse delta estático antes de preparar a campanha paga para consentimento.

## Retorno de aba em segundo plano

Duas barreiras determinísticas reproduziram a habilitação precoce de controles
ao retornar à aba, inclusive quando um GET anterior ainda estava pendente.
O controller agora marca as seções desatualizadas antes do refresh e invalida
a resposta iniciada antes do retorno, mantendo uma única requisição em voo.
12 focais passaram; a regressão completa passou200/200 e o build final passou
com bundle `index-D4dmKnLh.js`. Antecedentes e fontes em
`evidence/pr06-visibility-revalidation/`. Nenhum efeito de runtime foi alterado.

## Estado consolidado do corte final

Produto enviado em `fa2e4215`; frontend200/200 e build PASS. Os sete checks de
navegador passaram novamente com o backend atualizado e bundleD4dmKnLh,
sem mutações ou erros JS. Wheel final0.3.4 SHA256
`7e1563622f4becb21cc62b6182cb4683c7546861256c355c16bb9aa78efa87ff`
e sdist passaram Twine; o focal instalado de pacote passou,699 payloads e7
assets iguais ao checkout,3 origens instaladas conferidas e2.110 inputs
imutáveis entre build/teste. Ver `evidence/pr06-package-ui-final/`.

O ledger consolidado contém56PASS/17NOT_RUN. A auditoria
`evidence/pr06-final-audit/audit.json` distingue o que cada prova cobre e quais
asserções ainda faltam; não soma execuções sobrepostas nem transforma revisão
de código em execução. Os36 itens e10 invariantes agora têm referências e
escopo de qualificação. Core/Connector continuam limpos nas branches anteriores,
sem mudança necessária de protocolo ou versão nesta frente.

M3 permanece em revisão e a Home clássica continua padrão. Faltam a campanha
real consentida, a avaliação humana de compreensão em aproximadamente10s e
os ramos de aceite ainda não executados. Fala de leitor de tela não foi medida.
Os quatro p95 medidos excedem500ms; nenhum SLO de produção ou deploy é declarado.
A proposta da campanha é inerte, com dados sintéticos e orçamento independente;
preparação e testes offline não significam execução paga.

## Qualificação adicional de eventos

Quatro novos testes determinísticos exercitaram eventos durante snapshot,
reconnect/gap, hints duplicados/fora de ordem e TTL externo com stream live.
Todos passaram, sem alteração do produto ou do candidato de campanha.
E03/E05 passam no menor nível controller/presentation, complementado pela
expiração SQLite já executada. E02 continua NOT_RUN: falta a fronteira de
assinatura/transporte real, que esses testes não substituem. Ledger atual:
58PASS/15NOT_RUN. Ver `evidence/pr07-stream/qualification.json`.

Cinco novos testes SQLite/HTTP em `evidence/pr07-scope/` passaram e qualificam
A01/A02/B02: isolamento com mesmo agente em dois projetos e alterações adversariais
de trabalho/pendência/resultado em B, união paginada com vínculos repetidos e
retries, sessões READY/OPENING/cleanup sem turno produtivo. Ruff/diff-check PASS.
Uma falha anterior era falta de autoridade canônica na fixture, corrigida em
verify_by, sem mudança do produto. A08 permanece NOT_RUN sem produtor global
canônico disponível, sem fabricar NULL inválido. Contagem atual:61PASS/12NOT_RUN.

A fronteira E02 passou agora com TCP/SSE reais: commit entre overview e
assinatura, commit desconectado/reconnect e pruning com retention_gap real.
O HomeController de produção fez fetch HTTP real e observou1→2→3 atividades,
com pico de1GET concorrente. Cliente Node e fixture Uvicorn encerraram fisicamente
com código0. Ruff do sistema PASS; sem React/browser EventSource ou provedor
declarados. Ver `evidence/pr07-stream-boundary/`. Ledger:62PASS/11NOT_RUN.

## Interrupção com isolamento de sessão

O novo teste C10 passou na fronteira HTTP/SQLite/Core real, com dois peers
Python JSON-RPC sintéticos: HomeTarget resolve o alvo exato, sessão forjada é
recusada, turno obsoleto não tem efeito, interrupt cancela somente o selecionado
e a sessão irmã conserva turno, receipt e processo vivos. Cleanup usa interrupt
e close canônicos, com saída física dos dois peers comprovada por wait; códigos
reais1/1 preservados, sem alegar0. Ruff/diff-check PASS. Não é prova de clique
no browser nem inferência real. Ver `evidence/pr07-interrupt/`. Ledger:63PASS/10NOT_RUN.
