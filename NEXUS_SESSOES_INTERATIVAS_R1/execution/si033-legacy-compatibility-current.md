# SI-033 · Regressão dos fluxos existentes com os pacotes instalados

Em Windows, passaram 384 testes com Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 instalados em um diretório isolado. Cada suíte verificou que os três módulos foram importados dos wheels. O código do Nexus, o frontend e os arquivos de dependências do wheel coincidem com o checkout auditado. [Pacotes, revisões e suítes](si033-legacy-compatibility-current.json)

| Fluxo | Testes | Cobertura |
| --- | ---: | --- |
| CLI e profiles | 187 | Gramática legada, `--no-chat`, reutilização de profile, seleção entre harnesses, recuperação de resposta perdida e recibo de `work resume`. |
| Operator e handoffs | 69 | Autorização do operador remoto, vínculo e grant revisados, claim canônico, recuperação de handoff e navegação pela solicitação exata. |
| Contrato do Codex simulado | 4 | Conclusão, rejeição, revisão e resultado sem autorização pelo protocolo do app-server. |
| Participant e sessões | 124 | Configuração, lançamento e remoção de participant, credencial com escopo de processo, mensagens e handoffs privados e em broadcast e correlação de sessões. |

A regressão usa perfis e bases descartáveis com respostas de fixture. O teste do cofre do Windows criou e removeu uma entrada isolada com chave sintética. A prova de ida e volta no Edge com Pi, os testes em ConPTY e a recuperação instalada de envio incerto estão nos registros anteriores. [Edge e Pi](si036-pi-browser-writer-roundtrip.md) [Modos do CLI](si029-installed-connect-modes.md) [Recuperação de envio](si030-installed-work-resume.md)

Na primeira rodada, a fixture de perfil falhou ao tentar gravar um BLOB pelo gatilho de autoridade do SQLite. O teste agora insere a linha histórica e confere que o diagnóstico a preserva. A fixture de handoff também falhou na abertura do Codex simulado porque faltava a resposta a `account/read`. Ela passou a reutilizar a resposta sintética de conta já definida nos testes. O código distribuído permanece igual.

Os cenários de aceite SI-T-I01 e SI-T-I04 ainda exigem a campanha prevista. Este marco atualiza fixtures e evidências, sem migração ou alteração do pacote. O rollback consiste em reverter o commit.
