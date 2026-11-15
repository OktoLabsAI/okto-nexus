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
