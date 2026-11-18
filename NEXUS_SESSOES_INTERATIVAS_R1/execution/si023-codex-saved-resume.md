# SI-023 Retomada exata do Codex

O Core permite exigir o identificador exato da thread no pedido de abertura da sessão sucessora. Antes de resolver o ambiente ou criar o processo nativo, exige uma autorização do host vinculada à mesma thread, sessão sucessora e escopo. A autorização inclui a comprovação de que o contexto foi gravado e de que o host tem posse exclusiva após o encerramento anterior. Um pedido repetido mantém o mesmo recibo. Usar a mesma chave para outra thread ou para uma abertura comum retorna conflito. O Core usa um hash da thread na identidade da operação.

## Observação no app-server real

O Codex 0.157.0 para Windows x64 (`ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f`) informou um caminho de armazenamento para uma thread ociosa, vazia e não efêmera. O perfil e o projeto eram temporários. Nenhum arquivo foi criado antes ou depois da saída do primeiro processo. O segundo processo recebeu uma recusa nativa ao chamar `thread/resume` com a mesma thread. A resposta reportou ausência do histórico gravado.

Os métodos utilizados foram `initialize`, `account/read`, `thread/start` e `thread/read` no primeiro processo, seguidos de `initialize`, `account/read` e `thread/resume` no segundo. O teste encerrou apenas os processos temporários e consumiu zero tokens. A leitura de um caminho informado pela API, por si só, é insuficiente para comprovar persistência. Esta observação cobre o caso negativo com uma thread vazia.

## Escopo da evidência

O teste simulado confirma a retomada da thread exata com autorização válida, a recusa quando a autorização falta ou aponta para outra thread, e o conflito de recibo antes de uma segunda abertura. O teste do app-server cobre a ausência de histórico. A persistência de uma sessão com trabalho real, as fases duráveis de transferência, a admissão com consentimento no Nexus, a recuperação após falha e o comando `nexus session resume` continuam pendentes.

O contrato Python do Core ganhou um campo opcional no pedido de abertura. As aberturas existentes mantêm a mesma identidade de operação. O mesmo cálculo identifica a abertura, a projeção imediata do recibo R4 e sua recuperação a partir do registro local. Os schemas gerados foram conferidos. Para reverter a etapa, restaure nos dois consumidores o pacote Core anterior, de SHA-256 `b6b7061288b536acb64b5afbc3043d7b740e3f70a4c28d715c45c4345d023b36`.

O Core `5df03b51fda46a293ae5f0cca73c8947be139726` passou 119 testes direcionados e 37 testes com o wheel instalado. Com esse pacote, o Nexus passou 48 testes de CLI, despacho e recuperação, e o Connector passou 67 regressões R4. O wheel e o pacote-fonte passaram a validação estrita. Os dois consumidores apontam para o mesmo wheel 0.0.16 de desenvolvimento, de SHA-256 `f43b40c69660cf50129506110576d1890fdc0b00867dff15b6d7ae5219c568f1`. [CI do Core](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44389382790)

## Prova do histórico gravado

O Core `1ed4bfa2854122b61c5ab6cc5df781e7683123ec` vincula a leitura do histórico à thread e ao dono verificado, incluindo a concessão corrente, o processo e o recibo de abertura. Aceita o arquivo regular selecionado pelo app-server no diretório de estado efetivo, com identidade de thread e projeto no cabeçalho. Confere a estabilidade do arquivo e registra tamanho e SHA-256. Uma tentativa sem arquivo, com ID divergente ou com atividade ou aprovação observada não produz prova. O caminho e o conteúdo ficam fora dos metadados do visualizador. [Formato do rollout do Codex 0.157.0](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/rollout/src/recorder.rs#L1952-L1988)

Em um perfil descartável, o binário real aceitou um item sintético de histórico por `thread/inject_items`, gravou o marcador e manteve o mesmo arquivo e SHA-256 antes e depois da saída do primeiro app-server. Um segundo app-server retomou a mesma thread com `thread/resume`. O marcador foi confirmado no arquivo, mas não apareceu na resposta de retomada. O teste fez uma única chamada de abertura, uma de retomada e nenhuma de inferência. O resultado comprova persistência do arquivo e retomada da identidade, com conteúdo sintético.

Passaram 99 testes direcionados do Core, 40 com o pacote instalado, 44 no Nexus e 67 no Connector. O mesmo wheel de desenvolvimento (SHA-256 `0a377b4b66a158ae05d570e740f4d872b0cb9bfeda5943662f0a6ed19a77aa8d`) está nos dois consumidores. Os pacotes passaram validação estrita. Nenhuma migração foi necessária. Para reverter essa etapa, restaure nos dois consumidores o wheel anterior, de SHA-256 `f43b40c69660cf50129506110576d1890fdc0b00867dff15b6d7ae5219c568f1`. [CI do Core](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44392848696)

## Prova de encerramento no Nexus

Com a interação de sessão habilitada, o Nexus embutido captura a prova privada imediatamente antes de um encerramento canônico do Codex qualificado. A captura é limitada pelo tempo restante da concessão e pode ser omitida quando o histórico estiver inacessível. O encerramento segue por seu recibo canônico.

A migração 181 adiciona um registro por pedido de encerramento. A verificação exige o recibo de sucesso no Nexus e no journal do Core, o mesmo processo de origem, a liberação confirmada da reserva do Core e a mesma identidade e SHA-256 do arquivo. Um histórico alterado fica inelegível. Uma prova sem confirmação de encerramento continua pendente. A manutenção pode reconferir o registro após uma interrupção, sem chamar o runtime para executar trabalho. O banco local preserva os identificadores de arquivo do Windows com precisão integral.

Passaram 16 regressões com o wheel do Nexus instalado, incluindo cinco cenários da captura com adaptador sintético. Eles cobrem histórico intacto, arquivo alterado, retomada da verificação por outro reconciliador a partir do registro durável, ausência de prova viva e falta de prova de liberação. Passaram também oito testes de migração. O smoke HTTP usou dois clientes MCP autenticados no Server temporário, confirmou a saída física pelo stop canônico e contabilizou zero chamadas a provedores. O wheel e o sdist passaram a validação estrita.

A migração é aditiva, começa com a tabela vazia e preserva filas, controles e recibos existentes. O código anterior recusa uma base na versão 181. Para voltar diretamente a ele em um ambiente migrado, use a cópia consistente anterior à migração.

A matriz inicial do Core encontrou a ausência de `CodexRolloutEvidence` no guia de API. A correção documental `0c556caa263967b9f25e05edbb91353bb8fd3744` passou 43 testes e reproduziu o mesmo SHA-256 do wheel que os consumidores já usam. [CI da correção do Core](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44395910144)

O próximo passo é usar a prova de origem na admissão explícita da sucessora, com consentimento e exclusão duráveis. A retomada deve revalidar o arquivo, preservar a fila de origem e usar configuração MCP e credenciais próprias. O teste com adaptador sintético e um novo reconciliador cobre a recuperação do registro, e a verificação de uma sucessora após a reinicialização do serviço continua pendente.
