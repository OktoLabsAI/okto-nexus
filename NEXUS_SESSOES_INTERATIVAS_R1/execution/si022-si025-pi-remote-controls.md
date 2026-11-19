# SI-022 e SI-025 — controles da execução do Pi via Connector

O editor da sessão do Pi aceita Ctrl+R para revisar uma reorientação no próximo ponto de processamento e Ctrl+X para revisar uma interrupção. Cada revisão exige confirmação do operador. O Nexus confere a execução ativa, o evento de início, a sessão, a geração e a conexão atual antes do envio. A interrupção registrada pausa a fila da sessão.

O Nexus e o Connector negociam `nexus-pi-run-control-v1` para carregar a referência exata junto da operação R4 existente. O Nexus recusa um controle humano revisado se a conexão não tiver essa capacidade. O Connector valida a origem, a geração e a reserva da fila. O Core registra a referência no vínculo do recibo e confere a execução no processo nativo antes do efeito. O contrato R4 existente passou na verificação de geração.

Dois cenários passaram com o Pi 0.87.1 em Windows ConPTY, por meio do Connector e do servidor Nexus em loopback. A reorientação aplicou um único rascunho na execução original e retornou o evento nativo de consumo. A interrupção encerrou o trabalho selecionado, pausou a fila e conservou o mesmo processo e a mesma sessão após o detach. Ambos os cenários usaram respostas sintéticas em processos com rede bloqueada e terminaram pelo fechamento canônico da sessão temporária. [Resultados e hashes](si022-si025-pi-remote-controls.json)

A migração de banco é dispensável. O rollback usa os commits anteriores do Nexus, do Connector e do Core e repõe seus pins em conjunto. A validação em máquinas distintas e a qualificação restante dos fluxos remotos continuam no ledger. O próximo marco estende ao Pi a oferta de abrir a sessão após a conexão.
