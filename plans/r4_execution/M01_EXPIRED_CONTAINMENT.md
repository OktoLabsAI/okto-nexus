# M01 — contenção R4 depois da expiração produtiva

Data: 30 de setembro de 2026. Incremento Core `0.2.26.dev0`, consumido pelo
Nexus e Connector. Mantém R4 como `development-partial`, sem fechar M01/G0–G3.

## Comportamento corrigido

A verificação de contexto R4 recusava qualquer ação depois do deadline,
antes das exceções de contenção já existentes no runtime. Agora interrupt e
close previamente concedidos continuam autorizáveis após expiração produtiva.
Approval/input só recebem essa exceção para decline/cancel sem conteúdo do
operador, referência de resposta ou digest de conteúdo. A classificação vem
da operação validada; não existe flag de contenção aceita do peer.

Escopo completo, boot, grant, conexão, geração, ações concedidas e revogação
continuam obrigatórios. Uma resposta negativa ainda exige o pedido nativo
observado e sua correlação. Mudança do alvo, conteúdo ou identidade não
recebe exceção. O mesmo ID recupera o recibo, sem segunda aplicação nativa.

As verificações antes de autorização, leitura de recibo e efeito nativo usam
a mesma classificação. Respostas com conteúdo continuam produtivas mesmo
rotuladas como decline/cancel; a bridge nativa aplica o fence também nesses
casos. Os hashes e contratos históricos R3 não foram alterados.

## Pendência descoberta na campanha

Uma tentativa de permitir controles durante CAS pendente demonstrou espera
no `control_lock`: `renew_lease` mantém locks de efeitos durante o CAS do
journal. A implementação publicada conserva a recusa explícita
`LEASE_UPDATE_PENDING` antes dessa espera; não promete controles sem bloqueio
durante renovação pendente. O teste mantém a barreira ativa, confirma a recusa
e depois verifica que o contexto antigo e uma ação retirada continuam negados.

A evolução dessa coordenação precisa preservar o fencing de geração, o
produtor de CAS, o tratamento de confirmação perdida e o controle de recursos
durante shutdown. Ela permanece no trabalho de lifecycle/recuperação M11 e
de qualificação M01, sem transformar a recusa atual em aceite total do plano.

## Artefato e consumidores

- Wheel: `nexus_connector_core-0.2.26.dev0-py3-none-any.whl`.
- SHA-256: `d1fd93375b84f68f14c7a6a84b609bcee0d14876b8c75ec00a71a11d8ec71977`.
- 89 arquivos do pacote comparados byte a byte com o source.
- Mesmo arquivo em Core `artifacts/`, Nexus e Connector `vendor/wheels/`.
- Pins e lock Nexus atualizados; pacote instalado nos ambientes dos consumidores.
- Geradores R3/R4 conferidos; verificador de wheel limpo e smokes embedded/remoto
  passaram. Esses smokes não qualificam providers nem hosts distintos.

Os comandos, resultados e hashes de XML estão em
[test_runs_20260930_containment.json](test_runs_20260930_containment.json).

| Campanha | Resultado |
|---|---|
| Core completo, source | 892 passaram, 74 skips de plataforma/provider |
| Core dirigido, source | 90 passaram |
| Leases Core instaladas, repetição final | 17 passaram |
| Connector completo com Core instalado | 239 passaram, 2 skips |
| Nexus R4 com Core instalado | 56 passaram |
| Nexus NS07/NS09/NS10, três pacotes instalados | 17 passaram |

As campanhas se sobrepõem e não devem ser somadas como cobertura única.
Skips permanecem pendentes de ambiente ou qualificação quando aplicáveis.

O primeiro comando instalado com `-I` e pytest fora do clone encontrou um
import de helper `tests.regression` indisponível. A repetição executou os
testes a partir do repositório Core, com o Core instalado e sem adicionar
`src` ao path; importação isolada separada confirmou `site-packages` e bytes
dos módulos alterados. A falha inicial de configuração permanece registrada.

## Limites da entrega

O Nexus ainda resolve apenas abertura e submit pelo novo caminho canônico.
As entradas públicas das demais ações, inclusive contenção expirada pelo
dispatcher, precisam ser compostas em M04–M08. Este incremento torna a
semântica necessária disponível no Core; não substitui o trabalho nos hosts.
Daemon, embedded composto, reconciliação não vazia, decisões, UI/CLI, idioma,
migração e qualificação real permanecem obrigatórios no plano completo.
