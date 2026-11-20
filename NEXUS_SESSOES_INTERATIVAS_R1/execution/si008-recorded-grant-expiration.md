# SI-T-A08 — Concessão expirada antes do despacho

Uma entrada humana aceita estava na fila quando a concessão registrada
e a lease de execução expiraram. Antes da correção, a revalidação
parava no conflito de lease e deixava o recibo como `QUEUED`. O
dispatcher agora verifica a expiração da concessão registrada na
entrada e conserva o mesmo recibo como `BLOCKED_AUTH`.
[Relatórios e hashes](si008-recorded-grant-expiration.json)

O ensaio no Windows usou o Pi 0.87.1 real, o executor local do Nexus e
o wheel instalado. A API retornou HTTP 202 na admissão. Com o turno
original ainda ativo, a fixture adiantou os dois vencimentos no
SQLite descartável. A consulta retornou HTTP 200 com a mesma entrada,
revisão 1, sem operação vinculada e sem efeito possível. O sistema
conservou a concessão, a lease e a sessão. Não abriu reserva de
capacidade nem iniciou outro turno.

Após observar o bloqueio, a fixture removeu a falha de tempo para
encerrar o ambiente pelo controle canônico. O Pi registrou apenas o
turno original, que concluiu com um resultado. O recibo continuou
bloqueado mesmo depois de remover a falha. A auditoria em modo somente
leitura confirmou uma abertura, um turno, um fechamento e a referência
à concessão original no recibo.

Passaram nove regressões no wheel instalado, um ensaio HTTP com o Pi,
o Ruff, a checagem de dependências e o Twine estrito. O Pi usou um
provedor simulado, sem tráfego externo. O marco dispensa migração.
Reverter o commit restaura a classificação anterior para esse caso.
