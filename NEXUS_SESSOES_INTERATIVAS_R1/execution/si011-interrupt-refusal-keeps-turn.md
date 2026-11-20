# SI-T-C16 — Recusa de interrupção mantém o turno e a fila

No Edge, o operador revisou o turno ativo e confirmou a interrupção.
O Nexus registrou a barreira da fila antes de chamar o peer. O peer
Codex de teste recusou o comando antes da escrita nativa. O recibo
ficou associado ao turno exato, sem efeito possível.

A conversa exibiu que a interrupção foi recusada, que o turno
selecionado continuava rodando e que havia uma mensagem na fila
pausada. A execução original terminou naturalmente. A pausa
permaneceu e o Nexus não despachou a mensagem.
[Dados do ensaio no navegador](si011-interrupt-refusal-keeps-turn.json)

Passaram o ensaio com o pacote instalado no Edge e a regressão unitária
da mensagem de status. A recusa foi injetada em um peer Codex e o
navegador recebeu a resposta da API em loopback. Essa verificação
cobre a recusa comprovada antes do envio, com efeito possível falso.

A primeira rodada de navegador usava campos adicionais no destino
da Home e não abriu a conversa. O destino foi ajustado ao contrato
e a repetição passou. O marco dispensa migração. Reverter o commit
remove o registro.
