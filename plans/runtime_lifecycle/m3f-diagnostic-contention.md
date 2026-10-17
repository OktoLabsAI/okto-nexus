# M3f — Contenção compartilhada causada pelo próprio diagnóstico

## Incidente observado

Na instalação global M3c, geração 69, o processo 18616 permaneceu vivo e a UI
confirmou Pi, Claude e Codex em `LOCAL · RECOVERING`. Os três registros de
recuperação individual continuavam `READY`; o executor compartilhado estava
`RECOVERING`.

O log de 2026-10-17T02:03:25Z identifica o caminho
`defer_publication → _recovery_event → SqliteUnitOfWork.__enter__`. A escrita do
aviso `RECOVERY_PUBLICATION_DELAYED` sofreu `DB_ERROR` retryable por timeout na
admissão FIFO de escritores. O erro secundário escapou para `owner.failed()`,
que interrompeu o despachante e iniciou contenção de todos os recursos locais.

O dump de threads posterior mostrou os workers ociosos. A contenção inicial da
fila de escritores já havia cessado; não foi possível atribuir sua origem a
uma transação específica com a instrumentação disponível. Isso não é evidência
de corrupção do SQLite nem de falha simultânea dos três provedores.

O owner usa o mesmo sinal terminal para contenção e encerramento; a recuperação
de inicialização não reativa esse owner parado. Esse limite permanece no plano
de supervisão M6: não se deve limpar o sinal ou recriar um owner sem primeiro
comprovar encerramento dos produtores e liberação dos recursos antigos.

## Correção

- Timeout transitório ao persistir diagnóstico mantém o aviso no log e não
  derruba o host. `runtime_recovery_events` é observabilidade, não uma prova de
  encerramento, autorização, resultado ou liberação.
- A escrita dos fatos de execução continua obrigatória. Publicações pendentes
  continuam sendo tentadas pelo owner existente, sem repetir o efeito nativo.
- Falhas não transitórias não são suprimidas.
- A resposta de recuperação manual verifica se o despachante está realmente
  ativo. A mera existência de um objeto `pump` não é mais prova de prontidão.

## Validação e implantação

Passaram 12 testes de fonte e 20 testes do pacote instalado, sem alterações das entradas durante a campanha. A regressão reproduz contenção real da fila de escrita na emissão
do diagnóstico, combinada com indisponibilidade temporária da publicação de
recibos, nos três adaptadores. Também cobre falha permanente e resposta de
recuperação manual com o owner já parado. Os peers de harness desses testes são
determinísticos; a validação real pela interface será registrada separadamente.

O diagnóstico foi realizado antes de qualquer reinício. Para aplicar código ao
processo já contido será necessário encerramento controlado, backup e nova
inicialização; isso não deve ser descrito como recuperação espontânea do M3c.
