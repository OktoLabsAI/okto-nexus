# SI-024 e SI-038 · Recibo de reorientação do Codex

O Core espera até cinco segundos pela resposta de `turn/steer` no build Windows qualificado do app-server Codex 0.157.0. Se o `turnId` coincide com o turno revisado, o Core conclui a operação e o Nexus registra `ACCEPTED_NATIVE`. O recibo confirma a aceitação da reorientação. O resultado e os eventos de geração continuam ligados ao turno original. Resposta ausente ou divergente mantém o efeito incerto. Consultar a mesma intenção devolve o recibo gravado, sem novo envio.

No Windows, o app-server 0.157.0 devolveu a confirmação do turno exato. No Edge, uma mensagem comum permaneceu na fila durante a reorientação pelo Nexus CLI e iniciou um turno separado após o término. O visualizador 0.170.0 desanexou sem interromper o app-server. O journal e o SQLite confirmaram uma sessão, uma única reorientação aceita, três resultados, dois anexos desanexados e fechamento canônico. O ensaio usou respostas determinísticas em loopback e perfis descartáveis. [Dados e hashes](si024-codex-steer-ack.json)

Passaram quatro casos focais instalados do Core, 23 testes do Connector e sete do Nexus. A suíte de código-fonte do Core teve 110 aprovações, um salto e um teste antigo de inicialização que excedeu seu limite de 300 ms sob carga. O teste antigo passou isoladamente depois do ensaio nativo. Os lotes iniciais também corrigiram a preparação do ambiente e o identificador temporário do navegador.

Nexus e Connector fixam o mesmo wheel Core 0.0.16. O marco dispensa migração. Para reverter, restaure o wheel anterior em ambos os consumidores e mantenha os recibos já gravados. O ensaio não usou credenciais de provedor nem qualificou uma campanha paga.
