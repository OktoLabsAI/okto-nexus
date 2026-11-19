# SI-012, SI-026 e SI-036 · Mensagens retidas do Claude na Home

No pacote anterior, um envio ao terminal Claude retomado terminou com `SUCCEEDED` e gravou o resultado canônico. A API de conversa ficou vazia, embora o arquivo nativo contivesse o prompt e a resposta com IDs distintos.

O Core passou a ler o trecho concluído do histórico depois de corroborar o `Stop`. A leitura verifica o UUID da sessão, o workspace, o ID do prompt aceito pelo hook, o conteúdo enviado e a resposta final. Cada mensagem mantém a identidade da sua entrada no arquivo nativo. A projeção só inclui texto de usuário e assistente da conversa principal e aplica sanitização antes de publicar.

O primeiro ensaio com a mudança concluiu o turno, mas a projeção ainda ficou vazia. O filtro exigia que o registro do prompt fosse posterior ao aceite do hook. O prompt passou a ser correlacionado pelo ID e pelo conteúdo confirmado. O limite temporal continua sendo verificado nas mensagens geradas depois do aceite.

No Edge, enviei o mesmo texto duas vezes pela Home. Cada envio recebeu HTTP 202 e produziu um único par de mensagens. As quatro entradas do painel coincidiram com os UUIDs do arquivo nativo e com duas operações distintas. O mesmo processo Claude executou os dois turnos e o fechamento canônico foi confirmado. O diagnóstico verificou nos dois turnos que o registro do prompt já tinha sido datado ao chegar ao hook.

Passaram 61 testes do Core, 45 do Connector e 50 do Nexus com os pacotes instalados. O ensaio usou o Claude Code 2.1.328 no Windows, com um provedor simulado em loopback. A projeção do modo stream-json, a identificação de subagentes e o aceite humano seguem em aberto. A mudança dispensa migração. Para reverter, reverta a projeção do Nexus e os pins do Core nos dois consumidores em conjunto.

[Registro de evidências e hashes](si012-claude-retained-conversation.json)
