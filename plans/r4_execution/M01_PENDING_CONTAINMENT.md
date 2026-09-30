# Contenção durante renovação pendente

Incremento Core `0.2.28.dev0`, parte de M01/M11. Não encerra esses marcos ou
G0–G3. Resultado completo em
[test_runs_20260930_pending_containment.json](test_runs_20260930_pending_containment.json).

## Correção

O teste novo reproduziu `LEASE_UPDATE_PENDING` em interrupt durante uma
renovação que preservava toda a autoridade. A implementação também mantinha
os locks normal/controle durante a espera de CAS, impedindo contenção até o
término da espera.

Agora `renew_lease` espera efeitos em curso e reserva o bloqueio produtivo
sob os locks, mas aguarda storage fora deles. Novas operações produtivas
revalidam esse bloqueio após adquirir o lock e imediatamente antes do efeito.
CAS e reconciliação continuam possuídos pelo runtime após cancelamento.

Interrupt, close e respostas estritamente negativas continuam autorizados
durante renovação do mesmo escopo, grant e conexão, somente se a ação
permanecer concedida nos dois contextos. Expiração produtiva não muda essa
regra. Conexão/geração ou escopo diferentes, ação retirada e revogação
recusam o contexto anterior. Owner durável observado como superseded
permanece bloqueado. Renovação tardia não confirma sessão drenando/fechada.

## Evidência

Doze casos novos mantêm a barreira CAS fechada durante as asserções: quatro
ações antes/depois de expiração, mais quatro recusas de autoridade. Eles
passaram também com Core instalado fora do clone. A regressão dirigida com
leases, close e casos C3/C7 passou 67 testes. O manifesto registra as suites
completas e integração instalada, comandos, XML, skips e hashes, sem somar
suites sobrepostas.

O wheel `nexus_connector_core-0.2.28.dev0-py3-none-any.whl` tem SHA-256
`27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c` nos três
repositórios. Pins, lock e verificação de inventário estão alinhados. O
verificador do wheel passou; os 91 arquivos Core, 316 Nexus e 51 Connector
instalados correspondem byte a byte à fonte registrada.

## Limites e próximos trabalhos

A barreira retém a porta CAS antes da escrita, permitindo verificar os locks
do runtime. Não demonstra admissão paralela por um writer SQLite bloqueado.
Operações públicas ainda aguardam seu journal; shutdown proprietário é a
trilha independente quando storage impede essa admissão.

Qualificação/peers continuam sintéticos. Completar conformance restante do
Core, onboarding público, owners embedded/daemon e loop de outbox, seguida
de reconciliação, domínio, jornadas e qualificação real. Nenhuma flag R4 ou
prontidão Server foi promovida por este incremento.
