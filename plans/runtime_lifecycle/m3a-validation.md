# M3a — Renovação independente e validação inicial pela UI

Data: 2026-10-16. Parte do M3; não conclui M2, M3 ou o gate UI-A.

## Causa reproduzida e correção

O caso L1 falhou antes da correção com `LEASE_REVALIDATION_REQUIRED`.
O trace na fronteira do Core mostrou a renovação iniciando 227 ms depois do
agendamento e o grant chegando 391 ms depois do prazo anterior. Boot, escopo,
grant, conexão, geração e serial esperado permaneciam iguais. O predicado que
recusou a aplicação foi `received_at_monotonic >= previous.deadline_monotonic`.

A renovação local agora tem um agendador separado da manutenção de histórico e
admissão da fila. Cada sessão conserva no máximo um worker de renovação; o
encerramento retém e aguarda esses workers. O próximo agendamento reserva o
custo observado de solicitação/aplicação, além da margem de meia-vida. Os TTLs,
deadlines de autoridade e checks de revogação não foram ampliados.

Expiração e grant tardio de uma sessão iniciam sua contenção e recuperação,
depois de verificar que o dono compartilhado ainda é válido. Não desligam o
executor inteiro. Falha dessa verificação continua sendo falha do dono.

O caso L2 tinha uma asserção imediata competindo com a recuperação assíncrona.
Agora aguarda o resultado do worker retido, com prazo limitado, e continua
verificando receipt, bloqueio correto e ausência de nova abertura nativa.

## Verificação automatizada

| Campanha | Resultado |
|---|---|
| Reprodução L1 antes da alteração | 1 falha reproduzida |
| Agendamento: histórico/fila bloqueados, renovação lenta e custo | 5 passaram |
| Source: lease curta, recusa isolada e recuperação de histórico | 6 passaram |
| Wheel instalada: anteriores, startup Pi/Codex/Claude, shutdown e controles | 18 passaram |
| Dependências do ambiente isolado (`pip check`) | Sem incompatibilidades |

O gate instalado conferiu os arquivos dos pacotes contra suas wheels e rodou
em diretório temporário, sem importar o source do repositório. Seus inputs
permaneceram estáveis durante a campanha. Um aviso de depreciação de Starlette/
HTTPX apareceu; não houve falha. Evidência resumida em `m3a-results.json`.

## Testes reais operados pela interface

Instalação inicial: Nexus M1 `7c4a4b5`, Core M1 `8520deb`, Windows nativo.
Banco e logs foram preservados antes do início. Meta-harness foi usado para
enviar uma mensagem privada a cada harness, proibindo ferramentas e alterações
de arquivos e solicitando uma resposta com marcador único.

| Harness | Sessão | Resultado no chat e terminal | Admissão → receipt final |
|---|---|---|---|
| Claude | `ses_d36338ec1e683aae9b2c8cb58d95d900` | `NEXUS_UIA_CLAUDE_20261016_OK`; CLOSED; 19 eventos | 54,52 s |
| Codex | `ses_c980471333df7f02c3d247d7d99e8bd5` | `NEXUS_UIA_CODEX_20261016_OK`; CLOSED; 34 eventos | 67,16 s |
| Pi | `ses_b36e0a4841ff777fd2505b15d5d076f6` | `NEXUS_UIA_PI_20261016_OK`; CLOSED; 24 eventos | 13,27 s |

As três respostas foram vistas no chat e nos respectivos terminais, com
`Turn completed`. A consulta posterior, somente de leitura, confirmou receipts
`SUCCEEDED` e birth/container records associados à abertura original. Pi usou
uma sessão previamente aquecida; seu turn foi submetido em 2,67 s.

O startup publicou host ready às 15:54:46.914 UTC. Codex, Claude e Pi concluíram
recuperação às 15:54:48.775, 15:54:50.428 e 15:55:23.350 respectivamente. Não foi
usado Retry nem confirmação manual de processos encerrados. Após os testes,
Agents mostrou os três locais online e o pool Pi com 4/5 disponíveis.

Limites e achados preservados:

- Houve saturação de CPU e falhas intermitentes de comunicação com o navegador.
  Os tempos acima são observações de três chamadas, não uma qualificação de
  desempenho nem uma atribuição causal ao Nexus.
- MCPs globais do Codex tiveram falhas externas de conexão/timeout; a resposta
  do harness chegou mesmo assim. Nenhum URL com credencial foi copiado para
  estas evidências.
- Na mesma execução M1, duas reposições do Pi falharam com
  `BINDING_NOT_AUTHORIZED`, sem birth record, e uma tentativa posterior completou
  o pool automaticamente. Os receipts finais registram o código, mas não a
  fronteira interna da recusa: causa ainda não demonstrada (L3). Não se presume
  que a correção de L1 também resolva esse achado.
- Não foram exercitados neste checkpoint crash em startup, isolamento físico
  sob falha induzida, carga de pool ou Connector remoto. Permanecem nos gates.

## Instalação atual

Após o gate instalado, o processo M1 recebeu encerramento gracioso e publicou
`DRAINED`, seguido de `Application shutdown complete`. Não houve encerramento
forçado nem reset. A wheel M3a foi reinstalada globalmente; 533 arquivos Nexus e
147 arquivos Core foram comparados byte a byte às respectivas wheels antes do
novo startup. A conferência de recuperação pós-update está em `m3a-results.json`.

Após o update, Agents mostrou Pi, Claude e Codex online sem intervenção. O
Meta-harness entregou outra chamada ao Pi, que respondeu
`NEXUS_M3A_RESTART_PI_20261016_OK`; o chat confirmou 1/1 ACK e o terminal mostrou
CLOSED, 19 eventos e `Turn completed`. A abertura fria levou 35,96 s; depois de
admitido, o turn foi submetido em 1,59 s e teve receipt final em 9,23 s. O close
também teve receipt `SUCCEEDED`. Alertas de publicação atrasada de histórico
continuaram registrados para Pi/Claude, sem bloquear essa nova chamada do Pi.
Isso confirma um fluxo observado, não encerra a investigação dessas pendências.

O Core e o Connector não receberam mudanças neste checkpoint. A próxima etapa
continua sendo a intenção durável e a exclusão de produtores atrasados (M2),
juntamente com os critérios ainda pendentes de disponibilidade independente M3.
