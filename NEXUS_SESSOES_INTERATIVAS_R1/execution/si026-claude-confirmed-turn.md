# SI-026 — Confirmação do fim do turno no terminal Claude

O Core retém a notificação `Stop` até que o processo que recebeu o prompt entre em estado ocioso e o histórico nativo confirme o encerramento e o texto daquele resultado. Os dois comprovantes precisam ser posteriores à notificação. Uma nova notificação do mesmo turno pode substituir a anterior. A fila só avança quando o resultado confirmado está no journal.

No ensaio com o Claude real, outro hook barrou o primeiro encerramento. O recibo ficou em `SUBMITTED` durante o hook e durante a continuação. Após a segunda resposta, o processo ficou ocioso e o Core publicou apenas o texto final. O leitor saiu durante a execução e o processo manteve o mesmo UUID. Um segundo ensaio observou `StopFailure` depois de o processo ficar ocioso. A confirmação dessa falha usa um estado ocioso posterior à admissão do prompt e grava somente o código canônico. Os dois ensaios usaram o wheel instalado, modelo em loopback, ferramentas desabilitadas e processos temporários encerrados ao final. [Dados dos ensaios](si026-claude-confirmed-turn.json)

Na integração R4 com eventos sintéticos, uma entrega incerta permaneceu em `OUTCOME_UNKNOWN` enquanto faltava a confirmação nativa. Depois da confirmação, a mesma operação publicou `SUCCEEDED` com o valor sensível ocultado. Passaram 83 testes do Core, 83 do Connector e quatro do Nexus.

SI-026 continua em andamento. A admissão da sucessora no produto, o attach e os controles de turno ainda precisam de implementação e qualificação. Os ensaios cobrem Windows e o Claude Code 2.1.328. Eventos sem comprovante compatível permanecem pendentes. O marco dispensa migração. O rollback reverte os commits e restaura os wheels anteriores em conjunto.
