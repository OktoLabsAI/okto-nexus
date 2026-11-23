# SI-037 · Processo Pi e recibo de encerramento no Linux

O ensaio instalou Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 em Ubuntu 24.04.5 x64 descartável no WSL2. O preflight do Core confirmou procfs, enumeração de filhos, pidfd e subreaper. Os artefatos da distribuição e do Node 24.15.0 foram conferidos contra os hashes oficiais. [Imagem Ubuntu](https://cdimage.ubuntu.com/ubuntu-base/releases/noble/release/) [Node 24.15.0](https://nodejs.org/en/blog/release/v24.15.0) [Versões e hashes instalados](si037-linux-owned-pi.json)

O adaptador RPC abriu o Pi 0.87.1 sob o guardião do Core. O teste fechou a assinatura de eventos enquanto a resposta simulada estava retida. O mesmo processo concluiu o turno sem assinantes e o histórico nativo preservou um pedido e uma resposta. O encerramento usou a parada forçada da árvore de teste e a leitura posterior do recibo recuperou `STOPPED`. O executor rodou como usuário sem privilégios em um namespace com apenas a interface de loopback.

Passaram 34 testes de processos e descoberta do Core, seis testes de ciclo do Connector e 30 testes de transcrição e transporte do Nexus. Na preparação, o teste do Pi precisou permitir a leitura de dois caminhos de busca de recursos dentro da distribuição descartável. A conferência do resultado usa o evento nativo `agent_settled` e o histórico retido. [Resultados e hashes](si037-linux-owned-pi.json)

O modo hospedado do Pi continua indisponível nesta instalação Linux. O seletor do Nexus, a qualificação do Core e o próprio arquivo do renderer recusaram a combinação. O ensaio de RPC foi direto, sem attach pelo produto. SI-T-H01 continua pendente porque exige um Connector em outra máquina.

A distribuição de teste e seu disco foram removidos após as verificações. O marco atualiza evidências e dispensa migração. O rollback consiste em reverter o commit.
