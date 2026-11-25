# SI-034 · Revogação com navegador, terminal e fila ativos

O ensaio de SI-T-H16 rodou em Windows com Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 instalados. O Edge autenticado e o editor Pi 0.87.1 em ConPTY usaram o mesmo login descartável. O Connector hospedou o executor remoto em loopback. O Pi recebeu uma resposta simulada de um provedor isolado. [Versões, hashes e resultados](si034-current-live-author-revocation.json)

1. Com a conversa aberta, o turno original retido e a anexação de escrita ativa, o terminal registrou uma entrada `QUEUED`, vinculada ao login original e sem operação de execução. O navegador tinha um rascunho ainda não enviado.
2. O endpoint de logout revogou esse login. O Edge mostrou a tela de autenticação sem recarga, retirando a conversa, o rascunho e os controles. O editor encerrou por perda da anexação e restaurou o modo do terminal. Outro login permaneceu válido. O processo Pi e a geração do Connector continuaram os mesmos.
3. Depois de liberar o turno, a fila manteve o ID, a ordem e a referência original da entrada em `BLOCKED_AUTH`. O item ficou sem operação e sem indicação de possível efeito. O histórico nativo registrou somente o pedido original.
4. Após autenticação pelo formulário no mesmo Edge, a sessão exata mostrou o pedido e o resultado originais. O rascunho e a entrada bloqueada não apareceram. A auditoria confirmou uma abertura, um turno, um resultado e um fechamento canônico. A anexação ficou `DETACHED` e os hashes do ticket e do desafio foram removidos.

Passaram 200 regressões do pacote instalado. As suítes cobriram autoridade, cancelamento e pausa de fila, redação da conversa, contratos HTTP e proteção de origem/CSRF, handshake e apresentação do Codex remoto com peers de protocolo. Os avisos de depreciação vieram de Starlette e websockets.

No primeiro ensaio, o retorno automatizado parou na Home clássica depois de observar a revogação. Na rodada final, o formulário do Edge abriu automaticamente a sessão exata na Home operacional. Uma navegação redundante do driver acionou a confirmação já prevista para sair do painel. A verificação usou o DOM capturado antes dessa navegação e permitiu que o teste nativo concluísse. [Origem e CSRF](si034-browser-websocket-origin.md) [Tickets de anexação](si034-native-attachment-ticket-replay.md) [Comandos de terminal](si034-terminal-command-authority.md) [Privacidade da conversa](si034-transcript-privacy.md)

Este marco atualiza o ledger e as evidências. O rollback consiste em reverter o commit e dispensa migração. O ensaio se limita ao Windows em loopback. A próxima etapa é SI-035, recuperação de falhas e concorrência.
