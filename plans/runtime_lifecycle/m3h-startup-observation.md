# M3h — Descoberta paralela e espera correta do pool

2026-10-17. Nexus 0.3.1, Core 0.0.12, Connector 0.0.10, nas branches
`feature/v<versão>`. Checkpoint do M3 com contribuição para o M7.

## Diagnóstico e mudança

Na inspeção deste ciclo, a geração 71 já estava saudável: Pi, Claude e Codex
READY no backend e Online na tela Agents; Pi com quatro sessões aquecidas.
Nenhum reinício foi feito para esta inspeção. Isso não transforma o atraso
inicial registrado em L14 em um problema resolvido.

A descoberta completa fazia as leituras de Codex, Pi e Claude em sequência.
O Core passa a executar até três observações simultâneas, com fila de submissão
limitada, contexto de cancelamento por worker e join antes do retorno, inclusive
em erro. A identidade completa, os limites das leituras, a ordem do catálogo,
a exigência de confiança e a detecção de observações conflitantes permanecem.

Foi reproduzido um segundo problema: sem uma publicação atual de inventário, o
pool reservava quatro aberturas e contabilizava suas recusas de admissão como
falhas de aquecimento. O backoff cresce por instância: quatro recusas acumulam
16 segundos; outras quatro, 256 segundos. O teste anterior à correção falhou
na presença desse registro, sem nenhuma execução nativa iniciada.

O Nexus agora aguarda host, recuperação do agente e inventário atual antes de
reservar aquecimentos especulativos. A consulta reutiliza a regra canônica de
freshness, incluindo sequência e idade da observação. Espera por descoberta
não aumenta o contador de falhas. Admissão, despacho, identidade e permissões
continuam sendo verificados pelo caminho normal antes de qualquer efeito.
Falhas reais e recursos incertos conservam suas regras de backoff/contenção.

O backup anterior ao rollout M3g não tinha backoff. Os snapshots históricos
iniciais já foram compactados; não há evidência suficiente para atribuir todo
o intervalo de 4m46s da geração 71 a uma sequência específica dessas recusas.

## Validação

- Core: 22 testes de source; 59 testes instalados aprovados, 18 casos exclusivos
  de POSIX ignorados no Windows. Cobrem concorrência, limite de submissões,
  cancelamento, join em erro, identidade, descoberta e probes existentes.
- Connector: 35 testes instalados aprovados com o novo wheel do Core;
  byte comparison de 156/98 arquivos e `changed_inputs=[]`.
- Nexus: o caso anterior à correção reproduziu o defeito. Os nove casos de
  source passaram: três harnesses x inventário ausente/expirado/outra sequência.
  A campanha instalada passou em **46 casos**, sem falhas ou skips, em 564 s;
  incluiu startup, cancelamento, troca de autoridade, Connector local, prioridade
  da primeira instância pronta, reposição após recusa e fence de shutdown.
  Os 541/156/98 arquivos dos pacotes foram conferidos com os wheels,
  `changed_inputs=[]` e `pip check` passou. Resultados em `m3h-results.json`.
- Leituras passivas das três instalações reais: serial/paralelo/paralelo/serial
  em 21,94 / 10,74 / 13,94 / 21,75 segundos; mesma evidência completa nos quatro
  resultados. São amostras locais sob carga variável, sem executar os harnesses,
  sem credenciais e sem constituir SLA de startup.

O primeiro comando do benchmark usou por engano o Python global, que ainda
contém o Core M3e, e terminou com AttributeError antes de medir. Os quatro
resultados válidos usam o interpretador isolado com o Core M3h instalado.
O build do Core concluiu; seu wrapper PowerShell teve erro no `exit`, corrigido
na invocação seguinte dos demais comandos. O wheel foi verificado pelos testes.

## Limites e continuidade

O inventário ainda é publicado como snapshot completo. A prontidão independente
por harness exige representar explicitamente observações pendentes, ausentes,
falhas e respectivas idades. Publicar uma lista parcial como completa poderia
invalidar configurações de outros agentes; isso não foi introduzido.

M3, M7 e o gate UI-A continuam abertos. Não houve reinstalação global neste
checkpoint: a geração 71 permanece com M4d2/M3g e Core M3e, já validada na UI.
O rollout conjunto M3h deve acontecer no próximo marco significativo, com
observação do startup/pool pela interface. Nenhum merge, tag ou PyPI.
