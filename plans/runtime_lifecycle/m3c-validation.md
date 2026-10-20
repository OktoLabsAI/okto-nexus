# M3c — Recuperar falha de startup sem reiniciar o owner

2026-10-16. Nexus 0.3.1, Core 0.0.12, Connector 0.0.10.

## Incidente preservado e reprodução

O Pi voltou a RECOVERING na instalação M2e, antes do rollout M3b. Foram
preservados backup SQLite, logs, stack e identidades técnicas em
`build/runtime-lifecycle-m3b-live/`. Três aberturas tinham launch CLAIMED,
receipt OUTCOME_UNKNOWN e nenhum birth record. O Core mantinha os slots
incertos, mas shutdown não tentava conter uma abertura cuja factory falhou
sem devolver um handle. O host permanecia preso nessa contenção.

Reprodução: falha antes/depois de spawn; adapter Pi real com falha injetada na
consulta de versão; integração pelos três adapters. Todos recuperaram sob a
mesma geração do host com a correção. Uma falha anterior a Core.prepare já se
recuperava, portanto não foi usada como explicação desse incidente.

O subtipo original do CONFIG_ERROR não foi preservado pelo diagnóstico antigo.
Timeout de consulta de versão reproduz a classe de falha, mas não é afirmado
como causa inicial comprovada do incidente. CPU em 100% foi observada; causalidade
não foi inferida somente dessa coincidência.

## Implementação

- Core supervisiona um worker por launch incerto, cercando seu produtor e
  confirmando o término do container exato antes de liberar capacidade.
- Espera cancelada/expirada não descarta worker; contenção e release pendentes
  continuam contabilizados. Não há replay nem transformação de incerteza em sucesso.
- Nexus preserva a primeira causa e atualiza a causa atual, incluindo somente
  identificadores técnicos de motivo nos logs. Retry manual retorna a causa atual.
- Vendors de Core e manifesto CI sincronizados; versões e pins permanecem coerentes.
- Core: `7bab651` (inclui `122d2dc`); Connector: `0db859c`, ambos publicados nas
  branches feature respectivas.

## Validação

- Core instalado: 111 passaram; Connector instalado: 103 passaram.
- Nexus instalado: 52 passaram; total do checkpoint: 266 testes instalados.
  Sem falhas/erros/skips; inputs estáveis. Manifestos e hashes em `m3c-results.json`.
- Regressão de preparação observava um callback antes da gravação do estado;
  agora aguarda simultaneamente estado terminal e desbloqueio do agente.
- Fixture antiga de renovação não tinha authority_gate; corrigida para testar
  o erro pretendido e verificar a primeira causa separadamente da causa atual.
- Fixture Connector de recusa por sessão segurava também o lease do irmão;
  corrigida para conter somente o escopo alvo. Campanha completa repetida.

## Teste real pela interface antes do rollout

Na geração 66 M2e, com Pi em RECOVERING, foi enviada pelo Meta-harness uma
mensagem privada para Claude no workspace Techridy, com instrução de responder
um marcador sem executar ferramentas ou acessar arquivos.

- Envio: 20:32:29 UTC; sessão `ses_8fda90e76b98f69e0787123bc2bd55e8`.
- Harness ready: 20:32:59; turn started: 20:33:00.
- Resposta: `NEXUS_M3C_ISOLATION_CLAUDE_OK`, 20:33:01; conclusão: 20:33:03.
- Meta-harness confirmou 1/1 ACK e exibiu a mesma resposta final.
- Terminal live tail inspecionado; screenshot em
  `build/runtime-lifecycle-m3b-live/claude-isolation.jpg`.

Isso confirma isolamento do Claude no incidente atual; não confirma recuperação
do Pi nem instalação M3c. O servidor permaneceu intacto durante o diagnóstico e
esse teste. Rollout e teste real após atualização ainda pendentes. UI-A continua
aberto, incluindo a limitação externa de quota do Codex e critérios restantes
de M2/M3. A política geral de renovação remota fora de recusas correlacionadas
também continua no escopo M3/M5.
