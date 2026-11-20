# Desligamento com trabalho admitido e agendador ocupado

O teste de integração esperava que o prazo da solicitação HTTP de desligamento encerrasse o harness. O desligamento cooperativo preserva o trabalho admitido. Ao vencer o prazo, a resposta oferece a opção de parada explícita e continua aguardando os componentes que ainda precisam do armazenamento.

- No ensaio cooperativo, o harness de teste concluiu o turno original. O serviço manteve o armazenamento disponível enquanto o agendador ainda estava ocupado. Ao liberar o agendador, o serviço concluiu o desligamento.
- No ensaio com parada explícita, o coordenador interno preservou o prazo original e encerrou o harness de teste. O armazenamento permaneceu disponível até a liberação do agendador. Nos dois ensaios houve uma única admissão de turno.

Passaram 28 testes de ciclo de vida e decisão de desligamento com os wheels instalados. O teste usa um harness simulado e chama a parada explícita somente dentro da aplicação descartável. A alteração se restringe à cobertura de regressão, dispensa migração e pode ser revertida pelo commit do teste. A qualificação de processos e plataformas mantém seus gates. [Dados do ensaio](si037-retained-handoff-shutdown.json)
