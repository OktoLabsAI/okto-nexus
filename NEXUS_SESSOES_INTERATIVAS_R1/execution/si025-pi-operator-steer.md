# Confirmação de reorientação no Pi hospedado

O Nexus oferece uma revisão explícita da reorientação no painel e em `session steer`. A revisão vincula o pedido ao início confirmado de uma execução na sessão local do Pi. A promoção conserva o ID da mensagem, usa a revisão da fila e retira a entrada da entrega normal. A autorização é revalidada antes do envio canônico. O Core confere a mesma referência antes da escrita e a vincula ao recibo recuperável. O protocolo R4 mantém o formato atual.

O ACK do Core indica envio. A evidência nativa da fila faz o recibo indicar espera pela fronteira. O consumo correlacionado muda o recibo para aplicada. A confirmação mantém a mesma execução quando cabe e a recusa de um alvo diferente preserva a entrada original. O painel mantém a referência para recuperar o recibo enquanto o resultado está pendente.

O ensaio instalado executou o Pi 0.87.1 real com duas respostas sintéticas no mesmo run, HTTP concorrente e dois visualizadores em Windows ConPTY. Um alvo incorreto recebeu 409 e preservou o item. Duas confirmações concorrentes e a repetição posterior devolveram a mesma operação. Houve uma submissão de turno e uma reorientação. O recibo passou de `awaiting_boundary` para `applied` depois do evento de consumo. Desanexar preservou o processo original, e o encerramento canônico restaurou o console. Reproduza com o ensaio de terminal e a opção `--steer`. [Dados do ensaio](si025-pi-operator-steer.json)

Passaram 83 testes do Core instalado, 61 do Connector com o novo Core, 43 do Nexus instalado, 55 no Nexus a partir do checkout e 417 do frontend em Node. As suítes Nexus cobrem cenários em comum. A migração 183 foi verificada separadamente sobre dados anteriores. Ela preserva controles existentes, a pausa, as entradas e as referências. A reversão coordenada restaura o banco pré-migração e os artefatos e pins anteriores com o serviço parado.

O cenário automatizado SI-T-C04 passou. A SI-025 segue em andamento. O teste de terminal comprova visualização e desanexação com a promoção pela API. A confirmação dentro do editor nativo, interrupção, aprovações, verificação no navegador e qualificação com provedor real continuam pendentes.
