# SI-012 e SI-036 · Lacunas e paginação da conversa

A API de conversa identifica a primeira sequência confirmada que está indisponível. Ela entrega o trecho contíguo verificado, conserva o cursor nesse ponto e indica que a conversa está incompleta. A Home mostra um aviso de histórico indisponível e encerra a paginação naquele ponto. O aviso de recuperação continua disponível para eventos pendentes que ainda podem chegar. A rota canônica de eventos continua recusando uma leitura que atravessa uma lacuna confirmada.

No cenário SI-T-E05, o navegador abriu uma conversa sintética de 10 mil mensagens e carregou 50. Um clique carregou as próximas 50, com duas requisições e cursores 0 e 50. As respostas da API tinham 25195 e 25216 bytes. Repetir a segunda página manteve o mesmo corpo e a mesma época. A API recusou um limite acima de 50 eventos.

No cenário SI-T-E04, retirei as sequências 3 a 7 apenas da cópia descartável. A API informou a ausência a partir de 3 e conservou o cursor em 2, mesmo quando a lacuna começava no limite da página. O navegador mostrou as duas mensagens verificadas e o aviso, com uma única leitura. O ensaio confirma o comportamento quando faltam eventos antes confirmados. A política de retenção e o motivo da ausência estão fora desse ensaio. Nenhum harness ou provedor foi iniciado.

Passaram 35 testes Python no código-fonte, 39 com o pacote instalado e 420 testes frontend em Node. A validação incluiu o build do dashboard, o lock offline, as distribuições e a comparação byte a byte com o pacote instalado. O Ruff apontou os mesmos quatro diagnósticos do baseline. Os resultados são de API e navegador automatizado. O aceite por leitor de tela e por usuário permanece pendente.

A alteração dispensa migração e alterações nos pins. Para reverter, use o commit deste marco no Nexus. O próximo cenário verifica o estado da mensagem enfileirada e a recuperação de um envio cujo resultado ficou incerto.

[Dados e hashes dos ensaios](si012-history-gap-and-paging.json)
