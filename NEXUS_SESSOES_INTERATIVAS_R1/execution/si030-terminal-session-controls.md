# Controles explícitos da sessão pelo terminal

- `okto-nexus session send --id HARNESS --session-id SESSION --operator-profile PROFILE` registra uma mensagem na fila para o próximo turno, inclusive enquanto outro turno executa.
- `okto-nexus session steer --id HARNESS --session-id SESSION --operator-profile PROFILE` mostra o turno em revisão e pede confirmação antes de reorientá-lo. `send` e `steer` aceitam `--message-file` para texto UTF-8.
- `okto-nexus session interrupt --id HARNESS --session-id SESSION --operator-profile PROFILE` pede confirmação para interromper o turno revisado e pausar a fila da sessão.
- `okto-nexus session receipt --id HARNESS --session-id SESSION --operator-profile PROFILE --owner-generation GENERATION --intent INTENT` consulta o pedido original. A geração e o identificador são mostrados antes do envio. A consulta aceita `--json`.

O Nexus valida o login humano, a sessão, a geração e as revisões do catálogo, do controle e da fila antes de admitir a ação. Os comandos usam os mesmos serviços que a Home e registram a origem `nexus_cli`. Se a resposta do envio se perder, o terminal consulta o recibo original. A confirmação de interrupção depende do evento observado no turno. Uma revisão antiga é recusada, e o texto continua disponível no terminal ou no arquivo de origem.

O ensaio controlado usou duas sessões reais do app-server Codex 0.157.0 com respostas determinísticas em loopback. Enfileirar pela Home tornou antiga uma revisão já aberta no terminal. A confirmação dessa revisão foi recusada. O terminal enfileirou outra mensagem, enviou uma reorientação tipada após uma nova revisão e recuperou o recibo quando o teste omitiu a resposta do servidor. A interrupção foi admitida com a fila pausada, atingiu o turno revisado e preservou a sessão irmã. O transporte nativo registrou uma única chamada de cada controle. O teste observou o envio da reorientação ao turno, com consumo ainda pendente no recibo. [Dados do ensaio](si030-terminal-session-controls.json)

A alteração dispensa migração. Reverter o commit restaura o CLI anterior e preserva as entradas, os controles e seus recibos já registrados. A confirmação integrada ao frontend nativo, a qualificação remota e a campanha da jornada completa permanecem em andamento.

O ensaio passou com o código e com o wheel instalado. Passaram 24 regressões do CLI e do runtime no pacote instalado. Ruff e a validação estrita do wheel e do pacote fonte passaram. Todas as respostas do modelo vieram de loopback.
