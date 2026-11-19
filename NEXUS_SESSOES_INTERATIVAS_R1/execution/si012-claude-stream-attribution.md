# SI-012, SI-026 e SI-036 · Origem das respostas no Claude stream-json

A conversa da Home usa o UUID de cada envelope publicado pelo Claude. Dois blocos associados à mesma mensagem do provedor preservam identidades distintas. Uma resposta é rotulada como “Subagent” quando aponta para uma chamada Agent ou Task observada na mesma operação e no UUID da sessão confirmado pelo Claude. A projeção limita o texto, aplica a sanitização do Core e omite ferramentas e raciocínio. As respostas da sessão principal continuam aparecendo como “Assistant”.

No Windows, o Claude Code 2.1.328 executou um turno com respostas de modelo simuladas em loopback. O Nexus registrou um resultado canônico e três mensagens na mesma operação. Duas tinham o mesmo texto e UUIDs de envelope diferentes. A terceira trazia o vínculo nativo com a chamada do subagente. A sondagem reproduziu a emissão de um envelope adicional depois do primeiro resultado, fora do escopo da operação já concluída. Também houve tentativas de abertura bloqueadas por falha de registro do processo ou divergência do perfil. O ensaio nativo não chegou ao fechamento canônico na execução com os três registros. O job descartável terminou sem processos restantes.

Reabri uma cópia SQLite do mesmo ensaio com o Nexus instalado, pela API e em um navegador real. A leitura paginada devolveu três IDs distintos e o navegador mostrou duas linhas “Assistant” e uma “Subagent”. A reprodução manteve o processo nativo desligado. O ledger registra SI-T-E06 como aprovado nesse recorte.

Passaram 121 testes instalados do Core, 45 do Connector, 37 do Nexus e 419 testes Node do frontend. O build do frontend, os geradores de contrato, a resolução offline, a verificação de artefatos e os testes de instalação dos pacotes passaram. O stream-json ainda precisa de qualificação para deltas, eco do prompt, conteúdo posterior à conclusão da operação e outros builds. O aceite humano segue pendente.

A mudança dispensa migração. Para reverter, reverta a projeção e o frontend do Nexus junto com o pin do Core nos dois consumidores. O próximo passo no transcript é verificar a indicação de lacunas e a paginação em um histórico com 10 mil itens.

[Dados e hashes do ensaio](si012-claude-stream-attribution.json)
