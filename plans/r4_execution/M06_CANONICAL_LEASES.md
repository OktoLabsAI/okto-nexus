# M04/M06/M07 — concessão canônica, despacho e recibo de abertura

Data: 30 de setembro de 2026. Incremento parcial do Nexus, usando Core
`0.2.25.dev0` e Connector `0.5.0.dev0` instalados. Não encerra marcos nem gates.

## Alterações

O Server agora emite grants R4 a partir de `runtime_execution_grants`, do
serviço de política existente e da operação de abertura admitida. A identidade
do registrante técnico do executor não substitui o agente do endpoint. A lane
precisa estar admitida com ticket corrente e escopo explícito `lease:request`.
Endpoint, perfil, seleção, inventário, workspace, revisões, owner e escopo
são revalidados dentro da transação de concessão.

A migração 076 persiste request, digest, grant, scope, revisão da delegação,
conexão, vencimento original e prova de aplicação. Requests repetidos devolvem
a mesma concessão sem reancorar o prazo; serial concorrente usa a transação
SQLite. `lease.applied` exige correlação com request/serial/conexão e autoridade
vigente. Uma lease emitida não coloca o runtime em READY.

Revogação da delegação e substituição do owner/lane cercam a autoridade
persistida. Desconectar não transforma REVOKED em SUPERSEDED. Reconnect de
concessão sem confirmação de aplicação exige reconciliação; não inventa ACK.
Isso é fencing no Server, não prova de revogação física instantânea no host.

O WSS real recebe `lease.renew` e `lease.applied` pelo serviço canônico. O
despacho exige lease aplicada, revalida a lane e a delegação, e consome budget
na mesma transação de RESERVED para SENDING. Repetir a reserva não consome
nem autoriza novamente. O modo da sessão vem da abertura persistida.

O ingresso de recibos de operações canônicas exige a lease e a conexão da
tentativa efetivamente despachada. Abertura, recibo, outbox e projeção de sessão
são transacionais. No Core atual, open retorna SUBMITTED com native ID depois
de registrar o handle e iniciar o pump de eventos. Esse fato pode promover
OPEN_PENDING para READY quando o owner continua atual, mantendo o estágio
original da operação; não significa conclusão de turno. Recibo de owner antigo
permanece histórico e não promove a sessão do owner novo.

## Evidência executada

- 56 testes R4 e 13 regressões existentes de grants passaram: 69 no total.
  O teste legado `authenticated_stdio` foi deselecionado explicitamente;
  sua adequação à remoção de MCP stdio continua pendente em M09/M12.
- 14 casos NS09/NS10 passaram novamente com os três aplicativos importados
  de `site-packages`, usando `python -I`, configuração pytest externa e cwd
  fora dos clones. Os testes são do checkout; o código exercitado é instalado.
- O teste vertical usa WSS/HTTP ASGI reais, concessão canônica, aplicação pelo
  Connector/Core, abertura nativa sintética, publicação do recibo, admissão de
  turno, consumo único de budget e recusa do segundo turno. Operações não são
  semeadas. Binding/perfil/inventário são fixtures aprovadas e o gate de
  qualificação de protocolo é substituído apenas no teste.
- Falhas dirigidas cobrem transação de concessão/renovação, serial concorrente,
  ACK tardio, socket substituído, revogação antes/depois de desconexão, escopo
  do ticket, mudança de política/chave, recibo sem despacho ou de outra conexão
  e rollback da projeção de sessão. Sem commit do ingresso, não há aceite.
- O wheel Nexus foi construído e seus 302 arquivos Python/SQL comparados byte
  a byte com o source, incluindo a migração 076. Os assets locais existentes
  foram empacotados sem alteração; não houve qualificação de UI ou release.

Comandos, hashes, contagens e XMLs estão em
[test_runs_20260930_canonical_leases.json](test_runs_20260930_canonical_leases.json).
A primeira suíte completa encontrou a expectativa de migrações encerrando em
075; ela foi atualizada para incluir 076 e a suíte foi reexecutada. O primeiro
teste vertical também revelou que o estágio efetivo de Core open é SUBMITTED,
não SUCCEEDED; a projeção foi alinhada ao comportamento do Core e repetida.

## Trabalho ainda obrigatório

1. Completar M01, incluindo contenção autorizada após expiração produtiva
   conforme §5.4; repetir a conformance e distribuir novo wheel quando mudar.
2. Integrar o loop de outbox, envelope inicial e seleção de grant à jornada
   pública de onboarding; configurar perfil/endpoint habilitado sem fixtures.
3. Compor o owner embedded com esse serviço e ligar o daemon/StateStore real,
   multiplexação, recuperação e reconciliação não vazia ao fluxo remoto.
4. Propagar revogação online ao runtime, recuperar ACK perdido/reboot e
   reconciliar revisões e instalação anterior sem renovar prazo artificialmente.
5. Completar eventos, projeções de todas as operações, governança de
   approval/input, UI/CLI, auditoria US English, migração e regressões amplas.
6. Qualificar providers reais, Windows/Linux, hosts separados e artefatos finais.

`R4_BUNDLE_EXECUTABLE=False` e o gate Server continuam fechados. M00/M01 estão
em andamento; estes incrementos não encerram M04/M06/M07. G0–G3 permanecem OPEN.
