# SI-T-I08 — Terminal, fila da Home e reorientação

O ensaio com os três wheels instalados usou o app-server Codex 0.157.0
no Connector, o visualizador Codex 0.170.0 em Windows ConPTY e o Edge.
O R4 e as respostas determinísticas passaram por loopback. O projeto,
o login sintético e o perfil do provedor eram descartáveis. Houve quatro
pedidos ao simulador e zero chamadas a provedores externos.
[Comandos, hashes e observações](si038-terminal-home-queue-steer-loopback.json)

1. Um turno de preparação iniciou uma única thread. O Connector recuperou
   a conexão existente com `connect -i` e anexou o leitor à thread ativa.
   O operador abriu a escrita explicitamente com `session attach --write`.
   Quando o preparo terminou, a mensagem digitada no Codex iniciou o
   turno observado nessa mesma thread.
2. Na Home, **Add to next turn** recebeu HTTP 202 e um recibo `QUEUED`
   sem operação vinculada. No CLI, `session steer` exibiu o turno em revisão.
   A confirmação enviou exatamente um `turn/steer` com o ID nativo desse
   turno. A entrada da Home permaneceu enfileirada. O simulador recebeu a
   reorientação dentro do turno original. O recibo do produto permaneceu
   em `DISPATCHING` para a reorientação.
3. Ctrl+] desanexou os dois visualizadores antes do resultado. O
   visualizador de escrita restaurou o console. A Home manteve a conversa
   ativa e a mensagem pendente. Após a liberação da resposta pelo
   simulador, a entrada da Home iniciou um turno separado. O navegador
   mostrou uma vez cada mensagem da jornada e seu resultado.
4. O SQLite confirmou uma sessão, três turnos incluindo o de preparação,
   uma reorientação, dois anexos `DETACHED` e resultados para os três
   turnos. O journal do Connector registrou um único lançamento do
   app-server. O fechamento canônico encerrou esse processo. As
   verificações de integridade e de chaves estrangeiras passaram.

O cenário de integração instalada e 88 regressões passaram. Os primeiros
roteiros usaram um perfil de teste com metadados insuficientes para o
visualizador, esperaram o eco integral do teclado e passaram a
`session steer` uma opção reservada a listagem e anexação. O ensaio
concluído usou um perfil temporário que reportou o esforço de raciocínio,
confirmou o envio pelo turno observado e usou o perfil salvo para executar
o controle. O cofre de teste foi injetado somente no ambiente descartável.

A campanha real e a qualificação em hosts distintos seguem abertas. A
alteração registra evidência e atualiza o ledger. A reversão do commit
dispensa migração de dados e de esquema.
