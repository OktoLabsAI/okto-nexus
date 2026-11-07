# Proposta M1 v2 — entrega útil e permissão nativa

Esta revisão substitui apenas o roteiro proposto. A v1 e seu manifesto permanecem intactos. Nenhum serviço, provider, binário Codex ou fixture foi executado; a pergunta sobre o teto rígido/operacional de tokens ainda não teve resposta.

O trabalho agora lê `numbers.csv` do projeto e produz `report.json` com `row_count=4`, `sum=10` e SHA-256 do arquivo de entrada. Cada topologia tem um destino próprio: `m1-campaign/deliverables/local/report.json` ou `m1-campaign/deliverables/connector/report.json`, irmãos dos respectivos diretórios de projeto, todos dentro do novo Temp autorizado da campanha. Os diretórios de entrega só serão criados após autorização; arquivos existentes nunca serão sobrescritos.

O destino deve estar fora dos writable roots efetivos do projeto. Isso pode provocar um pedido nativo legítimo ao tentar gravar, sem mudar sandbox, permissões, writable roots ou política global. A futura decisão humana cobre somente o comando realmente apresentado e os dois caminhos exatos daquela etapa. Uma recusa não pode ser contornada por outro tool, caminho ou comando.

Não há garantia de que a política efetiva produza um pedido. Se a gravação for admitida diretamente, o resultado útil pode ser validado, mas a etapa de decisão nativa M1 continua pendente. O teste não transforma um texto do modelo ou uma gravação bem-sucedida em prova de aprovação.

Mantêm-se os ciclos local e Connector, identidade humana do operador, checkpoints anteriores à submissão, perda de resposta declarada, recuperação pelos mesmos IDs, retorno ao resultado e limpeza canônica. O máximo continua sendo seis admissões produtivas, contando testes de conexão; não foram adicionados turnos para perseguir uma aprovação.

Os três wheels SVC07 candidatos agora têm hashes exatos no JSON, mas isso não representa aceite final da qualificação em curso. A proposta das duas tarefas Windows fica separada: é infraestrutura vazia, sem provider ou inferência. Autorizar essas tarefas não autoriza automaticamente M1.

O teto rígido de 200 mil tokens continua sem garantia no fluxo atual. A alternativa operacional em esclarecimento interromperia preventivamente aos 100 mil reportados e recusaria novos trabalhos; atrasos de observação/interrupção ainda podem causar overshoot. Não haverá goal persistente nem uso da conta antes da resposta e da autorização explícita.

O JSON é o roteiro completo revisado, com caminhos absolutos, prompts, gates, comandos, pins candidatos e vínculos de hash à v1. Esta nota não substitui suas condições.
