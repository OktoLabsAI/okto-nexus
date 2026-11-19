# SI-022 e SI-025 — Transporte do renderizador Pi no Connector

O Core validou um protocolo adicional para consultar, abrir, ler, editar o rascunho e desanexar o renderizador de uma sessão Pi existente. Cada resposta se vincula ao pedido e à conexão R4 negociada. A leitura sob demanda mantém um único bloco de saída pendente por visualizador. Os comandos de edição são restritos às teclas do editor e usam uma sequência própria por visualizador. O envio produtivo permanece na fila do Nexus.

O Connector consulta a sessão sob a autorização R4 corrente. O renderizador só é composto em uma abertura Pi que negociou a capacidade e corresponde ao pacote Windows revisado. Repetição ou cancelamento de edição, perda de autorização, expiração de inatividade e perda da conexão encerram ou recusam o visualizador conforme o caso. Desanexar libera o renderizador da sessão existente.

Passaram 14 testes do Core e 121 do Connector com os pacotes instalados. O teste de contrato usou o leitor R4 real com um socket e um renderizador simulados. Verificou negociação, vínculo da resposta, bloqueio de um segundo visualizador para a mesma sessão, leitura sob demanda, recusa de edição em leitura e recusa de repetição após cancelamento. Os quatro testes instalados do Codex remoto passaram com o Nexus anterior, que ainda não negocia o Pi. Os artefatos passaram pelo Twine e os contratos gerados permaneceram compatíveis.

Os pins de teste do Nexus agora apontam para esses wheels. A mudança usa contratos adicionais e dispensa migração. Para reverter, use `git revert` nos três repositórios e restaure os pins anteriores.

SI-022 e SI-025 continuam em andamento. O próximo passo é ligar o transporte ao broker e ao CLI do Nexus e repetir leitura, escrita e detach com o Pi real. Ainda faltam a validação entre máquinas e os cenários completos de desempenho e perda física de rede. [Dados dos testes e artefatos](si022-pi-connector-transport.json)
