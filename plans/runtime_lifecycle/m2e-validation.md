# M2e — Recuperação compartilhada no Connector

Data: 2026-10-16. Branches: Nexus `feature/v0.3.1`, Core `feature/v0.0.12`,
Connector `feature/v0.0.10`. Ambos os consumidores continuam fixados no Core
0.0.12. Este checkpoint não conclui M2, M3 ou o gate UI-A completo.

## Comportamento implementado

- O Connector usa o controlador de lançamento e a prova de contenção do Core.
  Uma conexão substituta precisa demonstrar autoridade atual antes de recuperar
  a intenção e antes de liberar os slots no journal e no ledger físico.
- Cancelar a negociação revoga essa autoridade, mas mantém a tarefa e seus
  recursos até a thread de recuperação terminar. Trabalho atrasado não pode
  liberar capacidade depois de perder o dono.
- A extensão negociada `nexus-launch-recovery-v1` distingue `NOT_STARTED` de
  `EXITED`. Exige intenção original, produtor cercado que nunca adquiriu spawn,
  sessão/operação/gerações correlacionadas, receipt FAILED e ausência de birth.
- O Nexus valida essa prova contra o histórico canônico, recusa contradições
  com execução nativa anterior, registra a sessão como FAILED/CLOSED e revoga
  suas leases/capabilities. Não fabrica um close bem-sucedido.
- O erro da abertura continua durável e monotônico. Uma mensagem inicial sem
  envio é resolvida a partir de prova do próprio Server; uma operação com efeito
  possível não é repetida. Mudanças de receipt durante o ciclo exigem nova
  fotografia consistente antes da prontidão.

Os bytes do contrato R4 base não foram reescritos: também validam registros
históricos duráveis. A extensão tem schema e hash próprios. Isso não é uma
exigência de interoperabilidade com versões anteriores.

## Pacotes e testes

| Pacote | Versão | SHA256 |
|---|---|---|
| Core | 0.0.12 | `5ab1f03165c5dcdb7e879a6c773f766a8a6b5cd479c529588f833d47096d13c8` |
| Connector | 0.0.10 | `fa3e82c9e2b2359c81f4a16e39f6e7ac4b547392a5a593c56cb14f4c02bf3abe` |
| Nexus | 0.3.1 | `aedb3a6e9356c3c50e1247c33acec339d77ef0512aad84116e34d8df8a317884` |

- Core: 95 testes instalados aprovados, com byte comparison da wheel, contrato,
  receipts, provas negativas e crashes Windows descartáveis.
- Connector: 103 testes instalados aprovados. Inclui cinco cortes reais de
  processo (intent, claim, container, spawn, birth), perda de autoridade,
  cancelamento da negociação, falha de publicação/ACK e isolamento de sessões.
- Nexus: 63 testes instalados aprovados, incluindo prova de abertura nunca
  iniciada, rejeição de evidências contraditórias, recuperação embedded e
  retenção do owner até o término dos workers. Total dos três pacotes: 261.
- Dependências dos três pacotes instalados no ambiente isolado: compatíveis.

Evidências locais: Core `build/process-launch-m2e-installed/`; Connector
`build/runtime-lifecycle-m2e-installed/`; Nexus
`build/runtime-lifecycle-m2e-installed/`. A campanha do Connector teve 103 casos
aprovados na primeira passagem, mas seu runner falhou no cleanup do cwd
temporário no Windows; o runner foi corrigido e a segunda passagem terminou com
103 aprovados e exit code zero. Não houve mudança de implementação por essa falha.

## Interface e instalação real

Ao retomar a UI, o servidor anterior não escutava mais na porta 8202. Não havia
processo Nexus identificado nem exceção de encerramento no final dos logs
consultados. Isso não demonstra que a reconciliação causou a parada. Foram
preservados logs e snapshot SQLite em `build/runtime-lifecycle-m2e-live/` antes
da instalação. Esses arquivos locais contêm dados do usuário e não são commitados.

Os três pacotes M2e foram instalados globalmente e conferidos byte a byte:
533 arquivos Nexus, 156 Core e 98 Connector. O Nexus foi iniciado na porta
8202, com geração embedded 66. No Meta-harness, o broadcast real recebeu três
ACKs; Pi e Claude responderam ao marcador e o Codex apresentou falha por quota
do provedor (`usageLimitExceeded`), confirmada no terminal. Todos ficaram
Online em Agents sem reparo manual. Ver `m2e-ui-broadcast.md`.

A inicialização HTTP demorou aproximadamente 2m20s. Um stack dump mostrou a
descoberta inicial esperando a identidade de build do Pi, com quatro workers
de leitura/hash. O lifespan HTTP aguarda essa descoberta. Essa dependência
será removida no checkpoint M3b, preservando a geração do owner, a ausência de
inventário fresco antes de sua publicação e a retenção dos workers no shutdown.

## Limites e próximo passo

Qualificação técnica deste checkpoint: Windows nativo com processos descartáveis.
Os testes do Connector não equivalem a uma campanha de providers em outro host.
Permanecem pendentes as demais fronteiras de crash, Linux/macOS, isolamento de
prontidão/publicação (M3), recuperação incremental (M4), roteiro diferencial com
Connector local separado (M5) e os gates de UI/carga finais.
