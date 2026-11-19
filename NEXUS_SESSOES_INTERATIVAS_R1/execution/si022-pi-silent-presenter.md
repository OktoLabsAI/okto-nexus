# SI-022, SI-025 e SI-032 — Expiração da apresentação Pi remota

O Nexus anuncia `pi_keepalive` ao preparar uma apresentação remota do Pi. O CLI usa essa capacidade para enviar um sinal periódico enquanto o leitor ou o editor espera. O sinal pertence à apresentação autenticada e mantém apenas seu prazo de validade. A fila, a concessão de execução e o processo continuam sob a autoridade do executor. Pedidos válidos do editor também renovam a apresentação.

Nos ensaios de transporte, o wheel anterior prorrogou a apresentação de leitura e a de escrita durante o silêncio da aplicação. No código atualizado, um ping do WebSocket manteve a conexão ativa sem alterar a validade. A expiração liberou o renderer, e os novos leitor e editor renovaram o prazo sem digitação. As verificações de conexão, fila e autoridade ocorreram no Nexus e Connector do produto, com processo nativo simulado. [Regressão](../../tests/execution_r4/test_remote_pi_presentation.py)

No ensaio com os wheels instalados, o próprio Connector manteve o Pi 0.87.1 durante o corte. O editor e o leitor em Windows ConPTY renovaram suas apresentações enquanto esperavam. A entrada enfileirada foi entregue uma única vez na mesma sessão e o CLI recuperou seu recibo original. O processo do Pi saiu pelo fechamento canônico. O ensaio usou relógio de apresentação controlado e respostas simuladas em loopback, sem chamadas externas. Passaram 71 regressões com os pacotes instalados. [Resultados e hashes](si022-pi-silent-presenter.json)

O roteiro inicial esperava o recibo final antes de liberar a resposta simulada. A nova execução liberou a resposta após observar o evento nativo correlacionado ao segundo turno. Em outra tentativa, a conexão do executor caiu durante a abertura. O ensaio final usou um projeto novo e aguardou uma publicação de inventário após a conexão ficar pronta.

O CLI envia o sinal após a oferta do servidor. Em ensaio cruzado com o CLI novo e o servidor anterior, o editor abriu no Pi real, interrompeu a execução revisada, pausou a fila e se desanexou conservando o processo. Em um servidor atualizado, um leitor anterior que permanece passivo expira após o prazo de 120 segundos. O guia orienta a usar um CLI com suporte à renovação ociosa e a voltar à mesma sessão após o corte. [Guia do terminal](../../docs/terminal-work.md)

O marco dispensa migração. Para reverter, reverta o commit no Nexus. A qualificação entre máquinas continua no ledger.
