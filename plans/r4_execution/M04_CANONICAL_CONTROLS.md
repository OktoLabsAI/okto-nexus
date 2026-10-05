# M04 — steer e interrupt pela admissão canônica

Data: 30 de setembro de 2026. Incremento parcial de NS06/M04, com o mesmo
Core `0.2.26.dev0` já publicado. Nenhum marco ou gate de produto foi fechado.

## Implementação

- Resolução e admissão aceitam steer e interrupt para a sessão existente.
  Core fornece a regra de targeting; não existe tabela de adapters no Nexus.
- A projeção HTTP → NXL coloca o ID nativo no hash calculado pelo Core.
  Mudança de alvo muda o hash. Para um adapter sem ID, `current_run` é
  explícito; alvo ausente não escolhe implicitamente um turno.
- O dispatcher confere hash, escopo e codec do frame completo antes do
  consumo de budget e do commit de `SENDING`. O host recebe esse frame
  validado no resultado de autorização.
- Interrupt pode usar a lease aplicada depois da expiração produtiva e
  dispensa inventário fresco para conter uma sessão já aberta. Grant,
  ação concedida, lane, revisões, owner e revogação continuam obrigatórios.
- A reserva de controle tem dois itens e 128 KiB por padrão, permitindo
  steer válido acima de 16 KiB. O limite de payload é conferido em bytes
  UTF-8 JSON antes da admissão; texto multibyte não cria outbox impossível
  de despachar. Filas continuam finitas.
- O cliente HTTPS Connector transporta o alvo e recusa resolução que mude
  ação, alvo, conteúdo, sessão, escopo ou hash, mesmo com hash recalculado
  pelo peer. As mensagens novas das aplicações estão em US English.

O [ADR 0003](../../docs/adr/0003-canonical-control-targets.md) documenta o
mapping de `text` para razão de interrupt e as restrições de contrato.

## Testes e instalação

| Campanha final | Resultado |
|---|---|
| Nexus, suíte `tests/execution_r4`, Core/Connector instalados | 68 passaram |
| Connector, suíte completa, Core instalado | 241 passaram, 2 skips |
| Casos novos, Nexus/Connector/Core instalados, `python -I`, fora dos clones | 12 passaram |

Os casos novos cobrem targeting Codex/Pi/Claude, hash dependente do alvo,
shape inválida, alvo nativo obsoleto, replay de admissão/efeito, controle
com faixa regular ocupada, budget, grant revogado antes do envio e
interrupt após expiry produtiva com grant/lane ainda válidos. O teste
usa clocks injetados; não altera a validade persistida dos grants.

As operações são resolvidas/admitidas pelas rotas reais e pelo cliente
Connector. Lease, Core, journal, autorização de dispatch e ingresso de
recibos usam os serviços reais. A seleção aprovada e o gate de qualificação
são fixtures; o peer nativo é sintético e estrito. Não é aceite de daemon,
provider, dois hosts ou do loop de produto.

Os cinco módulos de aplicação alterados foram importados de `site-packages`
e comparados byte a byte com o source. Nenhuma importação instalada usou
o clone irmão. Os assets HTTP prévios do usuário foram empacotados sem
rebuild; esta campanha não qualifica frontend.

Os comandos, XMLs, digests, versões e tentativas iniciais de ambiente estão
em [test_runs_20260930_controls.json](test_runs_20260930_controls.json).
As campanhas se sobrepõem; seus resultados não são somados como cobertura
única. A campanha instalada preliminar de 29 casos precedeu o ajuste de
capacidade e fica identificada separadamente da repetição final.

## Trabalho ainda obrigatório

Core precisa aceitar e aplicar a política `drain_seconds` /
`interrupt_seconds` de `ClosePayload`, preservando-a no hash e no recibo.
Também deve concluir a conformance da razão de interrupt: o schema
normativo admite até 1024 caracteres, enquanto o Core atual exige 1–256.
Razão de 257–1024 gera resolução bloqueada, sem truncar o conteúdo.

Continuam pendentes contenção durante CAS, close canônico, decisões/input,
loop de outbox, composição dos owners, daemon/StateStore, reconciliação
não vazia, revogação online, UI/CLI, idioma global, migração e qualificação
com providers/hosts reais. `R4_BUNDLE_EXECUTABLE` e a prontidão de execução
do Server permanecem falsos.
