# M02/P6.1 — intenção durável de capability no Connector

O schema 7 do StateStore registra intenção, digest, audiência, IDs e referência
de vault antes do POST. O segredo nunca é gravado no estado público.
SessionCapabilityOwner mantém um produtor por intenção, preservado quando o
waiter ou a espera de close é cancelada. O retorno só é liberado após gravação
do material no vault e do resultado no StateStore.

CapabilityLaunchProvider compõe esse serviço pela porta launch_provider do
R4ExecutionOwner. A configuração aprovada continua sendo responsabilidade do
caller; o guard de lane/configuração é reavaliado antes e depois das esperas.
O teste com Core real e peer técnico comprova que prepare/open só ocorrem após
o vault commit. A configuração final ainda não é carregada automaticamente
pelo daemon.

Resposta perdida conserva o request ID. Replay recebe os metadados canônicos
do Nexus; não gera substituição, novo segredo, processo ou turno. Respostas
concorrentes de metadados não apagam um resultado já armazenado. Drift da
intenção, namespace de vault adulterado, capacidade esgotada e validade
expirada falham antes de nova emissão.

## Testes e limites

Testes dirigidos cobrem cancelamento, perda de resposta, falha do vault,
repetição concorrente, alteração de escopo, capacidade, migração 6 → 7 e
passagem pela porta de abertura. A integração usa HTTP ASGI contra o Nexus
canônico e verifica uma única capability no banco após perda de resposta.

O segredo e seus metadados sobrevivem ao restart, mas ainda falta reidratação
sob autoridade reconciliada. Não se deriva nova validade de timestamp
persistido. Também faltam configuração aprovada automática, renovação e
política de retenção/limpeza dos registros terminais. Esses itens continuam
obrigatórios no plano; este incremento não encerra M02, P6.1 ou gates.

A [evidência coordenada](test_runs_20260930_capability_reservation.json)
registra artefatos, campanhas e limites. Não há qualificação de provider real,
ambiente local puro ou hosts independentes nesta campanha.
