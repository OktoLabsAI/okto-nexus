# Bloqueio de WebSocket de origem externa no Nexus

O ensaio SI-T-H06 usou o Nexus 0.3.8 instalado e o Edge no Windows. O navegador autenticou o operador descartável no endpoint real de login. Em outra origem HTTPS, servida em uma porta distinta do mesmo host de loopback, o navegador iniciou um WebSocket para a rota de apresentação remota do Codex. O Nexus recebeu o cookie válido do operador. O navegador recebeu a recusa antes da abertura e nenhum frame de apresentação. [Resultados e hashes](si034-browser-websocket-origin.json)

Um cliente de protocolo em WSS isolou a verificação de origem com o mesmo cookie e um ticket legítimo. Tanto a origem incorreta quanto a origem ausente receberam HTTP 403 antes do upgrade. A mesma oferta permaneceu `PREPARED`. Com a origem correta, o cliente concluiu o desafio, leu o contexto da sessão exata e se desconectou. Na API HTTP, a revisão de anexação também recebeu 403 com origem incorreta ou sem o cabeçalho de proteção CSRF.

O SQLite confirmou um único anexo em `DETACHED`, os hashes de ticket e desafio removidos, zero entradas de fila e zero operações de trabalho. O primeiro ensaio observou as recusas, mas excedeu o tempo de encerramento do servidor TLS da fixture. O ensaio final aguardou o fechamento do Edge, encerrou os listeners e removeu a chave TLS descartável. A confiança no certificado ficou restrita aos clientes do teste.

Passaram a integração com Edge e seis regressões instaladas. O catálogo e o contexto nativo foram fornecidos pela fixture. A verificação cobre a rota de apresentação remota do Codex sobre WSS em loopback. Este marco atualiza apenas a evidência e o ledger. O rollback consiste em reverter o commit.
