# SI-010 e SI-026 — Reorientar uma sessão Claude no Connector

O Nexus agora reconhece o evento de geração do terminal Claude hospedado pelo Connector. A revisão exige o mesmo dono, geração, sessão e operação que emitiram o evento, além da extensão de reorientação negociada no R4. O teste anterior com o binário real encontrava o turno em geração, mas a revisão ficava indisponível porque esse evento era aceito apenas para sessões locais.

O ensaio com os wheels instalados usou Claude 2.1.328 no Windows ConPTY, um perfil descartável e um modelo simulado em loopback. Antes da geração, a revisão ficou indisponível. Uma revisão de fila desatualizada recebeu HTTP 409 antes de qualquer escrita no terminal.

Após a confirmação válida pelo CLI, o Connector registrou um Esc e uma mensagem substituta no mesmo processo. O roteiro simulou a perda da resposta HTTP e da confirmação local após a escrita. A recuperação mostrou a interrupção confirmada e a entrega ainda incerta. O resultado posterior mudou o mesmo recibo para `ACCEPTED_NATIVE`. Repetir a confirmação recuperou a operação existente. O visualizador leu o resultado da mesma sessão e o encerramento canônico terminou o processo. [Evidências e hashes](si026-claude-remote-managed-steer.json)

Na suíte ampliada, passaram 89 de 90 regressões, incluindo os dois formatos de evento remoto e a recusa sem negociação. O teste local de confirmação perdida falhou no ponto em que esperava a resposta do hook simulada. A repetição isolada passou com o wheel candidato e com o anterior. A validação estrita dos wheels, o lock e os pins passaram.

O marco dispensa migração. Reverter o commit do Nexus restaura a revisão anterior. A interrupção remota independente, a validação entre máquinas e a campanha com provedor real continuam pendentes.
