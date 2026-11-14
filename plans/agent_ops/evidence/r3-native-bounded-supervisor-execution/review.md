# Supervisão limitada: campanha Windows instalada

SVC-T19 foi verificado nos dois hosts com falha injetada de código 3. Cada host
executou a tentativa inicial e três reposições automáticas, mantendo o mesmo
supervisor e ciclo. Os intervalos observados respeitaram o backoff de 60 segundos
com tolerância de medição de 1 segundo. Depois do quarto crash, o diagnóstico
canônico informou esgotamento e orientou a ação do operador. A janela adicional
de 190 segundos não observou uma quinta tentativa.

A parada saudável anterior aos crashes concluiu drain e confirmou a saída física
de runtime, launcher e supervisor. Ambos permaneceram parados por 190 segundos.
No Nexus, o próximo connect iniciou o serviço, mas retornou NOT_FOUND para o setup.
No Connector, connect sem identidade recusou sem iniciar; um start explícito
separado estabeleceu o runtime para o teste de crash. Por isso SVC-T20 permanece
IN_PROGRESS: connect configurado bem-sucedido não foi exercitado. Parada real
durante backoff também não é reivindicada.

Após esgotamento, a parada preservou shutdown_outcome=unconfirmed,
supervision_scope=supervisor_only e runtime_work_settlement=not_asserted.
As duas tarefas foram removidas canonicamente e os fingerprints dos dados
permaneceram iguais. Nenhum provedor, login, modelo ou trabalho ativo foi usado.

Qualificação anterior: 81 testes instalados passaram, com dois casos que criam
processos benignos excluídos; 53 fixtures finais do runner passaram. O erro inicial
de coleta por fixture auxiliar ausente e os resultados anteriores foram retidos.
A primeira campanha sem recuperação nativa e a matriz do Scheduler permanecem
como histórico separado, sem reclassificação retroativa.

As medições de backoff usam FILETIME e relógio de parede, com comparação de drift
contra o relógio monotônico nas extremidades. Ajustes de relógio que se cancelam
não são detectados. Não se generaliza o resultado para qualquer NTSTATUS.

Evidências exatas e hashes: [review.json](review.json) e
[artifact-manifest.json](artifact-manifest.json).
