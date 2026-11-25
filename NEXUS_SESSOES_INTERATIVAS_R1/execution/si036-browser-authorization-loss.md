# SI-017, SI-034 e SI-036 · Perda de acesso com a sessão aberta

Com o painel da Home aberto em uma sessão exata, o teste expirou o login na base descartável de operadores. A API devolveu HTTP 401 e o Chromium retirou a conversa e os controles da sessão. Em novo login, o teste desativou a identidade interna de operador e conservou o cookie válido. A API devolveu HTTP 403 e o painel retirou o mesmo conteúdo protegido. A interface reagiu às respostas reais do servidor.

Após restaurar a identidade, reabri o endereço da mesma sessão e confirmei o acesso ao histórico. Os hashes das linhas de eventos, resultados, operações e entradas de fila ficaram idênticos durante o ensaio. Passaram 20 testes de autoridade do operador, stream e persistência da fila com o wheel do Nexus instalado em diretório temporário.

O teste de 401/403 usou uma cópia descartável com conversa retida e sem permissão de escrita na sessão. A evidência anterior de logout já cobre remoção do editor e dos controles com escrita habilitada, preservação da mensagem enfileirada e conclusão dos turnos Pi em execução. [Ensaio de logout](si036-browser-session-isolation.md)

A primeira tentativa precisou esperar a abertura do painel de métricas. O ensaio também passou a fechar o painel da sessão pelos controles da Home antes de navegar de volta, respeitando a confirmação de saída. A versão final confirmou os três caminhos de SI-T-E15 com as evidências combinadas.

Esta etapa registra evidências. A reversão do commit restaura o ledger anterior e dispensa migração. [Resultados e hashes](si036-browser-authorization-loss.json)

## Revogação com uma resposta nativa aberta

No Edge com o dashboard do Nexus 0.3.8 instalado, o operador preencheu uma resposta personalizada para uma pergunta nativa. Depois que o servidor revogou o login, a tentativa de enviar recebeu HTTP 401. O navegador voltou à tela de entrada e retirou o formulário. A resposta ficou fora do armazenamento do navegador, e as tabelas de pedidos, aprovações, decisões e operações permaneceram iguais.

Passaram os 15 testes de decisão canônica e, em rodada focal, o cenário com comparação integral das linhas antes e depois da revogação. A suíte usou o backend real e fixtures de pedidos nativos, sem chamadas a provedores. O ensaio opt-in de diagnóstico legado parou na preparação. O teste esperava a antiga navegação e, após alinhar a fixture, a antiga abertura respondeu HTTP 409. As mudanças exploratórias ficaram fora do commit. A regressão entregue usa a decisão canônica e revoga o cookie no servidor. [Resultados e hashes](si036-browser-authorization-loss.json)

O marco acrescenta um cenário de regressão e suas evidências. A reversão é pelo commit. O aceite do participante e a validação de fala com leitor de tela no Windows continuam pendentes.
