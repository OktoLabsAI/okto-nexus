## 2026-11-07 — correção de caminho após primeiro setup real

O primeiro setup real terminou seu turno e salvou o Finish, mas o CLI retornou
PROFILE_DRIFT: comparava literalmente o provider home aprovado com barras `/`
e o mesmo caminho canônico Windows com `\`. A leitura do recibo confirmou o
mesmo Server, binding, instalação e projeto. Houve uma reserva produtiva e
22.775 tokens observados; o monitor registrou fechamento e liberação do slot.

Corrigida somente a comparação dos separadores em caminhos locais absolutos.
Não há leitura do home, resolução de links, alteração de caixa ou remoção de
`..`. A regressão falha no pacote histórico e passa no corrigido: 14 testes na
fonte e 14 no pacote instalado, incluindo retomada somente por GET e recusas de
caminhos distintos, relativos ou ausentes. Os inputs da qualificação ficaram
inalterados. A tentativa inicial de build sem setuptools foi preservada;
o build offline posterior concluiu normalmente.

O novo cliente tem apenas um payload de produto alterado entre 691. O Server
em execução, o Codex e os pacotes Core/Connector permanecem nos hashes originais.
A retomada será explicitamente cliente corrigido/Server original, pelos mesmos
recibos, sem repetir setup ou acrescentar ações de serviço. A correção e o setup
isolado não comprovam o ciclo produtivo completo M1 nem promovem aceite.
Evidência: `plans/agent_ops/evidence/r3-m1-path-normalization/qualification.json`.
