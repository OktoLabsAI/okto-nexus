# SI-025 / SI-030 / SI-031 / SI-037 · Editor do Pi no CLI Linux

`session attach --write` usa o terminal Linux para o editor do Pi. O CLI lê UTF-8 no modo bruto enquanto o editor está aberto e restaura os atributos do terminal ao sair. O rascunho, o recibo, o escritor exclusivo e a recuperação da mesma intenção usam o fluxo de sessão existente. [Comandos](../../docs/terminal-work.md#native-pi-viewer)

O ensaio executou o comando em um pseudoterminal no Ubuntu 24.04.5 em WSL2 com os wheels instalados. O comando selecionou o servidor, a revisão do vínculo e a sessão exata de um Connector real por R4. A colagem dividiu um caractere UTF-8 entre leituras e continha Ctrl+C. O caractere apareceu no rascunho e a fila permaneceu vazia. Enter registrou uma única entrada e mostrou o recibo. Ctrl+] fechou o editor e restaurou o terminal. Depois do detach, o Pi 0.87.1 concluiu o primeiro turno e recebeu a mensagem da fila. Um leitor reaberto encontrou a segunda resposta na mesma sessão. O fechamento canônico encerrou o processo. O ensaio substituiu o cofre do operador por uma fixture e usou respostas simuladas em loopback, sem chamadas externas. [Dados do ensaio](si037-linux-pi-cli-editor.json)

Passaram 61 testes de CLI no Linux e 61 no Windows com o wheel instalado, além do ensaio integrado. Cada ambiente pulou um teste específico do outro sistema. O caso de pseudoterminal confirmou a restauração após uma falha durante a apresentação. `pip check` e `twine check` passaram. A distribuição descartável do WSL e seu disco foram removidos.

O marco qualifica a digitação, a colagem, a fila e o detach no pseudoterminal exercitado. Continuam pendentes as provas em outro host físico, macOS, a campanha com provedores e a aceitação humana. Os ensaios seguintes exercitam reorientação, interrupção e retomada salva no Connector. [Controles do turno](si037-linux-pi-exact-controls.md) · [Retomada salva](si037-linux-pi-saved-resume.md)

O marco dispensa migração e pode ser revertido pelo commit do Nexus. A próxima etapa local é testar a reorientação e a interrupção no Pi Linux com revisão de execução e recibo canônico.
