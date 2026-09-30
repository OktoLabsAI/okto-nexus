# M04/M06 — abertura autorizada antes da primeira lease

O dispatcher agora admite a exceção de bootstrap prevista no contrato R4:
uma operação runtime.open sem histórico de lease recebe o envelope
OPEN_AUTHORIZED_PENDING_LEASE, depois de revalidar autoridade, seleção,
perfil, inventário, lane e conexão. O envelope permite resolver a realização
e solicitar a primeira lease. Não contém um ExecutionContext nem permite
prepare/open no Core antes da instalação.

## Alterações

- Migração aditiva 078 persiste fase, grant e conexão escolhidos no outbox.
- AuthorizedOpenBootstrap é um tipo distinto de AuthorizedDispatch.
- A reserva passa para SENDING antes de entregar o envelope; resposta perdida
  não libera a reserva nem autoriza outro envio.
- A lease inicial usa o grant e a conexão persistidos; outro grant aprovado
  ou uma conexão substituta não podem assumir esse bootstrap.
- O ACK real de instalação associa lease ID/serial ao envio na mesma
  transação que ativa a lease. Não dispara outro open.
- O receipt Core continua sendo a prova para a projeção da sessão.
- Uma lease existente porém inaplicável não vira um novo bootstrap.

O [ADR 0005](../../docs/adr/0005-opening-bootstrap-before-lease.md) descreve
a fronteira. Não houve mudança no wire ou no wheel Core.

## Testes e artefatos

| Campanha | Resultado |
|---|---|
| Nexus R4 completo | 97 passed |
| Migrações | 7 passed |
| Instalação fora dos clones | 46 passed |
| Autoridade/falhas do bootstrap | 10 passed |
| Jornada pública de abertura/turno | 1 passed |

Os grupos se sobrepõem. O [registro](test_runs_20260930_open_bootstrap.json)
guarda comandos, hashes, fontes e manifest instalado. O wheel Nexus foi
construído em staging limpo; seus arquivos e os do Connector foram comparados
com a fonte e com os pacotes instalados. Os três usam Core 0.2.28.dev0,
SHA-256 27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c.

A primeira tentativa instalada parou antes da coleta porque o ambiente
temporário antigo estava sem 42 de 46 arquivos de jsonschema. O motivo da
perda desses arquivos não foi estabelecido. O preflight foi preservado e
um venv novo, com dependências instaladas em modo copy, passou a campanha.

A jornada pública semeia somente identidades. Registro, inventário,
realização, aprovação delegada, apply, grant, tickets, resolve/admit e
publicação de receipts passam por HTTP. WSS negocia a lane e a lease;
Core real prepara/abre e envia um turno para um peer nativo sintético.
O teste verifica zero abertura antes da lease, uma abertura após replay,
a mesma operação após resposta repetida e consumo único do orçamento.

Os casos negativos cobrem grant revogado/sem open, ticket revogado,
inventário stale, alteração de perfil/política/conexão, estado de lease
incompatível, troca de grant, takeover de bootstrap e rollback do ACK.

## Pendências

O teste chama o dispatcher explicitamente. Não prova loop owned de outbox,
daemon, resolução física de realização em produção, provider real, UI ou
hosts separados. Root/candidato do Core e qualificação são controlados pela
fixture; não representam aceite do resolver de produção.

Permanecem integração do loop e seus owners, recuperação de reservas/envios,
resolução física imediatamente antes de efeito, composição embedded/daemon,
reconciliação não vazia, decisões/input, jornadas, migração/cutover e campanhas
finais. M04/M06 e G0–G3 continuam abertos; readiness de produto não foi ativada.
