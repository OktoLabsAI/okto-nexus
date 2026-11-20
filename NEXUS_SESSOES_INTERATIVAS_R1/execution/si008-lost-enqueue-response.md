# SI-T-B14 e SI-T-B15 — Resposta perdida e repetição da intenção

O teste abriu uma sessão descartável, pausou a fila e enviou uma
mensagem por HTTP em loopback. A fixture deixou a admissão gravar a
entrada no SQLite e interrompeu a conexão antes de entregar o corpo
da resposta. O cliente recebeu um erro de transporte.
[Relatório e hash](si008-lost-enqueue-response.json)

O servidor conservou uma entrada `QUEUED` na sequência 1, sem
operação vinculada. Consultar o recibo devolveu HTTP 200. Repetir a
mesma intenção devolveu HTTP 202 com o mesmo recibo e a mesma
sequência. Repetir o identificador com outro texto devolveu HTTP 409.
O recibo, o conteúdo e a impressão digital da entrada ficaram intactos.

Ao retomar a fila, o dispatcher fez uma única entrega ao peer. A
operação canônica continha o texto original, incluindo quebra de
linha e acento. Passaram o teste HTTP e o teste de armazenamento com
o wheel instalado, além do Ruff. O peer era sintético e a queda foi
injetada somente no servidor de teste.

O marco acrescenta uma regressão e atualiza o ledger. Reverter o
commit remove a cobertura, sem migração.
