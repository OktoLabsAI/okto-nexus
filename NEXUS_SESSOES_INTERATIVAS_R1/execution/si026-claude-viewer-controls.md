# SI-026 e SI-031 — Reorientação e interrupção no visualizador Claude

No Windows, `nexus session attach --write` permite revisar a reorientação com Ctrl+R no compositor e a interrupção com Ctrl+X no visualizador. A revisão apresenta o turno e o efeito. Ctrl+Y confirma e Ctrl+N cancela. A confirmação usa a mesma geração, autoridade de escrita e revisão da fila. O CLI mostra a referência do recibo e, se a resposta se perder, consulta a intenção original.

Os dois ensaios com os wheels instalados passaram com Claude Code 2.1.328 real em ConPTY, com Nexus e Connector na mesma máquina Windows. O modelo recebeu pedidos apenas em loopback. A reorientação cancelou o turno revisado e enviou uma substituição. A perda de duas confirmações foi simulada e o recibo foi recuperado sem repetir o envio. A interrupção pausou a fila antes do Escape e conservou o item pendente até a retomada explícita. A auditoria confirmou uma abertura e um fechamento por sessão, bem como a integridade dos bancos.

Passaram 289 testes na suíte de código-fonte de interação de sessões e 88 testes direcionados nos wheels instalados. O teste de terminal exclusivo de POSIX foi ignorado nessas rodadas no Windows. [Cenários, comandos e hashes](si026-claude-viewer-controls.json)

No executor local do Nexus, o mesmo pacote passou por dois anexos em ConPTY na mesma sessão. O segundo anexo interrompeu o turno criado pelo primeiro. A fila pausada registrou o único recibo de entrega ainda incerto, ligado ao turno de substituição. O fechamento canônico encerrou o processo e o banco passou na verificação de integridade. O teste iniciou no handler de anexação do CLI com um vínculo de teste obtido pela API.

Os ensaios usaram o perfil `plan` revisado, ferramentas bloqueadas e atalhos padrão. O ledger mantém em aberto as validações com provedores e participantes. O Connector entre máquinas e as medições adicionais em macOS ficam para outro corte. Este marco dispensa migração. Para desativar os novos atalhos, reverta o commit de implementação do Nexus. A fila e os recibos já registrados permanecem disponíveis. [Como usar](../../docs/terminal-work.md#follow-or-reorient-a-managed-claude-session)
