# Reorientação no editor nativo do Pi

Ctrl+R revisa o rascunho e a execução atual no mesmo Pi. Ctrl+Y confirma e Ctrl+N cancela. Enter continua registrando mensagens para o próximo turno. A revisão lê o rascunho pelo canal privado do renderer. O Nexus confirma sob a autoridade do operador e com a revisão exata da fila. O editor conserva a mensagem enquanto aguarda o recibo e a limpa só quando o journal comprova que o Pi a consumiu.

O ensaio com Pi 0.87.1 real em Windows ConPTY verificou cancelamento, Enter durante a revisão, recusa após mudança na fila e confirmação válida do mesmo rascunho. O recibo autenticado do terminal mudou de `awaiting_boundary` para `applied`. Houve uma reorientação e uma submissão de turno. Um Enter após a aplicação manteve a contagem. Outro ensaio confirmou que Enter fora da revisão continua enfileirando a continuação e só a envia após o término da execução ativa. Os dois ensaios usaram respostas sintéticas, o mesmo processo Pi após desanexar e o encerramento canônico. [Dados dos ensaios](si025-pi-native-steer.json)

Para reproduzir, use `si025-pi-terminal-e2e.py --steer-editor` com os parâmetros para o executável Node, o Pi e os auxiliares ConPTY. A regressão de Enter usa `--queue --queue-surface editor`. A etapa dispensa migração. A reversão restaura os pins anteriores no Nexus e no Connector e reverte a alteração do Core.

A rodada com os pacotes instalados passou com 79 testes do Core, 61 do Connector e 72 do Nexus. Os testes de transporte cobrem resposta perdida depois da confirmação e recuperação pela intenção original.

A SI-025 segue em andamento. A evidência controlada complementa SI-T-C04 e SI-T-G18. Interrupção pela execução exata, aprovações e qualificação em campanha continuam pendentes.
