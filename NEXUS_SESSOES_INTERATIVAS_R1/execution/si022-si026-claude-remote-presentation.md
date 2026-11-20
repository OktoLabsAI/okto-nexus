# SI-022, SI-026 e SI-031 — Acompanhamento remoto do Claude

O Nexus CLI pode abrir a saída da sessão Claude exata que um Connector hospeda. O acesso exige autorização de operador e negociação de `nexus-claude-presentation-v1`. O leitor acompanha a saída pelo canal R4 existente. Ctrl+C encerra a apresentação e devolve o recibo. O processo e a concessão continuam com o Connector. As ações produtivas seguem pelos controles canônicos.

O teste com os três wheels instalados passou por HTTP, WebSocket, daemon e R4 com o terminal Claude simulado. Verificou recusas de escrita, credencial de agente, origem externa e geração divergente. O leitor silencioso expirou e outro leu o mesmo alvo sem admitir trabalho adicional. Os testes instalados passaram no Core (49), Connector (206) e Nexus (92), incluindo regressões de Pi e controles de sessão. Os schemas gerados, lock, pins e pacotes passaram nas verificações. [Resultados e hashes](si022-si026-claude-remote-presentation.json)

O Claude 2.1.328 real abriu uma sessão vazia no Connector com perfil descartável no Windows ConPTY. O primeiro leitor saiu durante o turno. O segundo exibiu o resultado da mesma sessão, com o mesmo processo. O encerramento canônico terminou o Claude e o SQLite passou no `quick_check`. O ensaio usou uma resposta simulada em loopback e zero chamadas a provedor externo.

Os primeiros ensaios expuseram a falta da capacidade negociada na configuração do daemon e a classificação incorreta do HTTP de loopback. As duas falhas foram corrigidas. Cada tentativa usou um projeto novo. Depois do setup, o roteiro reabriu o socket temporário e aguardou a revisão corrente da autorização antes de admitir a sessão.

O marco dispensa migração. A reversão coordenada restaura os commits do Nexus, Connector e Core junto com os pins anteriores. A qualificação em duas máquinas e a campanha com provedor real permanecem pendentes.
