# SI-023 · Trabalho em segundo plano durante retomada

No Windows, o Codex 0.157.0 chamou uma ferramenta MCP que iniciou um processo de leitura separado. A ferramenta devolveu o controle ao modelo e o turno terminou. O processo em segundo plano continuou aguardando o marcador de teste.

O CLI e a API autenticada responderam HTTP 409 à tentativa de retomar o histórico da mesma sessão. A resposta orientou o uso de anexação ao vivo, quando disponível, para manter o trabalho no executor atual. O Nexus não gravou nova operação nem prova de encerramento. O app-server manteve a mesma thread. O mesmo processo em segundo plano, observado pelo handle do Windows, concluiu uma vez após a liberação do marcador. O teste confirmou a saída do app-server depois do fechamento canônico.

Em outro ensaio, o Nexus recusou a retomada de uma sessão ainda ativa no Connector e retornou a mesma orientação. Uma geração obsoleta recebeu uma recusa genérica. O histórico exato pôde ser retomado uma única vez após fechamento canônico, nova confirmação do operador e verificação do contexto. O Connector manteve o caminho autenticado de saída via WSS.

Passaram 58 regressões com os wheels instalados, além dos ensaios nativos local e pelo Connector. As primeiras tentativas locais expuseram dois problemas na instrumentação. O teste passou a aguardar o evento de prontidão do MCP e a iniciar o subprocesso com o executável-base do Python para correlacionar o PID real no Windows. As repetições usaram ambientes descartáveis e modelo sintético em loopback. [Resultados e hashes](si023-codex-independent-background.json) · [Ferramenta de teste](fixtures/si035_codex_background_gate.py)

O ensaio com processo em segundo plano ocorreu no executor local. O caso do Connector exercitou a recusa com uma sessão ativa, em loopback na mesma máquina. SI-T-G14 conserva a qualificação pendente para campanhas e outras plataformas. A alteração dispensa migração e pode ser revertida voltando ao wheel anterior do Nexus.
