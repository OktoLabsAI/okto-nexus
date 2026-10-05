# M02/P6.1/P6.3 — metadados e recuperação da capability

## Contrato e autoridade

A consulta sem material prevista no contrato é implementada por
GET /v1/runtime/sessions/{id}/capability. São 24 rotas: as 23 originais
mais essa consulta. A query é fechada e correlacionada por nonce;
parâmetros extras ou duplicados são recusados. O DTO não contém segredo
nem hash de segredo. O contrato HTTP, schema, mapa de rotas e validadores
foram atualizados; o wire Core/NXL permanece inalterado.

O Nexus exige sujeito autorizado ou operador, sessão READY, lease ACTIVE
aplicada, capability/grant vigentes e revisões compatíveis. A consulta não
altera emissão, validade ou estado. Seu TTL restante é limitado pela
capability e pela lease. Retornos carregam Cache-Control: no-store.

## Recuperação no Connector

O cliente valida nonce novo, escopo e tipos exatos, audiência, ações,
origem e prazo ancorado antes do HTTP. SessionCapabilityOwner.restore
consulta o contexto público atual do Core e exige o mesmo ID/serial
de lease retornado pelo Nexus. O prazo final é o menor dos dois.

O material existente vem do vault; não é reconstruído ou substituído.
A autoridade é revalidada após as esperas de metadata, vault e commit.
O owner mantém a task de recuperação durante cancelamento do observador.
A recuperação não cria runtime, não instala lease e não reenvia abertura.

## Provas e limites

A campanha integrada usa Core real, journal/lease reais, HTTP ASGI e um
peer nativo técnico. O teste recria o owner/StateStore, recupera o mesmo
segredo e consulta o handoff pela bridge pública. Também cobre renovação
aplicada nos dois lados, serial divergente, revogação e vault sem material.
A sessão READY e a seleção usam fixtures; não é reboot completo do daemon.

A composição automática da configuração, reconciliação não vazia do daemon,
agendamento de recuperação/renovação, retenção terminal e aceites reais de
provider/SO/hosts permanecem pendentes. Nenhum gate ou milestone integral
é encerrado.

O primeiro build Nexus herdou assets obsoletos de build/lib. A verificação
de bytes interrompeu ambos os runners antes de pytest. O rebuild em staging
limpo substituiu esse artefato; a tentativa fica preservada na evidência.
Os assets previamente modificados no workspace continuam presentes no
wheel técnico e não constituem aceite final de UI.

A [evidência coordenada](test_runs_20260930_capability_recovery.json)
identifica campanhas, artefatos e tentativas.
