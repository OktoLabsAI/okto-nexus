# Status e responsabilidades após CN5

## Core e centralização

Manter `nexus-connector-core==0.2.10.dev0` nesta rodada. Catálogo, avaliação técnica e identidade da instalação continuam provenientes do Core. As seis falhas confirmadas estão nas camadas consumidoras, não justificam copiar adaptadores ou mudar MCP. As verificações Pi/cópias distintas/revisão do inventário do CN4 passaram depois de ligar a fixture ao serviço de candidatos completos.

A descoberta e a avaliação locais não comprovam a publicação remota do snapshot ou o seletor real do Nexus. Preservar versão do formato e vínculo executor/candidato/revisão no contrato entre aplicativos. Não apresentar helpers locais como integração G2.

## Rastreabilidade

| CN4 | Resultado CN5 |
|---|---|
| P01 ordem Server→Core e tradução | Corrigida na etapa posterior; entrada real redige hash e há perda de namespace antes do Core. Q01/Q02 continuam abertos. |
| P02 alvo do ACK | Correção passou. Falha de leitura transitória ainda encerra publicador sem retomada por reconnect: Q04. |
| P03 diretórios longos | Cenário original passou; não foi criado novo achado de diretório. |
| P04 candidato completo/revisão por evidência | Cenários originais passaram; não foi criado novo achado de catálogo. |
| P05 reload/rotação | READY sem attach pendente passou; rotação com provider antigo aguardando não agenda substituto: Q03. |

## Pode continuar o desenvolvimento?

Sim. O desenvolvimento dos três repositórios pode continuar em paralelo com artefatos pinados. Não ratificar encerramento de CN4 nem o fluxo completo de aprovações antes de Q01/Q02. Não marcar geração/rotação e recuperação dos eventos como integralmente aceitas antes dos respectivos testes.

## Escopo externo declarado pelo executor

- `runtime.open` remoto permanece indisponível até o contrato integrado.
- Consulta/publicação persistente de decisões/intenções/recibos exige acordo com Server; não inferir retomada pós-crash a partir de tombstone RAM.
- Publicação remota do inventário e UI real não foram testadas.
- Callbacks opcionais de runtimes e política completa de renovação têm qualificação própria.
- Saída do daemon com recurso incerto exige supervisão ou transferência comprovada. Exit code 1 não conserva o loop por si.
- Providers reais, SOs-alvo/autostart e dois hosts: NOT_RUN nesta revisão.

Esses itens são pendências rastreadas, não foram contados como novos bugs reproduzidos do CN5. O executor deve entregar uma lista por owner, mantendo BLOCKED/NOT_RUN quando necessário. Não obter sucesso aparente inventando respostas do Server ou capacidades do Core.
