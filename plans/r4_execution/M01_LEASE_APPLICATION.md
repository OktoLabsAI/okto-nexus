# M01 — aplicação de autoridade R4 no Core

Data: 30 de setembro de 2026. Incremento de desenvolvimento da branch
`feature/v0.2.0`, posterior ao targeting/inventário. M01 permanece em andamento.

## Artefato compartilhado

- Core: `0.2.25.dev0`.
- Wheel: `nexus_connector_core-0.2.25.dev0-py3-none-any.whl`.
- SHA-256: `e4918889b6c4ffc0b4cb0d172bf32f18ef9aeefbc35e0371cf94b373f34232e4`.
- Cópias idênticas em Core `artifacts/` e consumidores `vendor/wheels/`.
- Os 89 arquivos do pacote no wheel foram comparados byte a byte com o source.
- Manifest R4: `sha256:a316cfb1575c9d926c10dcf5ee3192979651aa7db0efb145fab7635094816f03`.
- Bundle permanece `development-partial`, `R4_BUNDLE_EXECUTABLE=False`;
  revisão negociável histórica R3 e gate de execução Server preservados.

## Implementação e limites

O Core cria nonce local e captura o relógio monotônico antes de enviar
`lease.renew`. Somente essa tentativa registrada pode instalar o grant.
`R4Authority` vincula sessão, workspace binding, revisões, credencial,
grant/lease/serial, conexão e boot ao `ExecutionContext`. O runtime verifica
o escopo completo de `operation.submit`; remover metadados, aumentar ações
ou prazo, cruzar conexão e reaproveitar outro nonce não autoriza efeito.

Instalação inicial precede prepare/open e não inicia harness. Renovação de
sessão aberta usa o CAS durável já existente. O cancelamento de um cliente
não cancela o produtor entregue. Perda de confirmação após commit pode ser
recuperada pela mesma tentativa sem novo CAS ou prazo, inclusive depois de
vencido o prazo anterior, desde que o novo ainda esteja válido.

Revogação fecha os fences de memória antes de esperar. Uma renovação em curso
continua sob ownership do Core; a revogação usa a geração efetivamente
gravada. Escritas aguardando thread e aberturas aguardando ambiente verificam
a autoridade novamente na fronteira nativa. Não há ACK de revogação enquanto
a abertura ou o CAS estiverem incertos. Repetições confirmadas são idempotentes.

O registro inicial R4 é local ao processo. A autoridade canônica e a
persistência dos grants pertencem ao Server/host autenticado. Um novo boot não
restaura prazo monotônico. Claims de sessão e CAS continuam duráveis no Core.
Esta entrega não implementa ainda o serviço canônico de emissão/revogação do
Server, reconciliação completa de grants nem ownership distribuído.

No Nexus, `EmbeddedExecutor.authorize_r4` obtém o grant por callback do host,
instala-o antes das operações e oferece renovação/revogação pela API pública.
O teste NS07 usa o adapter existente para open, submit, steer, interrupt e
close com contexto derivado pelo Core. O callback de emissão permanece
sintético; ainda falta ligá-lo ao writer canônico de admissão.

No Connector, `apply_r4_lease` usa o canal de controle negociado, envia o nonce
Core e só emite `lease.applied` após instalação. Esse trecho requer um único
owner do leitor; multiplexação, persistência e integração ao daemon ainda
pertencem a M06. O teste vertical instalado exercita esse trecho e valida
contexto antes de executar/publicar cinco operações no Nexus. A concessão e
as operações admitidas ainda são fixtures. Nenhuma prontidão de produto foi
habilitada por estes testes.

## Campanha

Os resultados finais e comandos ficam em
[test_runs_20260930_leases.json](test_runs_20260930_leases.json).

O Core passou 885 testes com 74 skips em Windows/Python 3.13.1. Os dez novos
casos cobrem escopo completo, replay, nonce/boot, ações vazias, aumento de
permissão indevido, CAS, cancelamento, perda de confirmação, revogação durante
reconexão, espera de journal, thread e callback de ambiente. Trinta e dois
testes dirigidos passaram também contra o wheel instalado.

O Connector passou 239 testes com dois skips na repetição completa. A primeira
execução encontrou uma fixture nova com seleção vazia, recusada corretamente
pelo Core. A fixture foi corrigida para usar candidato e raiz locais; os quatro
testes WSS e a suíte completa foram reexecutados. Não houve redução de critério.

O Nexus R4 passou 41 testes com um skip opcional durante a instalação sem
Connector. Após instalar o Connector com suas dependências no ambiente de
teste, o vertical passou. A instalação do Connector serve somente à campanha;
o Nexus de produto continua sem depender da aplicação Connector.

Passaram: verificadores dos geradores R3/R4, wheel em venv limpo, smokes dos
dois consumidores, importação isolada `python -I`, identidade do artefato,
`uv lock --check --find-links vendor/wheels` e sync frozen. O lock exige
`--find-links vendor/wheels` porque esta versão Core não foi publicada em PyPI.

Permanecem três warnings históricos do Core: falha deliberada da thread do
reader Pi e duas corrotinas `close` de doubles antigos não aguardadas. A
regressão ampla anterior do Nexus mantém seus defeitos registrados; esta
campanha dirigida não os encerra. Nenhuma campanha com provider real,
hosts independentes ou matriz completa Windows/Linux foi executada.
