# Ledger — Home operacional HOME-R1

Plano: [cópia imutável](plans/home_evolution/source-plan.md), originalmente em
`C:/Users/jpamb/Downloads/PLANO_CODEX_NEXUS_HOME_OPERACIONAL_R1.md`.
SHA-256: `af6aa910d2ebd6f420b3b5905838a6d50b301cf66d3b9c0f09fbbb26e8f9bf14`.

Este acompanhamento é independente do plano R3 anterior. Há **36 tarefas,
73 cenários e 10 invariantes**; nenhum teste, dispensa ou orçamento de provedor
anterior é promovido automaticamente para HOME-R1.

- [Tarefas e marcos](plans/home_evolution/execution-ledger.json).
- [Cenários de aceite](plans/home_evolution/test-ledger.json).
- [Baseline](plans/home_evolution/baseline.md).
- [Fontes, autorização e invalidação](plans/home_evolution/source-map.md).
- [Contrato](plans/home_evolution/contracts.md).
- [ADR de visualização](plans/home_evolution/adr-result-view-state.md).

## Retrato atual — 2026-11-16

Produto `3d95aad8` enviado em `feature/v0.3.4`, com a faixa Servidor separada.
Matriz: **71 PASS / 2 NOT_RUN (H02/I01)**. O gate **M3 não foi aprovado**;
a Home clássica continua padrão e o objetivo completo ainda não é declarado
concluído.

O [pacote final](plans/home_evolution/evidence/pr10-package-server-final/qualification.json)
passou12/12 focais instalados e Twine, com699 payloads/7 assets, três origens
conferidas e2.116 inputs imutáveis. Wheel0.3.4: `c1c45e2a…`, bundleDcu4bArB.
Não houve novo build para contornar a ausência de Twine na venv; foi usada a
ferramenta já instalada nos mesmos artefatos.

O [HTTP real](plans/home_evolution/evidence/pr12-http-performance/qualification.json)
mediu20 amostras quentes por conjunto, após aquecimento: p95 de281,28/227,64/
289,28/450,32ms para1/10/100 workers e100 workers com1.000 atividades/100.000
eventos. Os quatro atingiram a meta local de500ms, com46 SQL/GET e0 writes.
O [experimento de serviço PR08](plans/home_evolution/evidence/pr08-performance-final/qualification.json)
permanece separado, incluindo seu p95 grande de
673,91ms; condições distintas não permitem subtrair overhead ou prometer SLO
de produção. As medições antigas permanecem no histórico com seu próprio corte.

As [capturas para avaliação humana](plans/home_evolution/evidence/pr11-human-preview/qualification.json)
e o [focal manual DOM/HTTP](plans/home_evolution/evidence/pr09-screen-reader-attempt/manual-qualification.json)
estão preparados e qualificados nos limites indicados. Não houve participante
avaliando compreensão em10s nem fala de leitor de tela. H02 continua NOT_RUN;
I01 ainda requer observar a continuidade dos processos vivos ao alternar Home.

A [proposta de campanha](plans/home_evolution/evidence/pr06-campaign-proposal/PROPOSTA.md)
está vinculada ao candidato `6181fd00…` e ao pacote final. Mantém o mesmo UUID,
diretório, IDs e orçamento observado de200 mil tokens/no máximo2 chamadas.
Não há consentimento, reserva, diretório ou execução dessa campanha; a recusa
antes de efeitos foi comprovada. A preparação não será apresentada como
inferência real. Restam HOME-033 consentida, H02/I01, compreensão humana e gate M3.

Os registros seguintes preservam o estado histórico de cada marco, inclusive
pendências posteriormente resolvidas. Este retrato é o estado vigente.

## 2026-11-15 — PR-00 em andamento

Working tree inicial limpa em `feature/v0.3.3`, HEAD `7e0cec1e`. Main recuperada
em `8d77b50c`; três commits de testes/CI foram integrados sem conflito de conteúdo,
preservando o trabalho R3. Nova branch `feature/v0.3.4`, baseline integrado
`970fd3deef61c913c92462b14925cefad8d0644d`. Os oito arquivos centrais da Home
consultados continuam iguais à referência `4ba6fa40` do plano.

Nexus foi atualizado para 0.3.4, incluindo frontend e locks. A integração de main
gerou uma chave `test` duplicada no package.json; ela foi consolidada no comando
atual da main. O lock Python requer `--find-links vendor/wheels` para resolver a
dependência local Core0.0.14; a primeira tentativa sem esse argumento falhou sem
alterar dependências e a resolução offline correta atualizou somente o Nexus.

Core/Connector permanecem 0.0.14/0.0.12: não há lacuna de protocolo demonstrada.
O diagnóstico confirma Graph global e diretório operator-only inadequados para
inventário de trabalho. A implantação começa por projeção batch com escopo antes
de total/paginação, sem modificar a semântica dessas fontes existentes.

Fixtures e baseline de validação estão em preparação. Os 73 cenários continuam
NOT_RUN até suas próprias execuções. Não houve campanha de provedor, acesso a
dados de produção, evento Windows, deploy ou release.

### Fechamento da PR-00

HOME-001–004 foram qualificados no escopo de baseline, especificação revisada e
fixtures, conforme o aceite de cada tarefa. Seis testes SQLite das fixtures,
três testes da tabela de erros e 154 testes frontend existentes passaram.
Os 73 cenários da nova Home permanecem NOT_RUN; Node/SSR e consultas atuais não
substituem integração da API nova, browser ou campanha com harness real.

As [medidas locais](plans/home_evolution/performance.md) e o
[relatório incremental](plans/home_evolution/release-report.md) identificam seus
datasets e limites. Há sete advisories dev/build no lock existente, sem caminho
de exploração demonstrado no produto estático; não foi aplicado autofix.
O próximo marco é PR-01, a projeção operacional autorizada e paginada.
# Marco de foundation da Home

DTOs/adapter GET, alvos tipados, apresentação, controller e hook implementados.
Qualificação final focal: 26 testes Node únicos PASS; TypeScript integrado PASS.
Os testes exercitam relógio e promessas controlados, incluindo duas correções
encontradas na auditoria: feed que sumia após refresh e páginas descartadas ao
fechar drawer sem alteração de revisão. Evidência em
`plans/home_evolution/evidence/pr05-foundation/final-qualification.json`.
Este marco não qualifica DOM, backend, pacote, provedor ou os 73 cenários.

## Marco da interface operacional

Foundation enviada em `c5294a30`. Layout, listas, atenção compacta, resultados,
drawers e composer compartilhados implementados com flag de apresentação OFF.
Qualificação UI:28 casos focais Node/SSR e build PASS; regressão integrada:
196PASS/0falhas. As tarefas de interface ficam IMPLEMENTED até o aceite integrado.
Seis checks de browser reais passaram em rodada preliminar; fontes backend
alteradas posteriormente exigem repetição antes da qualificação final.

## Integração, pacote e revisão dos limites

Backend enviado em `60069bc5`, com formatação do port em `bff71b13`. O pacote
desse corte passou17 testes instalados e Twine, além da regressão frontend196.
Sete checks reais adicionais comprovaram escopo, detalhe, draft/foco, paginação
de15atividades/scroll exato,360px, fallback e limpeza por403.

Na revisão foram corrigidos títulos de resultados, contagem de workers sem o
operador humano, redação de segredos reconhecidos, estado vazio/ocioso compacto
e anúncio DOM de lotes sucessivos. Fontes e evidências estão separadas por corte;
o pacote inicial não contém as correções posteriores. Há37cenários PASS no
escopo específico das provas e36NOT_RUN. O objetivo completo ainda não foi dado
como concluído. Campanha real, teste humano e os limites de acessibilidade
seguem explícitos; a nova apresentação permanece OFF até a decisão M3.

## Qualificação final de namespace e navegador

O corte namespace passou4 testes instalados;23 casos canônicos executados
qualificaram decisões e preferências via APIs/CAS com peers sintéticos. Zoom
real200% passou no Chrome. Corrigidos overflow de título em360px e isolamento
de freshness por seção.18 focais Node e build passaram. A contagem atual é
50PASS/23NOT_RUN; os totais anteriores são históricos. Evidências em
`plans/home_evolution/evidence/pr06-{canonical-reuse,package-namespaces,browser-final}`.
Pacote final com o delta estático e campanha local continuam separados;
nenhum novo consentimento pago ou execução de provedor ocorreu nesta etapa.

## Corte final empacotado

`fa2e4215` enviado,200 testes frontend PASS e build PASS. Sete checks finais
de browser PASS com backend atualizado. Wheel0.3.4 `7e156362…` e sdist passaram
Twine;1 focal instalado PASS com699 payloads/7assets e3 origens conferidas,
2.110 inputs imutáveis. A auditoria por requisito consolida56PASS/17NOT_RUN.
Tarefas e invariantes receberam fontes, testes e limitações explícitas.
M3 não foi aprovado: campanha consentida, compreensão humana e ramos restantes
continuam separados; p95 de500ms não atingido. A apresentação segue OFF por
padrão. Core/Connector permanecem limpos e sincronizados nas branches existentes.

## Qualificação adversarial adicional

Quatro testes novos do controlador passaram para eventos durante leituras,
hints duplicados/fora de ordem e TTL externo com stream live. Outros5 testes
SQLite/HTTP provaram isolamento adversarial A/B, união paginada sem duplicações
e estados técnicos READY/OPENING/cleanup sem turno produtivo. Produto e wheel
permanecem iguais; são deltas de testes. Ledger atual:61PASS/12NOT_RUN.
A08 permanece sem produtor global canônico exercitado; não foi criada uma
linha inválida para simular esse aceite. Evidências `pr07-stream` e `pr07-scope`.

A fronteira snapshot/SSE real passou nas três fases de commit/reconnect/gap,
com cliente e servidor próprios encerrados. O interrupt exato passou com duas
sessões e peers sintéticos: irmã intacta, cleanup canônico e saída física de
ambos comprovados, com códigos reais1/1. A regressão frontend inteira passou
204/204. Ledger atual:63PASS/10NOT_RUN. Produto e candidato pago não mudaram.

## Faixa Servidor e fechamento dos testes de contrato

Histórico/rascunhos/teclado e perguntas nativas/concorrência elevaram a matriz
a70PASS. A revisão A08 encontrou uma lacuna real e a corrigiu: faixa Servidor
separada, cursores Home por partição e hint somente de workspace, sem perder
a evidência de B ao filtrar o remetente A. São11 novos casos backend,210
frontend, build e6 checks de browser PASS. A regressão ampla foi233PASS/1falha
de expectativa antiga de migration, corrigida e qualificada por focal.
Contagem atual:71PASS/2NOT_RUN (H02/I01). O novo pacote e a medida de volume
completo ainda estão pendentes. O candidato pago D4 permanece antecedente,
sem execução. H02 depende da ponte Windows, que retornou native pipe unavailable;
não houve leitor de tela iniciado nem captura de fala real.
