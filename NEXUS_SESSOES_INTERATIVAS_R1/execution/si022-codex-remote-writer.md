# SI-022 e SI-031 — Escrita no terminal Codex hospedado pelo Connector

`okto-nexus session attach --write` usa o login humano para selecionar a sessão e pedir escrita. O Nexus verifica a capacidade atual do Connector no broker e revalida o escritor, a sessão e a autorização antes de gravar cada ação. Um pedido de escrita exige a versão qualificada do app-server e a disponibilidade da fila. A abertura em leitura continua disponível com a capacidade de leitura.

O terminal envia texto à fila do Nexus. A reorientação e a interrupção exigem confirmação para o turno selecionado. A interrupção pausa a fila antes do despacho. A referência ao recibo é exibida antes do pedido e a última referência reaparece ao sair. `session receipt` usa a sessão, a geração e a intenção originais com o mesmo login de operador.

O teste com HTTP, WebSocket, daemon Connector e banco temporário descartou a resposta do WebSocket após o registro da mensagem. A consulta recuperou o único registro. A segunda abertura reorientou o turno correto. A terceira recusou um alvo trocado, cancelou uma revisão e admitiu uma única interrupção depois da pausa da fila. O processo nativo e a construção do inventário foram simulados nesse cenário.

O ensaio instalado com o frontend Codex 0.170.0, app-server Codex 0.157.0 e Windows ConPTY abriu o escritor durante um turno. Após a conclusão, uma mensagem digitada no terminal originou o turno seguinte no mesmo PID e na mesma thread. O frontend exibiu a resposta, restaurou o console após Ctrl+] e o CLI recuperou o recibo `ACCEPTED_NATIVE`. Os dois turnos usaram respostas determinísticas em loopback. Uma tentativa anterior recebeu conflito durante a abertura logo após a conclusão do turno. A reabertura nessa transição ainda precisa ser qualificada.

Passaram 63 testes de regressão instalados, incluindo os cenários remotos, e 11 testes instalados de reset e inventário. O wheel passou pelo Twine estrito e contém os sete módulos alterados byte a byte. A checagem do lock offline passou e o Ruff manteve apenas apontamentos já presentes na linha de base.

Os pins de Core e Connector seguem os do candidato anterior. A mudança usa tabelas e comandos existentes e dispensa migração. Para reverter, use um revert do commit no Nexus e mantenha o banco e os recibos da sessão.

SI-022 e SI-031 permanecem em andamento. A validação em máquinas distintas, TLS entre hosts, perda física de rede, apresentações remotas de Pi e Claude e a oferta de abertura no próprio CLI do Connector continuam pendentes. [Dados do teste e artefatos](si022-codex-remote-writer.json)
