# SI-026 — Conclusão canônica do turno Claude

O Core associa o `prompt_id` do Claude à operação autorizada antes de liberar o envio. Um evento `Stop` ou `StopFailure` só conclui a operação se corresponde ao mesmo prompt, UUID e diretório da sessão. O Core ignora repetições e eventos de outro contexto. No sucesso, também exige o modo de permissão previsto e a ausência de trabalho em segundo plano ou continuação programada. A fila pode avançar depois que o journal confirma o resultado da operação exata.

O texto de sucesso passa pela remoção de segredos antes de ser publicado. O resultado de erro leva um código canônico, e o Core mantém caminhos privados, identificadores nativos e detalhes brutos fora do evento. O teste R4 do Nexus confirmou que um `Stop` correspondente resolve `OUTCOME_UNKNOWN`, preserva a mesma operação e publica o resultado com o valor sensível ocultado. A operação foi enviada uma única vez.

Dois ensaios com o wheel do Core e o Claude Code 2.1.328 no Windows gravaram `SUCCEEDED` a partir de `Stop` e `FAILED` a partir de `StopFailure`. No sucesso, o mesmo processo concluiu o turno com o leitor desconectado. No erro, o Claude fez quatro chamadas de modelo ao simulador dentro da mesma operação. A confirmação veio do hook nativo, e os ensaios usaram loopback com ferramentas desabilitadas. [Cenários e hashes](si026-claude-terminal-completion.json)

A abertura em produção ainda precisa ligar esse terminal à admissão exclusiva da sucessora e comprovar a configuração efetiva dos hooks. A rota de sucesso exige uma configuração revisada em que outro hook `Stop` não possa prolongar o turno. A anexação e os controles nativos de turno continuam pendentes. O marco dispensa migração. Para reverter, restaure os commits e wheels anteriores.
