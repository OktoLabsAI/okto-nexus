# SI-T-A01, SI-T-A02 e SI-T-A03 — Autoria da entrada humana

O Pi 0.87.1 executou dois turnos na mesma sessão do executor local
do Nexus no Windows. O ensaio usou o wheel instalado, um projeto
descartável e respostas determinísticas do provedor de teste.
[Relatórios e hashes](si006-pi-human-input-authority.json)

1. Enquanto o turno original estava ativo, o operador enviou
   `actor_agent_id` no corpo de uma nova entrada. A API respondeu
   HTTP 422. As operações, a fila e a referência do login
   permaneceram como estavam.
2. O mesmo login e a mesma intenção, com os campos do contrato,
   receberam HTTP 202 e um recibo `QUEUED`. A única entrada ficou
   vinculada à referência humana, à superfície web e à sessão exata.
3. Após concluir o turno original, o dispatcher entregou a entrada
   uma vez. O histórico nativo do Pi registrou o papel `user` e o
   texto exato, incluindo a quebra de linha e o acento. O recibo
   `ACCEPTED_NATIVE` ficou ligado à operação que produziu o segundo
   resultado na mesma sessão.
4. A auditoria final confirmou zero registros nas tabelas de mensagens,
   entregas, handoffs e decisões consultadas. O fechamento canônico
   encerrou a sessão e o SQLite passou nas verificações de integridade.

Passaram o ensaio com o Pi e as seis regressões do mesmo wheel. O
ensaio remoto anterior terminou sem recibos nativos. Em uma tentativa
local anterior, o inventário ficou com o Pi em `PENDING`. A fixture
aprovada forneceu à descoberta a instalação Pi cuja versão e identidade
foram medidas. O runtime, a fila, a autoridade e o processo nativo
foram exercitados pelo código instalado. A qualificação da descoberta
completa e de hosts remotos continua em seus cenários próprios.

Este marco atualiza evidências e ledger. Reverter o commit desfaz
esse registro, sem migração.
