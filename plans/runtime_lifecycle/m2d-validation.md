# M2d — Recuperação local das intenções de startup

2026-10-16. Checkpoint técnico; M2 e o gate UI-A completo continuam abertos.

O Nexus usa a recuperação compartilhada do Core M2c antes de exigir um birth
record. A geração atual cerca o produtor antigo, comprova o encerramento do
container e só então libera a capacidade. Um produtor nunca acionado tem sua
abertura encerrada como FAILED, com publicação durável antes da liberação. O
receipt preserva qualquer marca de efeito possível; nenhum comando é repetido.
Registros antigos sem prova suficiente continuam incertos.

O teste revelou uma fronteira adicional: a intenção pode estar gravada antes de
existir uma reserva física. Exigir essa reserva para iniciar a recuperação
deixava a abertura presa. O caminho agora cerca e encerra essa intenção mesmo
sem slot, usando a prova NEVER_CLAIMED. A ausência de um slot ou birth, sozinha,
continua insuficiente. A sessão é marcada FAILED, sem inventar um processo
executado/encerrado, e a mesma configuração aceita novas chamadas.

## Evidências

**24 cenários distintos aprovados** contra a mesma wheel candidata, com
dependências válidas. Resultados e hashes em [m2d-results.json](m2d-results.json).

- Seis processos Nexus descartáveis interrompidos com `os._exit(17)`: após a
  intenção, após a marca de efeito, após o claim de spawn, após criar o Job,
  após criar o filho e após persistir o birth. Cada reinício converge sem API de
  retry/reparo, mantém uma única tentativa original, libera os slots comprovados
  e aceita uma nova chamada no agente original.
- Regressões de contenção, confirmação manual para histórico sem prova,
  isolamento de agente travado/histórico indisponível, criação de agentes locais
  e remotos sintéticos durante recovery, publicação lenta e resposta parcial.
- Publicação lenta mantém native/lease para Pi, Claude e Codex sintéticos.
- Regressões de encerramento normal, kill do owner e kill antes do binding
  recuperam sem apagar locks/leases e sem replay.

A primeira candidata falhou antes do slot (1 falha/9 aprovados). Após a correção,
a campanha ampliada teve 23 aprovados/1 falha: o teste de confirmação manual
exigia READY na resposta imediata, embora o worker retido ainda estivesse
concluindo. Os registros mostraram a convergência automática. O teste passou a
aceitar a resposta transitória RECOVERING e exigir conclusão observada em até
20 s, sem outra ação de reparo; seu arquivo foi reexecutado com **4 aprovados**.
Os demais 20 cenários não mudaram. Nenhum input mudou durante as campanhas.

O runner verificou os bytes instalados e executou pytest isolado. Os seis novos
subprocessos herdam os caminhos instalados com `-I`. Limitação dos testes antigos:
os três helpers de crash da regressão de isolamento ainda importam o checkout
correspondente no subprocesso; não são evidência de empacotamento desse filho.

## Pacotes e limites

- Nexus 0.3.1: `0a178bdc76651d0bc0ea562b95b4520ebb78170907765a8db458d96ad6756603`.
- Core 0.0.12 / commit `877393b`:
  `5042ca20a0fa9389f8749f5208701790e0f0d672f42bdb72334f05fe25375cf5`.
- Vendor do Core e manifesto de CI atualizados no Nexus. Connector permanece
  no checkpoint M1; sua recuperação ainda precisa receber a integração.

Windows AMD64/Python 3.13.1; peers sintéticos e processos nativos descartáveis.
Não houve teste de provedor real com esta candidata, qualificação Linux/macOS
ou atualização da instalação global. Ela continua M3a Nexus/M1 Core; a evidência
real de Meta-harness está em [m3a-ui-broadcast.md](m3a-ui-broadcast.md).

Próximo passo: integrar o Connector com a mesma prova e publicação sob autoridade
atual, inclusive a abertura nunca iniciada, preservando a monotonicidade dos
receipts. Depois qualificar as demais fronteiras e executar o gate real pela UI.
