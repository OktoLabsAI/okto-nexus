# M3b — HTTP independente da descoberta inicial

Data: 2026-10-16. Repositório afetado: Nexus `feature/v0.3.1`. Core 0.0.12 e
Connector 0.0.10 permanecem nos artefatos M2e, sem alteração neste checkpoint.

## Causa e mudança

A campanha real M2e revelou aproximadamente 2m20s sem HTTP enquanto a
descoberta inicial calculava a identidade de build do Pi. O stack dump e o
lifespan confirmaram a dependência: `inventory.start()` aguardava o scan antes
de abrir o servidor. Uma falha nessa primeira descoberta também impedia
iniciar a rotina periódica de novas tentativas.

O startup agora aguarda somente a aquisição da geração de inventário. O scan
inicial e suas novas tentativas são executados pelo mesmo worker retido de
inventário. Nenhum snapshot persistido é promovido a fresco por esse ajuste;
as regras de admissão, autorização e validade de inventário continuam valendo.

O boot de endpoints aprovados também tem um owner retido. Ele aguarda uma
observação utilizável em segundo plano e preserva as chaves de idempotência
existentes. Falhas excepcionais têm nova tentativa; cancelar o observador de
shutdown não cancela a thread. O coordenador informa o produtor pendente e não
libera o dono do store antes de seu término. Shutdown anterior à observação
válida impede iniciar o boot. Reset só substitui um owner já encerrado.

## Validação

Campanha instalada: **103 testes aprovados**, sem falhas ou skips, exit code
zero. Ambiente isolado com `-I`, cwd temporário, comparação dos bytes dos três
pacotes e `changed_inputs=[]`. Dependências: 48 distribuições compatíveis.

Wheel Nexus 0.3.1:
`76412c9687ee647cc1ad96d75b0ace3caec3a280fe708d0e0873bc5612f7bf7d`.
Os 534 arquivos do pacote também foram comparados ao source final. Core e
Connector mantêm os hashes M2e. Evidência: `m3b-results.json` e diretório local
`build/runtime-lifecycle-m3b-installed/`.

Cobertura: HTTP durante scan retido, snapshot anterior ainda stale, retry
inicial, mudança de geração/dono/revogação, cancelamento do observador, boot
aprovado/idempotente, falha transitória do boot, reset e shutdown.

Os fixtures que precisam de candidatos passaram a aguardar explicitamente sua
publicação. Isso separa a prontidão da interface da disponibilidade de cada
recurso, sem depender da velocidade da máquina para ordenar o teste.

## Instância real e achado que precede a atualização

A instalação global continua em M2e. Durante a preparação da atualização,
sem reiniciar o servidor, o Pi voltou a RECOVERING. Snapshot SQLite e logs
foram preservados em `build/runtime-lifecycle-m3b-live/`; não são commitados.
O servidor continua com PID 20896 e geração 66. A atualização global M3b foi
adiada para investigar a recorrência sem apagá-la com um restart.

Evidências disponíveis: liberações de sessões por recuperação a partir de
19:45:47 UTC; `NativeAdapterError`/`CONFIG_ERROR` registrado a partir de
19:47:21 UTC; Pi ainda RECOVERING às 19:48:22, enquanto Claude e Codex constavam
READY. A amostra posterior de CPU mediu 100% da máquina, com vários processos
externos ao Nexus ativos. Isso é contexto de carga, não prova causal.

O código `EmbeddedAgentRecovery.fail` usa `errors.setdefault` e grava a primeira
exceção também como erro da tentativa atual. Portanto, os logs repetidos de
CONFIG_ERROR não demonstram que todas as tentativas falham pela mesma causa.
Preservar primeira causa e causa atual é um critério pendente de M3; essa
observabilidade e a reprodução da recorrência são o próximo passo.

Na verificação real anterior à recorrência, Graph mostrou os três harnesses
conectados mesmo com atividade de chat antiga. Nenhuma nova chamada ao provedor
Codex foi feita. Isso não qualifica o pacote M3b na instância global.

## Limites

Esta mudança remove a descoberta do caminho de abertura HTTP. Não reduz ainda
o custo do scan nem torna o inventário incremental por harness. A qualificação
de desempenho e esse isolamento continuam em M3/M4/M7. O restante do gate UI-A
e a resposta real bem-sucedida do Codex continuam pendentes; M2e identificou
quota do provedor, sem tentativa de contorno.
