# M02/M03 — prova delegada de operador

Este incremento permite que o agente prepare uma proposta e o operador
canônico a autorize pela fila existente de aprovações. A prova permanece
vinculada à proposta, revisão, diff, sujeito e identidade corrente do operador.
O agente transporta a referência opaca no apply. Consentimento e grant de
runtime continuam separados.

## Implementação

- Migração aditiva 077: prova persistida na proposta.
- Decisão, prova, resultado e evento confirmados na mesma transação.
- Rejeição de autoaprovação, decider forjado, prova cruzada, expiração,
  alteração de política e rotação de chave.
- Replay consulta o resultado anterior; falha de storage reverte decisão
  e prova. Rejeitar proposta vencida continua permitido.
- Bootstrap básico preserva Core opcional; os imports R4 são tardios.
- Connector 40a8cb0 já publica os campos de consentimento completos e
  transporta operator_proof_ref.

O [ADR 0004](../../docs/adr/0004-binding-operator-proofs.md) registra a decisão.

## Evidência revisada

O [registro de execução](test_runs_20260930_delegated_binding.json) contém
comandos, hashes de fonte/artefatos e as tentativas anteriores com falha.

| Campanha | Resultado |
|---|---|
| Nexus R4 após correções | 86 passed |
| Regressões de aprovação existentes | 48 passed |
| Migrações | 7 passed |
| Nexus/Connector instalados fora dos clones | 27 passed |
| Connector DTO | 6 passed |
| Connector regressão anterior | 246 passed, 1 failed, 2 skipped |
| Connector pacote após correção de isolamento | 2 passed |

A revisão atual conferiu que a fonte e os XMLs continuam iguais aos hashes
registrados; não conta essa revisão como nova execução. Casos se sobrepõem.
O manifesto instalado compara os arquivos dos pacotes com os wheels exatos.
Core permanece 0.2.28.dev0, SHA-256
27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c.

As falhas anteriores foram preservadas: expectativa de HTTP 500 onde o
storage retorna 503 DB_ERROR; caller vertical sem prova de operador; teste
de pacote Connector contaminado por PYTHONPATH. As correções têm reruns
dirigidos registrados; não anunciar regressão Connector completa reexecutada.

## Limites e próxima integração

Inventário/peers são sintéticos. Este incremento não prova provider, UI,
daemon, hosts distintos ou aplicação de approval/input nativos.
Reuso autorizado de configuração existente, abertura com lease inicial,
outbox/owners e campanhas finais seguem obrigatórios. M02/M03 e G0–G3
permanecem abertos. O commit que contém este relatório publica o incremento
Nexus; o snapshot de planejamento anterior conserva seu estado histórico.
