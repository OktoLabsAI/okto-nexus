# HOME-033 — proposta de validação local

> **Atualização técnica A08:** a revisão encontrou falta da faixa Servidor na
> Home. Esse delta está sendo implementado e será empacotado/qualificado antes
> de qualquer execução. O candidato e wheel D4 descritos abaixo são antecedentes,
> sem autorização nem efeitos. Pasta, IDs, duas chamadas e orçamento proposto
> permanecem iguais; não haverá reinício de contabilidade ou nova campanha.

**Preparação inerte concluída; execução ainda não autorizada.** Candidato final `cbb2a45ba9cc99833b5af881abc8415c4c7d355c436d6e05e8cfab4288fdd6af`, wheel `7e1563622f4becb21cc62b6182cb4683c7546861256c355c16bb9aa78efa87ff`, interface `D4dmKnLh`. O candidato anterior permanece preservado, com a mesma pasta, IDs e limites. A tentativa de preparar sem consentimento foi recusada antes de efeitos; nenhum serviço ou chamada de modelo foi iniciado.

Proponho validar a Home com o Codex CLI na conta já usada pelo próprio CLI, em uma campanha temporária própria. Serão **no máximo duas chamadas produtivas**: o teste obrigatório de conexão e um pedido pequeno para ler um CSV sintético, calcular quantidade/soma decimal e escrever um relatório com hash verificável. Não haverá terceira chamada de continuação: após encerrar a sessão, verificaremos a recusa de continuar aquele contexto exato.

O limite proposto é **200 mil tokens observados**, com parada preventiva em 150 mil e reserva de 50 mil antes da segunda chamada. A medição pode chegar com atraso; portanto esse limite não é uma trava atômica de cobrança e pode haver ultrapassagem. Uso desconhecido ou incompleto impede nova chamada. Nenhum orçamento ou consentimento de campanhas anteriores será reutilizado.

A campanha usa a pasta `Temp/home-r1-local-codex-bc1d3f18e856`, porta local 62817 e IDs fixos. Criará dados sintéticos, um serviço de usuário temporário e sua tarefa de login, removida no encerramento. O login/configuração nativa existente pode influenciar modelo, MCPs e instruções; não prometemos isolamento dessas configurações nem leremos/coparemos arquivos de autenticação. A conta nativa pode manter seus próprios registros de sessão/cache.

Durante o pedido, observaremos a atividade e o resultado na Home. Se surgir uma pergunta ou permissão nativa real, será revisada pelo operador no alvo exato; não fabricaremos uma pergunta. Também alternaremos a apresentação nova/clássica enquanto o mesmo trabalho permanece ativo. Ramos que não ocorrerem serão registrados como não executados.

A limpeza contempla interrupção canônica do pedido exato quando necessária, parada normal, observação das identidades dos processos e, se indispensável, a força canônica do serviço próprio dentro da autorização já existente para paradas necessárias do Nexus. Dados e evidências ficam preservados. Não encerraremos a sessão do Windows, reiniciaremos o computador ou alteraremos serviços pessoais.

A preparação passou 27 testes offline e revisão independente. Isso não comprova execução real ou sucesso do modelo. A autorização futura será um recibo separado vinculado ao hash do candidato final, sem trocar pasta, IDs ou reiniciar reservas.
