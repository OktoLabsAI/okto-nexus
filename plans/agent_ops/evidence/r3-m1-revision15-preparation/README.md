Revision15 — preparação offline finita

Local útil13 em nova sessão e continuação14 somente após sucesso canônico na mesma
sessão. IDs remotos15/16 pertencem à alocação, mas seus seletores permanecem fechados
até qualificação separada. A autorização humana existente cobre700k tokens; esta
revisão técnica explicita12 reservas históricas +4 novas =16, sem novo consentimento
humano de hash. Carry295262, preventiva500k e tolerância700k permanecem explícitos.

Sete registros máximos observados (3 históricos+4 novos): snapshot1s, inicialização2s,
margem1s, poll17s/fresh18s/cadence22s e alvo200ms. São limites operacionais, não novo
critério de aceite. Deadline de trabalho600s. CLI readiness5s é opt-in explícito,
sem novo start/replay de POST; padrão do produto permanece uma inspeção.

Pacote próprio de archives Nexus46ba5c31/Connector645d7bd5 e Core7810/d881 existente.
1002 payloads verificados; probe60 passou.48 testes de preflight instalado,6 da
composição e14 deltas do controlador (12+2 rodadas) ficam separados, sem somar casos
distintos. Import real do prefixo work/facade passou sem chamar handler ou controller.

Roteiro: prepare → upgrade-plan → seleção técnica do plano exato → upgrade-apply →
install/start uma vez45s e observação passiva permitida180s → watcher de três processos
→ revisão de grant (apply só se expirado e selecionado) → útil13 → continuação14
condicional → stop normal → cleanup proof → uninstall → final presence → close direto.
Native decision usa private/native-decision.json, sempre revisão do pedido real.

Se uma falha deixar turno nativo admitido ativo e stop45 continuar draining, a
autorização existente permite contenção normal canônica exata: observar owner,
coorte, sessão/operação/turno; root revisa e seleciona um resolve+admit de interrupt,
sem novo turno ou replay de decisão. Session close apenas se necessário; stop e
provas físicas separados. A referência request12 não é comando reexecutável.

Request12 permanece CANCELLED e seu controle interrupt SUBMITTED; original checkpoint
e falhas não mudam. Cleanup não prova settlement. Falha antes de uso final exige
companion contábil pós-saída separado, preservando mínimo observado/unsettled.
Nenhuma execução de serviço, provedor, grant ou migração foi feita na preparação.
