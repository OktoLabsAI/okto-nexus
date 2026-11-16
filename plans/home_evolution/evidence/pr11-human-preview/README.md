# Prévia para avaliação humana §9

**Captura técnica pronta; avaliação humana de10segundos ainda NOT_RUN.**
Nenhum participante foi simulado e nenhuma resposta humana foi presumida.
Para uma avaliação não conduzida, a imagem é o estímulo; `metadata.json` e os
fatos abaixo servem ao revisor e não devem antecipar respostas ao participante.

## Capturas

- `first-fold.png`: viewport1440×1100, projeto Orion/home-alpha, antes de scroll.
- `full-page.png`: captura Playwright fullPage. O scroll é interno ao dashboard;
  isso não significa que toda a lista longa apareça em uma única imagem.
- `work-and-result.png`: detalhe após scroll real por wheel, sem alterar CSS/dados.
- `served-index.html`: HTML HTTP servido, byte a byte igual ao index estático
  pinado do produto. O conteúdo visível após React está em `metadata.json` e PNGs.

Fonte: fixture padrão `browser_fixture.py`,17 handoffs, sem injeção do contrato
Server, sem estados Running falsos e sem alteração do seed. Backend do checkout
`3d95aad8c1b5d2e6354cd872512586fd7a02aec9`, bundle `index-Dcu4bArB.js`.
O prefixo instalado final não foi acessado ou alterado.

## Fatos observados para o revisor

Os quatro contadores visíveis são Running0, Waiting to start14, Needs you0 e
New results1. Work tem15 itens no projeto, com10 na página inicial. Atenção
acionável do projeto e Server estão em0; o badge lateral Attention mostra2
ocorrências canônicas gerais, não é o contador Needs you.

No primeiro fold, `Review the integration / Awaiting owner` e
`Validate the response / Claimed` aparecem inteiros. `Verify the delivery /
Awaiting verification` aparece parcialmente no limite inferior. O resultado
`Document the result / COMPLETED · verification COMPLETED · Unseen` aparece
inteiro. Claimed não é uma prova de execução nativa. Esses fatos são dados
sintéticos canônicos, não resultado de inferência real.

## Amostra de navegação

Uma amostra completa foi retida com cache HTTP desabilitado via CDP em Chrome
próprio157.0.8103.51: overview1198,30ms; primeiro Work no DOM1533,30ms;
duas oportunidades de frame subsequentes1539ms. Corpo overview12664B.
O snapshot de recurso foi tomado no primeiro Work; o registro integral também
mostra a segunda leitura normal pós-assinatura em285,45ms.

Isso não é p95, latência de HomeService.read isolada,20 GETs HTTP sequenciais,
cache frio de OS/SQLite, início do processo Chrome ou compreensão humana.
Um primeiro ensaio passou, mas seu stdout foi truncado antes de reter todos os
metadados; o ensaio completo foi repetido e essa proveniência é explícita.

Zero consoleErrors, pageErrors e POST. Browser próprio fechado, PID ausente;
fixture teve saída física0 pelo handle. Os arquivos de servidor/cliente já
existiam antes do READY final e os8 pins de import conferem. O script executado
foi comparado integralmente ao transcript retido. A sonda genérica de scroll
não cobriu o wrapper real; o efeito do wheel está nas capturas, sem alegação
de uma medição exata de scroll nesses campos.
