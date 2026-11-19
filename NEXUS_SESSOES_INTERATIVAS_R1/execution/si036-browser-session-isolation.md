# SI-034 e SI-036 · Rascunhos e perda de acesso na Home

No Edge 157 em Windows, abri um card de um agente com duas sessões Pi ativas no mesmo projeto. A lista pediu uma escolha explícita. Digitei um rascunho em cada sessão e alternei entre elas no mesmo painel. Cada retorno recuperou o texto original e mostrou apenas a conversa daquela sessão. O navegador não enviou nenhuma mutação durante a troca.

Enviei uma mensagem para o próximo turno da primeira sessão. A API respondeu HTTP 202 e o servidor confirmou a entrada `QUEUED`, ainda sem operação associada. Invalidei a sessão autenticada pelo endpoint de logout enquanto o painel estava aberto. O navegador detectou a perda de acesso e retirou a conversa, o editor e os controles. Ao liberar os dois turnos já em execução, os dois processos Pi concluíram seus trabalhos e os resultados ficaram gravados. A mensagem enfileirada ficou `BLOCKED_AUTH`, sem criar turno ou ser enviada sob outra autorização.

Após novo login no mesmo navegador, cada sessão recuperou seu resultado e abriu com o editor vazio. Na Home a 360 px, confirmei dois cards em Results e abri o primeiro com o ponteiro. O ensaio usou o Nexus, o Connector, o Core e dois processos Pi 0.87.1 reais em ambiente isolado. As respostas eram sintéticas, com rede externa bloqueada no Pi. Em separado, passaram 417 testes do frontend e 57 de API, autoridade, conversa e fila.

O registro cobre o caminho de perda da sessão por logout no navegador. A validação individual de outras causas de 401/403 e os ensaios de zoom a 200%, leitor de tela e aceite humano seguem em aberto. Esta etapa atualiza a evidência e o ledger. O rollback é a reversão desse registro e dispensa migração.

[Registro de evidências e hashes](si036-browser-session-isolation.json)
