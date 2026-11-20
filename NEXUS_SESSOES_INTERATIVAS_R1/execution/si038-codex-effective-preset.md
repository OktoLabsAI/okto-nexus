# SI-038 · Preset do projeto e isolamento de MCPs globais

O Core agora aplica a opção de herança global do Codex quando o preset de projeto é a única fonte de ferramentas. Antes da correção, a decisão de desativar os MCPs globais acontecia antes de o preset ativar a renderização da configuração de processo. Um MCP global com outro nome podia permanecer disponível mesmo com a herança desativada. A revisão valida o comportamento com a herança habilitada e desabilitada. [Commit do Core](https://github.com/OktoLabsAI/okto-nexus-connector-core/commit/26a157abcc4d8fc79ac92cfb6a456747f19f36d1)

## Evidência

- A combinação com a herança desativada falhou no wheel anterior e passou no novo. Passaram 37 testes no código-fonte e os mesmos 37 no wheel, com dois casos ignorados em cada rodada. Também passaram 8 testes instalados do Nexus e 24 do Connector.
- No controle positivo, o Codex 0.157.0 iniciou a ferramenta sentinela declarada no perfil descartável. Com os argumentos gerados pelo novo wheel para um preset sem ferramentas do Nexus, o mesmo executável iniciou a ferramenta revisada e manteve a sentinela desativada. O arquivo do perfil ficou idêntico e o app-server saiu com código zero. O teste criou apenas uma thread temporária sem prompt.
- A API de operador avançou o preset da revisão 0 para a 1 e retornou o mesmo digest na leitura posterior. A escrita com chave de agente retornou `403` e a repetição da revisão antiga retornou `409`. O Connector recebeu o preset na configuração assinada de abertura. O ambiente produzido manteve a ferramenta HTTP da sessão do Nexus, incluiu o preset revisado e desativou a sentinela global.
- O ensaio instalado com Edge, ConPTY, Codex app-server 0.157.0 e visualizador 0.170.0 completou a jornada. O turno iniciado no terminal chamou `wait_for_marker`. A Home enfileirou a próxima mensagem, o CLI recebeu a confirmação da reorientação do turno exato e os dois visualizadores foram desanexados antes da liberação do marcador. A mensagem da Home iniciou um turno separado e os resultados apareceram uma vez. A jornada usou um único processo do app-server, três turnos da mesma thread e fechamento canônico. O SQLite passou nas verificações de integridade e de chaves estrangeiras.
- O simulador em loopback reportou cinco atualizações de uso, somando 1.575 tokens sintéticos associados aos três turnos. Os processos e o listener descartáveis foram encerrados. O ensaio usou resposta simulada e perfil temporário, sem inferência externa, cobrança ou mudança na instalação pessoal.

As primeiras rodadas registraram uma tentativa de autenticação pela superfície errada, interrupções no canal de controle e uma falha de admissão de escrita no SQLite. A rodada final aguardou recibos persistidos por leituras espaçadas e conferiu a resposta HTTP uma vez por transição. Ela também corrigiu a expectativa do fixture para aceitar o MCP de sessão que o Connector injeta em aberturas remotas. [Histórico das tentativas](si038-codex-effective-preset.json)

## Impacto e reversão

Nexus e Connector passaram a fixar o mesmo wheel de desenvolvimento do Core 0.0.16. O ajuste atua ao preparar uma nova abertura e não exige migração. Para reverter, restaurar o pin anterior nos dois consumidores, incluindo o SHA-256 no manifesto de CI do Nexus. [Commit do Connector](https://github.com/OktoLabsAI/okto-nexus-connector/commit/186a3dae4818edf1330395959d2efda6de885b36)

SI-038 segue em andamento. SI-T-I07, SI-T-I08 e SI-T-I09 exigem a campanha com provedor consentido e seguem como `NOT_RUN`. [Preparação da campanha](si038-codex-campaign-preflight.md) [Evidência estruturada](si038-codex-effective-preset.json)
