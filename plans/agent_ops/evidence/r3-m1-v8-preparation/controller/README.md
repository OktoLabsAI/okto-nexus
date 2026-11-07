# Preparação v8 — revisão 2, sem autorização de execução

Esta revisão acrescenta somente o guard de sessão existente ao controller v8:
se o perfil já tem session_id, ele deve corresponder a exatamente um stream
conhecido deste controller e deste binding, e esse stream não pode estar retired.
A recusa ocorre antes da reserva, persistência ou dispatch. O primeiro work sem
sessão continua com new_session=True; a continuação própria usa False.

23/23 testes sintéticos passaram em 6,55 s: os 19 anteriores mais quatro negativos
(sessão estrangeira, binding divergente, epochs ambíguos, stream retired).
Os negativos comprovam zero dispatch, zero reserva e checkpoint inalterado.
A rodada final anterior de 19 testes e sua curadoria estão preservadas em history-v1.

Carry-in 2/45.843, máximos 6 novos/8 cumulativos, preventiva proposta 200.000,
tolerância 700.000, deadline 120 s e approval/proposal SHA exatos permanecem iguais.
Nenhuma campanha, provider, HTTP, serviço, cofre ou aprovação real foi executada.
O histórico da campanha continua faulted e intocado. Confira o README de history-v1
para a interface e os limites completos, que continuam válidos.

Comando de repetição apenas sintética, com nome de saída ainda inexistente:

```powershell
rtk proxy python C:/Users/jpamb/AppData/Local/Temp/m1-controller-v8-bfx9ol3t/revision-2/run_tests.py another-synthetic-run
```
