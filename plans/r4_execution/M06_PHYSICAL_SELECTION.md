# Seleção física aprovada e composição Core — incremento parcial M03/M06

O Connector `b1d87106f1ed3abffd438e81ae0ca2fb4383a0af` acrescenta o vínculo
R4 aprovado ao StateStore, separado dos bindings legados e dos grants de
execução. O schema passa de 3 para 4 sem fabricar aprovações para registros
antigos. O ACK de publicação compara a configuração completa e preserva
`BOUND` em replay; o resultado de apply só é persistido contra a realização
publicada do mesmo Server/executor/agente.

O resolver valida o envelope pelo codec público Core e confere binding,
workspace, candidato, inventário e revisões. Resolve somente recursos do
host, verifica o snapshot aprovado, identidade da pasta, fingerprint,
arquitetura registrada e build portátil. Para Pi, alterações no conteúdo do
pacote são detectadas mesmo quando Node e `cli.js` continuam iguais.

`CoreRuntimeHost.build_r4` congela a seleção antes de esperar, revalida após
inicializar journal/ledger e antes/depois do callback de ambiente. O cache
usa Server/executor/binding/sessão e exige a mesma seleção. Compor o runtime
não instala lease nem executa prepare/open.

## Jornada integrada e testes

A jornada de WebSocket real agora usa `stage_local_realization`, publicação
HTTP e ACK, o resultado real do apply e a composição do host. O teste deixou
de fornecer diretamente o mapa de paths ao Core. Confirma recusa de contexto
antes da lease, workspace aprovado no prepare, uma abertura nativa e o ciclo
open/submit/steer/interrupt/close com receipts correlacionados.

| Campanha | Resultado | Alcance |
|---|---|---|
| Connector dirigido | 27 passes | Persistência, schema, escopo/revisões, drift e espera no host |
| Connector completo | 278 passes, 2 skips | Regressão; skips e causas preservados |
| Nexus R4 | 103 passes | Inclui a jornada pública WSS |
| Jornada WSS isolada | 1 pass | Mesmo caso contido na suíte R4 |
| Pacotes instalados, fora dos clones | 55 passes | Seleção, host, conexão, bootstrap e leases |

Os grupos se sobrepõem. Os dois skips do Connector são a capability de sessão
cujo peer de laboratório não oferece a autoridade completa e o caso de shim
para plataforma não Windows. A primeira rodada dirigida teve duas falhas de
fixture: referência de candidato inválida no schema e diretório privado do
runtime inexistente. As fixtures foram corrigidas e os XMLs preservados.

O [manifesto coordenado](test_runs_20260930_physical_selection.json) registra
comandos, hashes, instalação e limites. Os módulos instalados foram comparados
byte a byte com os wheels; Nexus e Connector também foram comparados com
as fontes de produção. O wheel Core continua `0.2.28.dev0`, SHA-256
`27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c`.
Produção Nexus, Core e contrato wire não mudaram neste incremento.

## Trabalho restante

O daemon e a CLI ainda precisam chamar esses serviços, persistir o executor,
renovar credenciais/revisões aprovadas e compor perfil/ambiente canônicos.
Também faltam reconciliação não vazia, projeção durável de erros/receipts/eventos,
as sete ações integradas e o owner embedded. O teste usa peer nativo e
qualificação sintéticos; não aceita daemon, provider, Linux ou hosts separados.

Binários anteriores recusam o schema 4. Backup verificado e ensaio completo de
upgrade/rollback permanecem em M12. Contenção sob alteração concorrente do
filesystem, limites globais e a matriz provider/SO/hosts precisam das campanhas
de M11/M13. `R4_BUNDLE_EXECUTABLE` e `remote_execution_ready` permanecem falsos.
M00/M01 e G0–G3 continuam abertos.
