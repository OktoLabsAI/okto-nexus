# SI-017, SI-034 e SI-036 · Perda de acesso com a sessão aberta

Com o painel da Home aberto em uma sessão exata, o teste expirou o login na base descartável de operadores. A API devolveu HTTP 401 e o Chromium retirou a conversa e os controles da sessão. Em novo login, o teste desativou a identidade interna de operador e conservou o cookie válido. A API devolveu HTTP 403 e o painel retirou o mesmo conteúdo protegido. A interface reagiu às respostas reais do servidor.

Após restaurar a identidade, reabri o endereço da mesma sessão e confirmei o acesso ao histórico. Os hashes das linhas de eventos, resultados, operações e entradas de fila ficaram idênticos durante o ensaio. Passaram 20 testes de autoridade do operador, stream e persistência da fila com o wheel do Nexus instalado em diretório temporário.

O teste de 401/403 usou uma cópia descartável com conversa retida e sem permissão de escrita na sessão. A evidência anterior de logout já cobre remoção do editor e dos controles com escrita habilitada, preservação da mensagem enfileirada e conclusão dos turnos Pi em execução. [Ensaio de logout](si036-browser-session-isolation.md)

A primeira tentativa precisou esperar a abertura do painel de métricas. O ensaio também passou a fechar o painel da sessão pelos controles da Home antes de navegar de volta, respeitando a confirmação de saída. A versão final confirmou os três caminhos de SI-T-E15 com as evidências combinadas.

Esta etapa registra evidências. A reversão do commit restaura o ledger anterior e dispensa migração. [Resultados e hashes](si036-browser-authorization-loss.json)
