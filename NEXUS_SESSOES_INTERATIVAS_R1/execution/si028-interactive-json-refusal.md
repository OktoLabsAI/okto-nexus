# SI-T-F05 — Combinação de terminal interativo e JSON

O executável instalado `okto-nexus.exe` rodou em um ConPTY descartável
no Windows. O comando `connect` recebeu `--json` com `-i` e, em outra
execução, com `--interactive`. Ambas terminaram com código 2 e
mostraram o erro de incompatibilidade dos argumentos.
[Relatórios e hashes](si028-interactive-json-refusal.json)

O diretório indicado para o estado do Nexus permaneceu ausente, o
projeto de teste conservou seus arquivos e o socket de observação na
porta indicada não recebeu conexão. O fluxo instalado trata o erro
do parser antes de iniciar o setup. Passaram quatro casos do parser
e o ensaio com o executável instalado.

O marco registra evidência do cenário no Windows. Reverter o commit
remove o registro, sem migração.
