# SI-T-B12 e SI-T-H08 — Fila continua sem terminal no Windows

O Nexus instalado abriu uma sessão com o Codex app-server 0.157.0.
O visualizador 0.170.0 anexou com escrita em ConPTY. A API registrou
uma mensagem na fila enquanto a primeira resposta estava retida.

O ensaio encerrou o pseudoconsole em um caso e somente o processo de
apresentação em outro. Nos dois casos, o Windows confirmou a saída do
visualizador. O recibo passou a `DETACHED`. O mesmo app-server continuou
ativo com a mesma thread, geração, autorização e turno. A fila conservou
a mensagem e permaneceu sem pausa.

Os dois turnos terminaram antes de abrir um novo terminal. Ao reanexar,
o terminal mostrou o resultado da mesma thread e saiu pelo controle de
desanexação. Não houve transferência de controle nem novo prompt.
Cada caso teve dois inícios de turno e duas respostas simuladas em
loopback. O controle canônico encerrou o app-server.
[Resultados dos dois casos e hashes](si032-queue-without-terminal.json)

A primeira repetição completou os turnos e exibiu o histórico, mas
a saída revelou que faltava o diretório do serviço na fixture de
reanexação. A fixture passou a fornecer o diretório descartável e
os dois casos passaram. A auditoria SQLite confirmou os resultados.

O ensaio cobre o fechamento local em ConPTY e a desconexão direta.
Expiração sob falha de rede e execução entre máquinas seguem em
aberto. O marco não exige migração. Reverter o commit remove o registro.
