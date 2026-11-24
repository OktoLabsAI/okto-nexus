# SI-012 · Eventos da sessão no terminal

`work status`, `work events` e `work watch` conferem a identidade da sessão no retorno da API antes de mostrar a página. A conferência inclui o vínculo do workspace, o ID da sessão, a geração do dono, a época esperada, o escopo e a sequência de cada evento e o cursor de continuação. Uma resposta incompatível é recusada antes da apresentação. A leitura continua usando a API canônica e o checkpoint do CLI.

Quando há outras páginas, a orientação no terminal inclui o ID da sessão, a época e o número a passar em `--after-sequence`. O próximo comando pode retomar o mesmo fluxo após uma reconexão.

O ensaio cobre troca de sessão, vínculo, geração e época antes ou dentro da página, avanço indevido do cursor e a instrução de continuação. As nove variações falharam no wheel anterior. Passaram 20 testes no código-fonte e os mesmos 20 no wheel corrigido, com API e SQLite e respostas sintéticas dos peers. A mudança dispensa migração e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si012-terminal-event-scope.json)

## Continuação automática de `work watch`

`work watch` usa a época e o cursor da última página validada na consulta seguinte. Uma página adicional já confirmada pode ser lida sem aguardar outro intervalo de polling. O observador continua até o fim das páginas disponíveis quando o pedido termina com sucesso, dentro do prazo informado no CLI. A consulta vazia no mesmo cursor só gera saída se o estado ou outro dado da observação mudou. Se a sessão mudar, a leitura é recusada antes de exibir os dados. Perguntas pendentes são tratadas na sessão observada antes de avançar a página.

Os quatro casos falharam no wheel anterior. Passaram 16 testes no código-fonte e os mesmos 16 no wheel corrigido. A suíte cobriu recuperação pelo CLI e observação durante a parada controlada do Nexus com peers sintéticos. O marco altera a observação e dispensa migração. A reversão usa o commit do Nexus. [Comandos e resultados](si012-terminal-event-scope.json)

## Validação dos limites de cada página

O leitor confere a contagem, o cursor, a sequência contígua confirmada e a indicação de continuação antes de apresentar os eventos. Uma página vazia que indica mais eventos é recusada antes da segunda consulta com o mesmo cursor. Uma página vazia no fim do intervalo continua válida.

O wheel anterior aceitou seis combinações contraditórias de metadados. Em um sétimo caso, `work watch` exibiu a página vazia e voltou a consultar o mesmo cursor. Passaram os mesmos 23 testes no código-fonte e no wheel reconstruído. A suíte inclui envio, retomada e observação com a API canônica, SQLite e peers sintéticos. A inspeção do pacote confirmou que só mudou `terminal_work.py` entre os 815 arquivos do wheel. A alteração é restrita ao Nexus e dispensa migração. A reversão usa o commit do Nexus. [Comandos e resultados](si012-terminal-event-scope.json)
