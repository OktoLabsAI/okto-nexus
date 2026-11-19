# SI-025 Perguntas nativas do Pi

O ensaio abriu o Pi 0.87.1 com um único processo escritor em Windows e iniciou um turno pelo endpoint de mensagens da sessão. Uma extensão temporária fez três perguntas durante o turno. O primeiro visualizador, em Windows ConPTY, se desanexou enquanto a primeira pergunta estava pendente. O operador respondeu pela API canônica usada pelo painel e abriu outro visualizador para acompanhar a mesma sessão. O ensaio preservou o processo do Pi, o ID nativo e o histórico até o encerramento canônico.

O sino e a coluna Needs You referenciaram a mesma ocorrência para cada pergunta. A credencial do agente representado ficou sem acesso à pergunta dirigida ao operador. Uma revisão desatualizada e uma opção ausente foram recusadas. Repetir cada decisão devolveu o mesmo recibo e a mesma operação. A extensão do Pi confirmou a aplicação de cada resposta em sequência, incluindo escolha, negativa e texto. O valor textual permaneceu fora dos registros SQLite de decisões, operações, eventos, fila e despacho inspecionados.

O operador enviou a mensagem comum “Sim” durante a primeira pergunta. O item permaneceu na fila, sem operação nativa, durante as três perguntas. O próximo envio ocorreu após `agent_settled` do turno anterior. O histórico continha dois turnos em ordem, e ambos os visualizadores restauraram os modos do console ao sair.

Passaram 59 testes do Nexus para ingresso, escopo, concorrência, recibos e recuperação das decisões, além de 14 testes do Core para os diálogos do Pi. O Pi, a extensão, o banco SQLite, o dispatcher e os terminais eram reais. O modelo devolveu respostas sintéticas e o ensaio usou diretórios descartáveis. Os resultados HTTP cobrem a publicação para a Home e o sino. A interação em navegador, o Connector remoto e a campanha com provedor real ainda exigem qualificação.

A etapa acrescentou o cenário `--questions` ao roteiro existente e registrou evidências parciais em SI-T-B07, SI-T-C17 e SI-T-G01. O rollback consiste em reverter o commit de evidências. O ensaio dispensa migração e utiliza os pins anteriores do Nexus, Core e Connector. [Dados dos ensaios](si025-pi-native-questions.json)
