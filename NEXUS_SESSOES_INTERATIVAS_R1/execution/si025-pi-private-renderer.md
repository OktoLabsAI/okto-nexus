# Canal privado do renderer do Pi

O launcher hospedado abre um socket em `127.0.0.1` dentro do processo do Pi 0.87.1. O Core e o renderer autenticam a conexão com HMAC, desafio novo por conexão e vínculo ao ID exato da sessão. A chave nasce no Core, é entregue ao processo filho e retirada do ambiente antes da inicialização da CLI. O filho informa a porta apenas pelo pipe de protocolo da abertura. O Core revalida o processo, a concessão R4 e a sessão antes de entregar cada bloco ao host. O Nexus também verifica o mapeamento canônico antes de liberar a saída ao chamador interno.

O renderer usa os componentes de transcrição do Pi com uma janela de saída limitada. Ele recebe um visualizador por sessão e ignora a entrada de teclado. O filtro permite texto, estilo e movimentos de cursor necessários para a transcrição. Sequências de clipboard, links OSC, imagens e relatórios do terminal são descartados. Se o buffer do visualizador exceder o limite, o socket é fechado. A fila e o canal RPC continuam com o dono.

No ensaio de Windows, a fábrica de produção do Core abriu o Pi com uma extensão sintética em um perfil descartável. O primeiro visualizador viu o início do turno. Após o detach, a consulta R4 confirmou que a mesma sessão continuava em streaming. O segundo visualizador recuperou o contexto e recebeu a resposta. A operação repetida devolveu o mesmo recibo e o histórico reteve um único par de pergunta e resposta. O fechamento canônico encerrou o dono ao final. O ensaio acessou o renderer pelo `EmbeddedRuntimeHost` com composição de teste. O renderer usa socket real e o ensaio lê quadros em memória. [Resultados e hashes](si025-pi-private-renderer.json)

As regressões verificam a recusa de outra sessão, de um segundo visualizador, de chave inválida e da reflexão da prova do cliente. Também verificam a remoção de sequências de terminal e a desconexão quando uma saída excede o limite. O teste do Nexus recusa o renderer Pi em um mapeamento Codex.

Passaram 57 testes do Core, 103 do Connector e 23 do Nexus com os wheels instalados. O mesmo wheel do Core está fixado nos dois repositórios e os hashes do manifesto de CI foram conferidos.

Para reproduzir, execute `python NEXUS_SESSOES_INTERATIVAS_R1/execution/si025-pi-observer-probe.py --node <node.exe> --pi-release <raiz-do-release> --hosted-core --hosted-turn` com os wheels registrados na evidência disponíveis no interpretador. O preload do ensaio bloqueia conexões de saída do Pi e limita a leitura ao perfil descartável e aos arquivos necessários do release.

A alteração dispensa migração. A reversão coordenada dos três commits restaura os pins anteriores. A SI-025 segue em andamento. A próxima etapa deve emitir tickets do operador para esse canal e validar o cliente de terminal e a entrada canônica com fila e aprovações.
