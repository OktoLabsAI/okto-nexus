## 2026-11-07 — Core preserva prova local de liberação no drain

Confirmado e corrigido o defeito observado no cleanup da M1: depois de close,
liberação de slot e eviction, o drain tratava o claim histórico como órfão sem
considerar a prova local de liberação. O Core agora conserva prova limitada ao
opening, epoch e geração exatos; a composição de runtimes do mesmo journal
exige um dono único e revisão estável. Nenhum claim, recibo ou ACK é reescrito.
Época/geração ausente ou ambígua, restart sem prova, capacidade esgotada,
produtores, handles tardios e outras operações pendentes continuam bloqueando.

Passaram 59 casos únicos do Core na fonte e na instalação, incluindo 24 novos.
As falhas iniciais de fixtures/oráculos foram preservadas. O mesmo teste de
integração Nexus falha no pacote histórico e passa no candidato, concluindo
DRAINED sem force/safety e preservando o histórico. A regressão instalada dos
consumidores passou em 18 casos Nexus e 26 Connector; o caso novo já integra
os 18 e não é contado novamente. Inputs ficaram iguais e os 981 payloads dos
três pacotes foram conferidos, com imports exclusivos do ambiente instalado.

Core commit `830f7ce8ef55f018fd4ad6301f97001a6a05bb93`, wheel
`4e677a205f5a486ef7134b8411983420c1c763c3dda274128a9c623ad1b1775d`.
Nexus e Connector receberam bytes idênticos dessa dependência. As versões
permanecem nas branches feature já preparadas; não houve publicação ou merge.
O serviço M1 vivo não recebeu hotpatch nem esse novo Core. Essa qualificação
isolada não transforma a tentativa real cancelada em M1 concluída.
Evidência: `plans/agent_ops/evidence/r3-released-session-drain/qualification.json`.
