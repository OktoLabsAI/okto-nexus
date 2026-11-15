# Consentimento do vault após state.reload

O daemon preservava o booleano de consentimento capturado antes da aprovação no CLI. A correção atualiza apenas o gate do mesmo RestrictedFileVault compartilhado por host, runtime e controles existentes. Não reabre o backend, não lê segredo no refresh e não recria clientes. Somente True literal autoriza; False, ausência e valores não booleanos recusam os próximos acessos. Isso não revoga material já entregue ou autoridade canônica.

16 testes passaram: nove casos novos e sete regressões do vault. O runner usa fonte Connector explícita sobre dependências do pacote R, sem modificar esse pacote. Os testes usam sentinela e estado temporários, sem serviço, rede, credencial pessoal ou provedor. Ruff F e diff check passaram; o root revisou o delta. Não é qualificação instalada nem aceite de campanha real.
