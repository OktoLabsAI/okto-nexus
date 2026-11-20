# SI-026 · Reanexação ao terminal Claude após descarte de saída

Um leitor novo começava pela sequência inicial, mesmo quando o buffer do Core já a havia descartado. O wheel anterior recusou a reanexação ao terminal gerenciado depois que a fixture preencheu o buffer. A execução original chegou ao resultado.

O Core agora filtra controles de terminal e mascara segredos na origem, antes de guardar o texto no buffer de 512 KiB. Um novo leitor começa no primeiro quadro seguro disponível e mostra um aviso quando a saída anterior foi descartada. O cursor de um leitor já conectado pode expirar se ele ficar para trás. Se a filtragem exceder seu limite, o Core desativa a apresentação e continua drenando a saída do processo.

Os ensaios usaram Claude Code 2.1.328 real, o CLI instalado em ConPTY e um modelo simulado em loopback. Depois de verificar o UUID salvo, o Nexus abriu o terminal gerenciado e iniciou um turno. Durante a espera pela resposta, Ctrl+C saiu com código zero e restaurou os modos do console. Um segundo leitor foi encerrado abruptamente. Nenhuma saída de leitor escreveu no terminal do Claude ou fechou seu canal. O mesmo processo publicou o resultado do turno original.

A fixture injetou linhas no buffer do processo enquanto ele não tinha leitores, no ponto em que o Core recebe a saída do ConPTY. O terceiro leitor exibiu o aviso e o resultado real produzido após liberar a resposta. O encerramento canônico fechou a sessão e o Job Object ficou sem processos. O SQLite passou nas verificações de integridade. Os testes de regressão também cobriram segredos e comandos de terminal partidos entre quadros descartados, UTF-8, expiração de cursor e falha de filtragem. [Dados e hashes](si026-claude-terminal-retained-output.json)

Passaram 46 testes focados do Core com o código-fonte e com o wheel instalado, 33 do Connector e 12 do Nexus. Uma execução anterior do teste de autenticação do hook perdeu a conexão local. O teste passou isoladamente no wheel anterior e nas duas execuções finais com o novo Core.

A prova de detach do Claude cobre a sessão retomada em terminal gerenciado no Windows. O processo stream-json original continua sem apresentação ao vivo qualificada. O cenário SI-T-G03 conserva a qualificação pendente. Para rollback, restaure o wheel anterior do Core nos dois consumidores. A alteração dispensa migração de banco e preserva os protocolos.
