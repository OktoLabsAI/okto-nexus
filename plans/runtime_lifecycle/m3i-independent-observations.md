# M3i — Observação e prontidão independentes por harness

Decisão de implementação, 2026-10-17. M3h reduziu o custo da descoberta, mas
continua aguardando o conjunto completo. Esta etapa remove essa dependência;
não altera as provas de identidade, contenção ou autorização.

## Contrato compartilhado

O snapshot de inventário passa ao formato 3. Sua cobertura contém exatamente
uma observação para cada adapter descobrível do catálogo:

- `PENDING`: ainda não há observação desta geração; idade e erro nulos.
- `PRESENT`: descoberta concluída com candidatos; idade própria da observação.
- `ABSENT`: descoberta concluída sem candidatos; idade própria da observação.
- `FAILED`: descoberta falhou; código técnico, sem evidência utilizável.

Ausência de resultado nunca equivale a `ABSENT`. Candidatos e linhas de
availability pertencem somente às observações concluídas. PENDING/FAILED
continuam explícitos na cobertura, sem uma linha falsa de NOT_INSTALLED.
O formato interno das linhas de availability permanece 2; o envelope 3 define
a cobertura parcial. Consumidores antigos recusam o novo envelope.

A idade efetiva de um adapter soma sua idade na emissão, a idade de transporte
do snapshot e o tempo desde o recebimento monotônico no consumidor. Publicar
outro harness não renova a observação antiga. Reiniciar o produtor começa com
PENDING; timestamps monotônicos não são recuperados de outro processo.
Os limites de freshness permanecem. Idade fica fora da revisão semântica;
estado/código da cobertura e evidência entram na revisão.

## Produção independente e limites

Um worker retido por adapter observa, aplica probes aprovados e publica seu
resultado. Cada um tem sua agenda, backoff com jitter, tentativa única e wake
de refresh. Um worker lento não impede as próximas observações dos demais.
O lock de publicação cobre somente montagem/CAS do snapshot; leitura de
arquivos e I/O de harness ficam fora dele. Shutdown cerca os produtores e
aguarda seus workers; cancelar um observador não libera o trabalho subjacente.

Requests explícitos de refresh registram a fronteira esperada por adapter.
Resultados iniciados antes do request podem ser publicados, mas não satisfazem
esse request. A falha de um adapter continua observável e não apaga resultados
dos outros. Refresh não cria um segundo worker concorrente do mesmo adapter.

## Consumo e migração

Uma única política interpreta freshness por adapter em preparação, seleção,
admissão, despacho, reuso, lease e capacidade. O agregado do host deixa de ser
um veto universal. Consultas e Agents/Graph distinguem host conectado,
observação do harness, autoridade, capacidade e recuperação de sessões.

Revalidação preserva a aprovação enquanto a observação estiver pendente ou
falhar; só uma descoberta concluída pode provar ausência/alteração. Sessões
ativas conservam seus fences e provas, sem replay. Seleções locais calculam
a revisão com a mesma cobertura publicada.

A migração dos baselines de seleção retidos reconhece explicitamente o formato
2, preservando toda a evidência consentida. A mudança de envelope, isoladamente,
não deve provocar `inventory_binding_review_required`. O formato anterior fica
restrito à leitura/migração de histórico, não à admissão de novas publicações.

## Entrega e provas necessárias

1. Core: envelope 3, cobertura estrita, cálculo de idade/revisão e testes de
   falsificação/omissão, idade por adapter e histórico.
2. Core/Nexus/Connector: workers independentes, fronteiras de refresh, shutdown
   e montagem/publicação incremental sob a geração correta.
3. Nexus: substituir todas as interpretações de freshness global, migrar
   baselines e atualizar projeções/UI sem divergência de autorização.
4. Campanha instalada conjunta: Pi bloqueado enquanto Claude/Codex renovam
   inventário e executam; falha/retorno do adapter; snapshot velho; troca de
   geração; refresh concorrente; rejeição de cobertura inválida; mesmas regras
   pelo Connector local. Nenhum teste de loopback equivale a host físico remoto.
5. Rollout conjunto dos consumidores M3i e gate real na UI, incluindo startup
   e pool. M3h já foi instalado com M3j na geração 72.

O checkpoint de contrato sozinho não habilita a funcionalidade nos consumidores
e não autoriza marcar L14/M3/UI-A como concluídos.

## Checkpoint Core qualificado — 2026-10-17

O Core implementa o contrato e `IndependentInventoryObserver`: um worker
retido por adapter, resultados imutáveis, idade desde o início da tentativa,
backoff independente e fronteiras de refresh. Um resultado inválido não
contamina a publicação dos demais. O orçamento de 128 candidatos é dividido
por adapter (42 atualmente); excedê-lo gera falha explícita daquele adapter,
sem truncamento. Encerramento aguarda todos os produtores mesmo quando o
chamador cancela sua espera. Um filho cancelado gera tentativa falha e permite
nova observação; cancelar diretamente o worker não é um modo de encerramento.

**117 testes instalados passaram**, sem falhas ou skips, com interpretador
isolado e 158 arquivos do pacote comparados com o wheel. Inputs permaneceram
inalterados e `pip check` passou. Inclui Pi bloqueado enquanto Claude/Codex
concluem cinco observações, idade/expiração individual, retries, refresh
concorrente, fronteira de geração e thread real retida durante shutdown.
O relatório reproduzível está em `m3i-core-results.json`; detalhes no Core,
`plans/runtime-lifecycle-m3i.md`, commit `6e97362`.

Esta é somente a base compartilhada. Os consumidores ainda usam o wheel M3h
e precisam integrar publicação, freshness, seleção exata e migração de
baselines antes do rollout. M3, L14 e UI-A permanecem abertos.

A inspeção da instância atual às 05:34 UTC confirmou geração 72
CONTROL_READY, os três agentes READY/Online e quatro sessões Pi aquecidas.
As autorizações continuavam renovando, chegando às revisões 13–15.
Não houve reinício nesta etapa, nem novo teste com o provedor Codex (L5).
