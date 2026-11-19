# Leitura remota da thread Codex gerenciada

Nexus e Connector negociam uma capacidade de leitura no WSS outbound existente. O Nexus seleciona a abertura canônica, o stream e a thread a partir do escopo e da geração exatos. A autorização humana, o vínculo ativo, as revisões e a posse do lease são verificados antes e depois da leitura. O daemon encaminha o pedido ao Core que já hospeda a sessão. O diretório informado vem do contexto que o próprio host leu.

A extensão permite uma leitura tipada e limitada. Ela correlaciona o resultado ao pedido e à conexão, ignora respostas tardias e deixa o controle e a renovação de leases na rota existente. Hosts e servidores que não negociam a extensão continuam a usar seus contratos anteriores. A leitura não cria sessão, usa grant ou gera uma operação produtiva.

O teste integrou Nexus, autenticação HTTP humana, Connector, IPC e WSS em loopback. Um simulador forneceu o contexto Codex na fronteira nativa. A credencial de agente e a geração incorreta foram recusadas antes da leitura. Depois do logout durante uma leitura em andamento, o Nexus descartou a resposta e o turno simulado concluiu. Ensaios separados rejeitaram respostas com hash ou geração divergentes e confirmaram que uma resposta tardia não reabre uma leitura.

O contrato é aditivo, sem migração. O rollback reverte os commits e restaura os pins anteriores. A ausência da capacidade na negociação mantém o runtime existente operável. SI-022 continua em andamento. A próxima etapa liga a leitura ao broker de attachments, ao cursor e ao terminal do operador. Os testes de attach e detach remoto em máquinas separadas permanecem abertos. [Evidências](si022-remote-codex-context.json)
