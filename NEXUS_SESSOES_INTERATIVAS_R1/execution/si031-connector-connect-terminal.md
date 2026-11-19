# SI-031 — Abrir o Codex pelo connect do Connector

O Connector oferece o visualizador após confirmar a conexão. `-i` pede abertura no terminal atual. Sem flag, o padrão da pergunta é Não. `--no-interactive` após `connect` pula a oferta, preservando as revisões do setup. O modo global do Connector e o comando de automação já existente mantêm seu contrato.

O processo Nexus usa seu próprio login humano salvo. Ele confere o servidor, o host, o workspace e a revisão do vínculo antes de consultar sessões. A seleção usa o catálogo autorizado existente. O resultado da abertura retorna em um arquivo temporário sem segredos e o Connector o valida contra o vínculo. Uma falha na apresentação preserva o recibo da conexão confirmada e o comando para abrir depois.

Os pacotes instalados passaram 76 testes do Connector e 30 testes do Nexus. O ensaio em Windows ConPTY usou os dois executáveis instalados, o daemon Connector, um app-server Codex 0.157.0, o frontend Codex 0.170.0 e o Nexus por loopback. Retomou o setup confirmado, pulou a oferta sob `--no-interactive`, e abriu a mesma sessão sob `-i`. O resultado apareceu no terminal e Ctrl+] desanexou a leitura. Os testes usaram um perfil de operador temporário e um cofre simulado para o token desse ensaio. A única resposta de modelo foi simulada em loopback.

A primeira execução completou as interações e expirou na espera pelo encerramento do servidor de teste. A repetição passou depois do encerramento canônico da sessão temporária e de uma janela maior para observar a saída do servidor. O encerramento ocorreu só depois de verificar que abrir e desanexar não admitiram trabalho.

O Core 0.0.16 segue o pin anterior. A entrega dispensa migração. O rollback pode reverter os commits dos dois repositórios, incluindo o pin de teste do Connector no Nexus.

SI-031 permanece em andamento. A oferta contempla o Codex com uma sessão viva. A validação entre máquinas e as apresentações remotas de Pi e Claude continuam pendentes. [Dados, hashes e resultados](si031-connector-connect-terminal.json)
