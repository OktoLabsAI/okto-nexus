# SI-T-D12 — Comando registrado por extensão nativa

O Pi 0.87.1 registrou `fixture-only-command` numa extensão sintética do
perfil descartável. A consulta nativa `get_commands` retornou o nome e a
origem `extension`. A sessão usou os três wheels instalados no Windows,
o transporte R4 em loopback e um provedor simulado.
[Comandos, hashes e observações](si015-native-extension-catalog.json)

1. O catálogo do Nexus omitiu o comando. Uma tentativa direta de enviá-lo
   pela API de comandos recebeu HTTP 422.
2. No Edge, digitar `/fixture-only-command` e pressionar Enter preservou
   o rascunho e gerou zero requisições de execução. Usar o comando
   autorizado `/status` na mesma sessão gerou uma requisição e HTTP 200.
3. A extensão registraria sua execução num arquivo local. O arquivo
   continuou ausente. A operação original produziu um resultado, e o
   fechamento canônico encerrou a sessão.
4. A auditoria em modo somente leitura encontrou um processo nativo,
   uma abertura, uma operação de trabalho, um fechamento, um resultado
   e zero entradas na fila. As verificações de integridade e chaves
   estrangeiras do SQLite passaram.

Um cenário integrado com o Pi e o Edge passou. A extensão e a resposta
do provedor foram simuladas. O teste verificou a autoridade do catálogo
para esse comando e reutilizou o mesmo build das regressões registradas
no SI-T-D10. [Regressões do mesmo build](si016-stale-catalog-settings.md)

Este marco atualiza evidências e ledger. Reverter o commit reverte o
registro, sem migração ou alteração de instalação.
