# Estado do Pi no dono R4

O runtime embutido do Nexus pode consultar o estado da sessão Pi 0.87.1 associada ao recibo de abertura. A consulta usa `get_state` no transporte RPC existente, com resposta correlacionada por ID e espera de até cinco segundos. O Core verifica o dono e sua concessão R4 antes e depois da leitura. O Nexus confirma que a composição e o mapeamento continuam atuais.

A leitura interna retorna apenas ID nativo, atividade de streaming, compactação e contagem de mensagens pendentes. O retorno exclui histórico, configuração de modelo e caminho do arquivo. Outro ID, um processo encerrado, uma geração obsoleta ou um build sem a capacidade de leitura resultam em recusa. A consulta reaproveita o runtime em memória e não abre sessão, inicia turno nem estende a concessão.

O ensaio em Windows usou o Pi instalado, o renderer do SDK em um terminal de captura e uma resposta sintética local. O `EmbeddedRuntimeHost` consultou o mesmo ID enquanto o renderer estava aberto, desanexado e reaberto. Depois de `agent_settled`, a leitura mostrou o fim do streaming. O ensaio também verificou a recusa de outro ID e a recusa após o fechamento canônico. A mesma operação continuou produzindo um único prompt e o ensaio observou zero tentativas de rede. [Resultados, artefatos e regressões](si025-pi-owned-state.json)

Passaram 39 testes do Core, 103 do Connector e 34 do Nexus com os wheels instalados. As suítes do Core e do Nexus também passaram a partir do código-fonte. Os módulos alterados mantêm os apontamentos preexistentes do Ruff registrados na evidência.

Para reproduzir, use o comando do ensaio Pi com `--core` e disponibilize Nexus 0.3.8 e o pin Core 0.0.16 desta etapa no interpretador. O roteiro injeta a composição embutida de teste e registra uma concessão temporária. [Comando base](si025-pi-shared-owner.md)

A alteração é interna e não precisa de migração. A reversão coordenada dos três commits restaura os pins anteriores. A SI-025 continua em andamento. O próximo passo é vincular o renderer ao canal autenticado do operador, mantendo o dono único e qualificando entrada, fila, extensões e detach no terminal real.
