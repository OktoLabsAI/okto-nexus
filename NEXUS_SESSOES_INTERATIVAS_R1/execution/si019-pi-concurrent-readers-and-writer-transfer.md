# SI-019 · Leitores simultâneos e transferência de escrita no Pi

No candidato anterior, duas tentativas de escrita concorrentes resultaram em um único escritor. Um terminal autorizado de leitura recebeu uma recusa enquanto esse escritor estava conectado. O Nexus serializava todas as apresentações da sessão, e o Connector e o renderer do Pi também limitavam cada sessão a uma apresentação.

O Core agora admite até dois leitores e um editor. Cada leitor tem seu próprio renderer e pode sair sem interferir nos demais. O Connector conserva o limite de duas sessões por conexão R4. O Nexus serializa apenas as apresentações com escrita, para que o novo escritor abra o renderer depois de o anterior soltar sua vaga. O broker continua exigindo o epoch revisado, confirmação explícita para transferência e a validação do escritor dentro da transação da fila.

No ensaio local, dois logins emitiram ofertas no mesmo epoch. O broker confirmou apenas uma. O segundo login respondeu `n` no terminal e manteve o escritor anterior. Em uma nova tentativa respondeu `y`, e o epoch passou de 1 para 2. O antigo escritor perdeu a capacidade de registrar uma mensagem. Um leitor atravessou a transferência, e outro pôde se conectar enquanto o novo escritor estava ativo. O Pi 0.87.1 continuou no mesmo processo e na mesma sessão. Os leitores exibiram o resultado do turno original e do turno iniciado após a fila. O histórico nativo registrou cada mensagem uma vez. O fechamento canônico encerrou o processo, e as verificações SQLite passaram.

Os logins representavam duas sessões autenticadas da mesma conta de teste. O Pi usou respostas determinísticas locais. A primeira tentativa com os wheels corrigidos revelou que a fixture ainda esperava texto de outro cenário no segundo turno. Na rodada seguinte, manter a resposta artificial em espera encheu a captura inicial do ConPTY. A validação final liberou a resposta pelo sinal da fixture e observou também os bytes mais recentes.

A regressão do Connector exercitou dois leitores e um editor pelo R4. O ensaio integrado remoto usou o Nexus e o Connector instalados, com um renderer de fixture, para abrir os três terminais na sessão exata e registrar a entrada do editor. Os testes do Core cobriram os limites de leitura e escrita e a filtragem do terminal.

A suíte ampla do Core teve 2.421 testes aprovados, 70 ignorados e três falhas reproduzidas com o wheel anterior. O commit `049feff` revisou a fixture de retry do Codex para usar saída controlada, atualizou a expectativa de conversação do Claude 2.1.328 e documentou `ClaudeTerminalResumeGrant`. A rodada focada seguinte teve 25 aprovados e dois ignorados. O conteúdo do wheel permaneceu igual após essas correções de testes e documentação.

Os wheels vendorizados passaram pelas verificações de hash e de conteúdo. A alteração dispensa migração de banco e preserva o formato das mensagens R4. Para reverter, reinstale em conjunto as versões candidatas anteriores do Nexus, do Connector e do Core indicadas na evidência. Os gates SI-T-G06 e SI-T-G07 conservam a qualificação pendente para campanhas. [Resultados e versões](si019-pi-concurrent-readers-and-writer-transfer.json)

## Revalidação do broker e do transporte

Passaram 97 casos com o Nexus, Connector e Core instalados no Windows.
As regressões cobriram ticket de uso único, expiração, origem, desafio,
revogação, confirmação de troca de escritor e revalidação dentro da
transação de entrada. O relay de leitura recusou outras threads,
listagem global e métodos que iniciam trabalho. A retomada salva
revalidou o perfil e o histórico selecionado.

O ledger registra SI-019 como `IMPLEMENTED` com o ensaio de múltiplos
leitores no Pi e o ensaio de duas threads no Codex já arquivados. A
bateria atual usou peers sintéticos e loopback. Os cenários de campanha
SI-T-G06, G07, G08 e G10 ficam pendentes. O registro dispensa migração.
[Casos, versões e hashes](si019-current-broker.json)
