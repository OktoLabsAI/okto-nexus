# SI-T-H15 — Sequências de controle na saída do harness

O Nexus empacotado abriu uma sessão Pi 0.87.1 no Windows e admitiu um turno por HTTPS. Um provedor determinístico local entregou texto com sequências OSC de área de transferência, link e título, uma consulta de posição de cursor e uma marca HTML. A resposta integral foi confirmada no histórico nativo. [Resultados, versões e hashes](si034-inert-terminal-output.json)

- **Terminal:** o visualizador em Windows ConPTY mostrou o começo e o fim da resposta. Os quadros WSS já chegavam sem as sequências de controle testadas. O contador da área de transferência não mudou. Ctrl+C desanexou a leitura e restaurou a configuração do console.
- **Navegador:** o Edge autenticado acompanhou a conversa exata via SSE e abriu a atividade técnica. A conversa exibiu a marca HTML como texto. A atividade técnica removeu os escapes e conservou os marcadores de início e fim. Nenhuma das duas superfícies ativou o link, interpretou a marca HTML como elemento, alterou o título, chamou a área de transferência ou enviou uma mutação de sessão.
- **Estado:** o SQLite registrou uma abertura, um turno e um fechamento, com um resultado e zero entradas de interação. O encerramento canônico terminou o Pi. O listener foi encerrado e a chave TLS temporária removida.

Passaram dois ensaios com o produto instalado, quatro regressões do renderer e 20 testes de componentes. A primeira tentativa parou na preparação porque o helper do provedor esperava quatro sinais. Com a fixture ajustada, nenhuma modificação de produto foi necessária. Os testes de componentes mantiveram os avisos conhecidos sobre `useLayoutEffect` na renderização no servidor.

A qualificação cobre Pi, Windows e transporte em loopback. A inspeção da área de transferência observou apenas o contador do Windows e as chamadas da página, sem ler nem escrever o conteúdo. O certificado temporário foi confiado pelo cliente de terminal e o Edge usou uma exceção restrita ao perfil descartável. A reversão deste commit remove apenas evidências e dispensa migração.
