## 2026-11-07 — controlador finito M1 preparado

Composição final verificada em 14 casos com Nexus/Core instalados e executor
sintético: journal próprio de setup e eventos canônicos de trabalho compartilham
orçamento e seis reservas; perda de resposta recupera os mesmos IDs; preventiva
de 100 mil e prazo de 120 s selecionam controles canônicos do trabalho ou stop
do dono temporário. Lock exclusivo impede dois controladores; reconstrução
exige reanexar as capacidades de parada correspondentes ao home selecionado.

Os journals anteriores, atribuídos e fechados, são preservados; apenas um novo
journal é aceito por reserva serial. O monitor projeta metadados/uso no SQLite,
sem exportar prompts, respostas ou credenciais. Setup encerrado exige namespace
exato e reserva própria liberada, além de close SUBMITTED/SUCCEEDED conforme o
contrato standalone do Core; SUBMITTED isolado não comprova encerramento.

A primeira rodada teve 1 falha/12 passes e intervenção de cleanup para remover
um gap artificial; permanece diagnóstica, sem aceite. Após correções do oráculo
e finalizer, passaram 13 casos e depois os 14 finais, incluindo negativo de slot
ainda ocupado. A qualificação final é 14 casos únicos, não soma de execuções;
994 inputs ficaram iguais, sem sombras de módulos de produto pelo checkout.

A proposta v7 consolida 700 mil tokens de tolerância, preventiva de 100 mil,
até seis admissões seriais e os recursos exatos. O coletor permanece operacional,
sem garantia de contador final ou corte atômico. Esta preparação não comprova
M1, provider, Connector real ou serviço do SO. A execução real ainda aguarda
autorização para conta e ações de serviço; nenhum status de aceite foi promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-controller/m1-codex-campaign-proposal-v7.json`.
