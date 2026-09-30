# Capabilities de sessão R4 — incremento parcial M02/M06/M09

Data: 30 de setembro de 2026. NS03.04 e CON-R4-03 continuam parciais.
G0–G3 permanecem abertos, com as flags de prontidão inalteradas.

## Implementação

O Nexus implementa `POST /v1/runtime/sessions/{id}/capability` pela identidade
canônica do sujeito ou por operador autenticado representando-o. A emissão
exige uma sessão admitida, binding/perfil/realização válidos e grant canônico
vigente. Revalida o principal, o escopo, o guard da configuração e as revisões
persistidas dentro da transação. A emissão não despacha uma operação.

O segredo aleatório é retornado uma vez, com `Cache-Control: no-store`; só seu
hash permanece no banco. A reserva distingue as audiências `nexus-mcp-session`
e `nexus-native-session`, preserva as ações pedidas como teto e tem validade
de no máximo 120 segundos, limitada pelo grant/lease aplicável.

Replay idêntico retorna `CREDENTIAL_MATERIAL_UNAVAILABLE` com ID do derivado
e elegibilidade de recuperação. Um novo pedido pode substituir o derivado
somente antes de haver envio de abertura potencialmente efetivo ou histórico
de lease. Expiração não prova que a configuração nunca chegou ao harness.
Pedido divergente, sujeito cruzado e substituição insegura são recusados.

O port `ExecutionCapabilityService.authorize_call` confere token, audiência,
ação, escopo completo, revisões, política atual, sessão READY e lease aplicada
vigente. Ele não substitui os guards de permissão/claim de cada caso de uso.
O commit legítimo de `lease.applied` atualiza a validade do mesmo segredo;
enviar um grant ou repetir um ACK não reancora a validade. Revogação/revisão
do grant invalida as capabilities derivadas.

O Connector adiciona um cliente R4 específico que valida o opening pelo Core,
confere o DTO completo e fixa a URL MCP à origem e ao caminho aprovados.
Captura prazo monotônico antes do HTTP, recusa resposta tardia e não repete
automaticamente a emissão. O segredo não aparece no repr; a redaction cobre
os novos tokens e a exceção de replay preserva apenas metadados de recuperação.

## Dados e contrato

A migração **080** expande `execution_session_capabilities` com intenção,
ator, escopo e grant/revisão de origem, datas e referência de substituição.
Acrescenta unicidade de pedido e de audiência viva por sessão. Registros
históricos sem escopo não autorizam chamadas. Os testes cobrem banco novo e
upgrade aditivo desde a baseline da suíte; o ensaio completo de backup,
restore e downgrade continua em M12.

A seção 2.4 do contrato e `ErrorBody` agora explicitam `capability_id` e
`recovery_allowed` no erro de replay. A concatenação e os hashes correspondentes
do manifesto foram atualizados. Isso não publica outro bundle NXL nem altera
o hash do Core compartilhado.

## Evidência e alcance

O [manifesto coordenado](test_runs_20260930_capabilities.json) registra comandos,
hashes, artefatos e tentativas. Resultados sobrepostos:

- Connector final: **343 passes e dois skips existentes**.
- Nexus dirigido: **46 passes**, antes do reforço final do ledger de revisões.
- Nexus R4 inicial: **134 passes**, antes desse reforço e dos três novos casos de ledger.
- Nexus R4 final: **137 passes**, incluindo o ledger e os erros HTTP conformes ao schema.
- Instalado inicial: **117 passes**, também anterior ao reforço.
- Instalado após o ledger: **120 passes**; repetição final após corrigir o DTO de erro: **120 passes**, incluindo as revisões e a integração pública
  do cliente Connector com o Server, com bytes conferidos contra os wheels.

As falhas iniciais de status HTTP, estágio do ACK e import da fixture são
preservadas. A validação da rota nova passou a usar HTTP 422 para forma inválida.
O teste de renovação foi corrigido para enviar `RENEWED`, conforme o Core.
O helper de erro /v1 passou a retornar `action` como texto vazio quando não
há ação corretiva; `null` não satisfazia o schema. As respostas negativas
da rota são verificadas contra `ErrorResponse`.

A prova usa TestClient/ASGI, WSS de laboratório e fixtures de seleção e
qualificação sintéticas. A transição READY nos testes do guard é isolada e
explicitamente semeada; não demonstra spawn de provider. A campanha instalada
executa fora dos clones com `python -I`, o mesmo Core e imports de site-packages.
Os três assets Nexus já modificados pelo usuário entraram no wheel de teste;
eles não pertencem a este commit nem qualificam UI ou release limpa.

## Trabalho restante

O middleware MCP ainda autentica chaves canônicas; os tokens novos não recebem
fallback de identidade. Falta ligar o port de capability aos handlers reais
MCP/native-actions, com limites de workspace/sessão e os guards de domínio.
Portanto, este incremento **não fecha NS03.04**.

No Connector, persistir intenção de emissão e material protegido, compor
perfil/ambiente aprovados e adotar esse cliente no launch provider. Depois,
completar lanes automáticas, renovação, reconciliação não vazia e publicação
durável. Embedded, jornadas UI/CLI, auditoria US English, migração/rollback e
qualificação de providers/hosts continuam exigidos pelo plano integral.
