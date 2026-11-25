# SI-005 synthetic peer and baseline regressions

The test fixture scripts a single synthetic turn for a full session key and
owner generation. Its two sessions share a short ID but use separate
executors. Acknowledgement can defer or be lost after the input was
accepted. Model end does not settle the turn. A pending question is tied
to the exact turn and blocks its transition until a matching response.

The fixture emits text echo, delta and snapshot events with separate
event and item IDs. A test feeds its output to the actual Core byte-bounded
event buffer. A reader that falls behind observes the overflow and the
synthetic producer still settles. The fixture uses no provider, engine,
network socket, PTY or personal credential.

The final combined source run in the isolated Core 0.0.15 environment
collected these fixtures alongside contract, SQLite and NS-00 tests.
It finished with 30 passes. An earlier run in the checkout's older venv
failed startup for one NS-00 test because that venv still contained Core
0.0.14. The same test passed with the intended installed dependency.

This evidence validates the synthetic driver and the observable boundaries
it supplies. Host ownership, native Pi settled signals, actual
actor revocation, browser rendering and platform shutdown are separate
qualifications.

## Reprodução com os wheels atuais

Passaram 47 testes de peer sintético, transcrição, armazenamento de fila e autoridade com Nexus `8bcee9bd`, Core 0.0.16 e Connector 0.0.15 instalados no Windows. As fixtures usaram duas referências de autor e duas sessões com o mesmo ID curto em executores diferentes. O teste concorrente conferiu as sequências gravadas no SQLite. Os testes do peer conservaram a ocupação após o ACK e o fim do modelo, atribuíram perguntas à sessão exata e preservaram identidades de evento e item durante deltas e snapshots. O teste de saída excedente exercitou a implementação do buffer do Core.

O verificador retirou credenciais de provedor conhecidas do ambiente de teste e bloqueou conexão de rede, resolução de nomes e subprocessos das fixtures. Na primeira passagem, esse bloqueio também atingiu o par de sockets interno que o `asyncio` cria no Windows. A repetição permitiu apenas os eventos internos de loopback da rotina de par de sockets. A suíte terminou sem tentativas de rede ou subprocesso pelas fixtures. [Resultados e hashes](si005-current-fixtures.json)

Os cenários focais mantêm as provas dinâmicas da fronteira `agent_settled` com Pi, da atualização por fragmentos com Edge e da drenagem de saída do Pi sem visualizador. Cada prova registra suas versões e condições. O marco verifica a preparação das fixtures, dispensa migração e pode ser revertido pelo commit. [Pi e fila](si025-pi-delayed-settlement.md) [Fragmentos no Edge](si012-codex-live-conversation.md) [Saída sem visualizador](si037-pi-headless-output.md)
