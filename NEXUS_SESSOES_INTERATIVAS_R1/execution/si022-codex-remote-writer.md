# SI-022 e SI-031 — Escrita no terminal Codex hospedado pelo Connector

`okto-nexus session attach --write` usa o login humano para selecionar a sessão e pedir escrita. O Nexus verifica a capacidade atual do Connector no broker e revalida o escritor, a sessão e a autorização antes de gravar cada ação. Um pedido de escrita exige a versão qualificada do app-server e a disponibilidade da fila. A abertura em leitura continua disponível com a capacidade de leitura.

O terminal envia texto à fila do Nexus. A reorientação e a interrupção exigem confirmação para o turno selecionado. A interrupção pausa a fila antes do despacho. A referência ao recibo é exibida antes do pedido e a última referência reaparece ao sair. `session receipt` usa a sessão, a geração e a intenção originais com o mesmo login de operador.

O teste com HTTP, WebSocket, daemon Connector e banco temporário descartou a resposta do WebSocket após o registro da mensagem. A consulta recuperou o único registro. A segunda abertura reorientou o turno correto. A terceira recusou um alvo trocado, cancelou uma revisão e admitiu uma única interrupção depois da pausa da fila. O processo nativo e a construção do inventário foram simulados nesse cenário.

O ensaio instalado com o frontend Codex 0.170.0, app-server Codex 0.157.0 e Windows ConPTY abriu o escritor durante um turno. Após a conclusão, uma mensagem digitada no terminal originou o turno seguinte no mesmo PID e na mesma thread. O frontend exibiu a resposta, restaurou o console após Ctrl+] e o CLI recuperou o recibo `ACCEPTED_NATIVE`. Os dois turnos usaram respostas determinísticas em loopback.

Um segundo ensaio abriu o terminal depois que o Nexus registrou a conclusão do turno anterior. A nova mensagem também usou o PID e a thread originais, exibiu o resultado e preservou o recibo após a saída. Em um ensaio separado, o mesmo app-server reportou estado ocioso e o Nexus aprovou cinco revisões de leitura e cinco de escrita após a conclusão. O HTTP 409 observado uma vez na campanha anterior não se repetiu. A causa daquela recusa permanece indeterminada.

Passaram 63 testes de regressão instalados, incluindo os cenários remotos, e 11 testes instalados de reset e inventário. A rodada posterior passou os quatro testes remotos com uma verificação adicional de reabertura em leitura após a conclusão. A reabertura mostrou o turno original encerrado, conservou o diretório remoto e não criou nenhuma operação. O wheel passou pelo Twine estrito e contém os sete módulos alterados byte a byte. A checagem do lock offline passou e o Ruff manteve apenas apontamentos já presentes na linha de base.

Os pins de Core e Connector seguem os do candidato anterior. A mudança usa tabelas e comandos existentes e dispensa migração. Para reverter, use um revert do commit no Nexus e mantenha o banco e os recibos da sessão.

SI-022 e SI-031 permanecem em andamento. A validação em máquinas distintas, TLS entre hosts, perda física de rede, apresentações remotas de Pi e Claude e a oferta de abertura no próprio CLI do Connector continuam pendentes. [Dados do teste e artefatos](si022-codex-remote-writer.json)

## Interrupção no visualizador nativo com Connector neste Windows

Com o Nexus `7fb92db1`, o Connector 0.0.15 e o Core 0.0.16 instalados, o visualizador Codex 0.170.0 abriu a thread que o app-server 0.157.0 já executava. Cancelar a revisão no primeiro visor manteve o turno e a fila intactos. O segundo visor confirmou a interrupção do mesmo turno. A observação no envio ao app-server verificou que a pausa da fila já estava gravada e que a entrada retida ainda não tinha operação de envio.

Os dois visores se desanexaram com os modos do console restaurados. O CLI recuperou o recibo da interrupção depois da saída do segundo visor. A retomada explícita despachou a entrada original em um turno separado. A auditoria, em modo somente leitura, ligou a interrupção ao primeiro turno, confirmou o resultado do segundo na mesma thread e encontrou uma abertura nativa, um fechamento canônico e zero violações de chave estrangeira. [Comandos e hashes](si022-codex-remote-writer.json)

Passaram seis regressões com os wheels instalados. A rodada nativa chegou à retomada, e o roteiro falhou ao ler a resposta HTTP antes de o resultado aparecer. A auditoria posterior confirmou o resultado persistido. A repetição com a espera corrigida foi recusada na anexação quando o canal do Connector estava desconectado. Em uma tentativa anterior, a segunda revisão não apareceu no mesmo visor durante a janela do ensaio. O ensaio usou respostas de modelo simuladas em loopback. [Matriz de capacidades](si027-session-capability-matrix.md)

## Recuperação da consulta de inventário durante um turno

A auditoria da repetição anterior separou duas transições. O Nexus revogou os tickets da configuração antiga antes de abrir a sessão. A desconexão posterior deixou uma prova de retomada na geração da sessão ativa, com o ticket e a lease ainda válidos. Os logs também registraram uma falha de transporte ao consultar uma atualização de inventário. O gatilho exato da desconexão daquela rodada segue indeterminado.

O Connector passa a aguardar a próxima consulta do mesmo produtor quando a resposta da consulta de inventário se perde. O Nexus devolve a entrega já registrada para aquela geração. A publicação só confirma a entrega depois de uma observação nova. Recusas de autoridade, geração e protocolo ainda encerram o fluxo. O wheel anterior reproduziu a perda do canal. Passaram 46 testes de código-fonte, 59 com o Connector instalado e três testes HTTP de escopo, revogação e confirmação no Nexus. [Comandos e hashes](si022-codex-remote-writer.json)

O ensaio instalado descartou a resposta depois de o Nexus registrar a entrega de inventário. O mesmo canal recuperou uma única entrega enquanto o Codex mantinha a execução. Depois de cancelar uma revisão e sair do primeiro visor, o segundo visor confirmou a interrupção do turno exato. A fila já estava pausada no envio do controle. O recibo sobreviveu ao detach e a retomada explícita concluiu um segundo turno na mesma thread e no mesmo processo. O fechamento canônico encerrou o app-server. A auditoria confirmou o resultado, uma única abertura nativa e a integridade dos dois bancos.

A primeira tentativa usou o cliente de operador numa rota que exigia a identidade do agente. A rodada final usou a credencial descartável do agente criado pelo teste. O ensaio qualificou a interrupção pelo visualizador Codex via Connector neste Windows, com respostas simuladas em loopback. A correção dispensa migração. Para reverter, reverta a mudança do Connector e restaure o wheel anterior fixado no Nexus. A prova da reorientação foi registrada no ensaio seguinte. [Reorientação pelo visualizador](si022-codex-remote-native-steer.md)
