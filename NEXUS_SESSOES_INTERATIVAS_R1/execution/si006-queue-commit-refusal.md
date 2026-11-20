# SI-T-B10 — Confirmação só após a fila persistir

Se o SQLite falha durante a admissão de um envio, a API de interação
responde HTTP 500 com `Cache-Control: no-store` e uma mensagem genérica.
O caso reproduzido antes da correção chegava ao erro genérico do
servidor sem essa diretiva. [Relatórios e hashes](si006-queue-commit-refusal.json)

A regressão usa uma chave estrangeira diferida no SQLite de teste.
A escrita da entrada ocorre dentro da transação, mas a restrição
impede o commit. A resposta não inclui recibo. A consulta do recibo
retorna 404 e o SQLite conserva zero entradas e zero operações de
turno. O dispatcher não envia nada ao adaptador de teste.

Após remover a falha, repetir a mesma intenção retorna HTTP 202
com sequência 1. O dispatcher entrega uma única vez e o recibo
recuperado aponta para essa operação.

Passaram seis testes com o wheel instalado, o Ruff, a checagem de
dependências com o Pip e o Twine estrito para wheel e pacote fonte.
O ensaio usa SQLite real e um adaptador sintético no caminho canônico
do dispatcher. Nenhum provedor foi chamado. Este marco dispensa
migração. Reverter o commit restaura o tratamento anterior do erro e
preserva os dados da fila.
