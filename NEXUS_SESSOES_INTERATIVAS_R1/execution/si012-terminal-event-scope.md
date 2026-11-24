# SI-012 · Eventos da sessão no terminal

`work status`, `work events` e `work watch` conferem a identidade da sessão no retorno da API antes de mostrar a página. A conferência inclui o vínculo do workspace, o ID da sessão, a geração do dono, a época esperada, o escopo e a sequência de cada evento e o cursor de continuação. Uma resposta incompatível é recusada antes da apresentação. A leitura continua usando a API canônica e o checkpoint do CLI.

Quando há outras páginas, a orientação no terminal inclui o ID da sessão, a época e o número a passar em `--after-sequence`. O próximo comando pode retomar o mesmo fluxo após uma reconexão.

O ensaio cobre troca de sessão, vínculo, geração e época antes ou dentro da página, avanço indevido do cursor e a instrução de continuação. As nove variações falharam no wheel anterior. Passaram 20 testes no código-fonte e os mesmos 20 no wheel corrigido, com API e SQLite e respostas sintéticas dos peers. A mudança dispensa migração e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si012-terminal-event-scope.json)
