# Interrupção da execução exata no Pi

O painel do Nexus e o comando `session interrupt` revisam a execução ativa do Pi hospedado. A confirmação grava a pausa da fila e a operação no mesmo commit. O Nexus preserva a execução revisada na associação do recibo. O Core revalida a referência, e o Pi confere a mesma referência imediatamente antes de chamar seu abort nativo. O evento de término carrega a referência da execução e confirma o resultado apresentado no recibo.

O ensaio no Windows usou Pi 0.87.1 real e respostas simuladas. A API recusou um alvo incorreto e manteve a fila aberta. Uma confirmação válida interrompeu a execução original, conservou uma mensagem pendente e manteve o mesmo processo. A continuação só começou após a retomada explícita. A API e o receptor RPC recusaram a referência antiga enquanto a continuação rodava. Repetir a confirmação original na API recuperou a operação existente. Na variante CLI, cancelar a revisão conservou a execução e a fila. A confirmação e a consulta ao recibo passaram pelo servidor real. [Dados dos ensaios](si025-pi-exact-interrupt.json)

Reproduza com `si025-pi-terminal-e2e.py --interrupt`. Acrescente `--interrupt-surface cli` para usar o CLI. A etapa dispensa migração. A reversão coordena os três commits desta etapa para restaurar o comportamento anterior e os pins correspondentes.

Passaram 91 testes do Core instalado, 61 do Connector com o novo Core, 77 do Nexus instalado e 417 testes do frontend em Node. O ensaio com o Pi real também repetiu a reorientação com entrega na fronteira.

A SI-025 segue em andamento. A confirmação no editor nativo anexado, as aprovações, a verificação em navegador e a qualificação com provedor real seguem pendentes.
