# SI-023 Retomada exata do Codex

O Core permite exigir o identificador exato da thread no pedido de abertura da sessão sucessora. Antes de resolver o ambiente ou criar o processo nativo, exige uma autorização do host vinculada à mesma thread, sessão sucessora e escopo. A autorização inclui a comprovação de que o contexto foi gravado e de que o host tem posse exclusiva após o encerramento anterior. Um pedido repetido mantém o mesmo recibo. Usar a mesma chave para outra thread ou para uma abertura comum retorna conflito. O Core usa um hash da thread na identidade da operação.

## Observação no app-server real

O Codex 0.157.0 para Windows x64 (`ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f`) informou um caminho de armazenamento para uma thread ociosa, vazia e não efêmera. O perfil e o projeto eram temporários. Nenhum arquivo foi criado antes ou depois da saída do primeiro processo. O segundo processo recebeu uma recusa nativa ao chamar `thread/resume` com a mesma thread. A resposta reportou ausência do histórico gravado.

Os métodos utilizados foram `initialize`, `account/read`, `thread/start` e `thread/read` no primeiro processo, seguidos de `initialize`, `account/read` e `thread/resume` no segundo. O teste encerrou apenas os processos temporários e consumiu zero tokens. A leitura de um caminho informado pela API, por si só, é insuficiente para comprovar persistência. Esta observação cobre o caso negativo com uma thread vazia.

## Escopo da evidência

O teste simulado confirma a retomada da thread exata com autorização válida, a recusa quando a autorização falta ou aponta para outra thread, e o conflito de recibo antes de uma segunda abertura. O teste do app-server cobre a ausência de histórico. A persistência de uma sessão com trabalho real, as fases duráveis de transferência, a admissão com consentimento no Nexus, a recuperação após falha e o comando `nexus session resume` continuam pendentes.

O contrato Python do Core ganhou um campo opcional no pedido de abertura. As aberturas existentes mantêm a mesma identidade de operação. O mesmo cálculo identifica a abertura, a projeção imediata do recibo R4 e sua recuperação a partir do registro local. Os schemas gerados foram conferidos. Para reverter a etapa, restaure nos dois consumidores o pacote Core anterior, de SHA-256 `b6b7061288b536acb64b5afbc3043d7b740e3f70a4c28d715c45c4345d023b36`.

O Core `5df03b51fda46a293ae5f0cca73c8947be139726` passou 119 testes direcionados e 37 testes com o wheel instalado. Com esse pacote, o Nexus passou 48 testes de CLI, despacho e recuperação, e o Connector passou 67 regressões R4. O wheel e o pacote-fonte passaram a validação estrita. Os dois consumidores apontam para o mesmo wheel 0.0.16 de desenvolvimento, de SHA-256 `f43b40c69660cf50129506110576d1890fdc0b00867dff15b6d7ae5219c568f1`. [CI do Core](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44389382790)

O próximo passo no Nexus é vincular a prova de persistência à posse do runtime, confirmar o encerramento pelo Core e registrar a linhagem e a autorização da sucessora. O diretório de estado efetivo do Codex pode ser específico da sessão. A retomada precisa preservar o contexto sem reutilizar a configuração MCP nem a credencial da sessão encerrada.
