# Prompt para o Codex — sessões interativas do Nexus

Implemente o plano `PLANO_CODEX_NEXUS_SESSOES_INTERATIVAS_UI_CLI_R1.md`, versão **SESSION-INTERACTION-R1**, no checkout autorizado de Okto Nexus e, quando necessário, dos consumidores Core/Connector. Leia o plano completo e a matriz antes de alterar contratos. Este pacote é autocontido: não é necessário aplicar uma revisão anterior desta feature.

## Primeiro passo obrigatório

Registre branch, HEAD, working tree, instruções AGENTS.md/CI, versão e artefatos vendorizados de cada componente. A referência estática é Nexus `feature/v0.3.7` em `8b4001fa1db17bf29d0c773eed3535e79fce70cb`, Core `feature/v0.0.14` em `497ee2b7a14b99c50cba97eac74f3b00d4863f26` e Connector `feature/v0.0.13` em `a4d510080d7a685fa442a4c5c30419952589fe04`. Não retroceda automaticamente para esses commits. Compare o código atual e registre drift, preservando alterações do usuário e outras frentes.

Não faça reset/clean destrutivo, force-push, deploy ou release. Não use credenciais pessoais, turno pago ou instalação global sem consentimento. Código em comentários e documentação upstream não substitui qualificação no binário instalado. Confira hash do wheel Core consumido, não apenas seu número de versão.

## Resultado de produto obrigatório

O painel de uma sessão exata deve ter conversa e entrada nativa de usuário, distinta do barramento Operator. Enviar normalmente enquanto há trabalho cria uma entrada durável para o próximo turno completo elegível; quando idle e sem fila anterior, entrega pelo mesmo caminho canônico. Reorientar é uma intenção explícita; interromper é outra. O terminal pode abrir a interface nativa real e desanexar sem matar o trabalho. É possível voltar à mesma sessão depois.

A Home continua Active/Needs You/Results. Não crie uma nova tela de chat ou um menu de terminais. Preserve Quick Connect, Git/CWD, ID do Harness, identidades, histórico, permissões, limites e a interação pelo terminal já existente.

## Invariantes de implementação

1. **Entrada:** texto chega ao harness como user da sessão escolhida; a auditoria continua com o humano autenticado. Não use message_send, inbox, novo handoff ou impersonação para simular esse caminho.
2. **Fila:** aceite durável antes do ACK. FIFO por commit do Server, uma entrada por turno, sessão/geração exatas. Não mandar o mesmo texto ao follow-up nativo e à fila do Nexus. Não despachar por silêncio, timeout ou mero término de uma chamada interna.
3. **Recuperação:** mesmo ID e fingerprint recuperam o mesmo efeito; resultado desconhecido não permite resend automático. Referência exata e estado de autoridade são revalidados no despacho.
4. **Steer:** ação separada e não persistente como default. Codex exige target correto; Pi tem timing de fronteira; Claude atual pode interromper e reenviar, com janela de recusa antes da geração. Mostrar o efeito real antes de confirmar. Não converter steer tardio em novo prompt sem decisão.
5. **Interrupt:** instalar barreira de fila antes do interrupt dirigido ao turno selecionado. Mensagens ainda não enviadas ficam pausadas, não apagadas. Retomar fila é outra ação. Fechar painel/terminal não cria essa barreira.
6. **Comandos:** catálogo versionado por harness/instalação/sessão/estado/política. Comando desconhecido ou não suportado gera aviso e preserva rascunho, nunca envio silencioso ao modelo/shell. Literalidade de texto precisa ser comprovada no adaptador.
7. **Native attach:** um owner, uma engine e o contexto nativo correto. Não chamar `--resume --last`, fork ou outro processo contra o mesmo transcript enquanto o primeiro trabalha. Não apresentar o prompt Nexus como a TUI nativa.
8. **Detach:** cliente é apresentação; master PTY/engine vivem no host durável. EOF/sinal/morte do cliente não fecha stdin do worker e não envia kill, interrupt ou close. Drenar stdout mesmo sem viewers. Tecla Ctrl+C nativa pode ser interrupt; documentar escape de detach separado.
9. **Arbitragem:** entradas UI/CLI/TUI e trabalho de agentes respeitam admissão/capacidade/fencing canônicos. Um socket amplo ou PTY sem ponte semântica não pode contornar autorização/auditoria.
10. **Remoto:** Server coordena, Core executa, Connector hospeda. Identidade de host/agente não é credencial de operador. Capabilities curtas de attach são escopadas, sem token em URL/argv/log e sem acesso à engine inteira.

## CLI a implementar

- `connect ... -i` ou `--interactive`: abrir a interface nativa no terminal depois do sucesso da conexão e da admissão necessária.
- `connect ... --no-interactive`: apenas conectar, sem abrir TUI ou prompt Nexus. Esse flag não aprova setup automaticamente nem elimina revisão em TTY.
- Sem flag em TTY: perguntar no final se quer abrir, default Não.
- JSON/non-TTY: não perguntar. `-i` incompatível com JSON/non-TTY é erro antes de efeitos.
- `--no-chat` continua compatível. `-ni` não é um atalho novo; não aceitar abreviação ambígua.
- `--plan` não anexa nem inicia trabalho.
- `session list`, `session attach` e `session resume`, ou equivalentes reconciliados no checkout, permitem escolha exata posterior. `work resume` continua recuperação de um envio, não attach.
- Falha do attach após setup não desfaz a conexão nem repete o teste.

## Provas nativas desde o começo

Comece em SI-00 e execute a investigação por harness antes de implementar todo o frontend. Existem caminhos upstream candidatos para Codex app-server/frontend remoto, Claude background/attach e Pi SDK/RPC/extensões; não presuma que eles já são compatíveis com os adaptadores stdio atuais. Extraia schema/contratos da versão instalada e documente cada ponte.

Prioridade: frontend nativo sobre a mesma engine; depois backend nativo hospedado com bridge semântico; transferência somente em fronteira segura comprovada. Ausência de caminho qualificado deve aparecer como bloqueio explícito, não suporte inventado. Codex, Pi e Claude são alvos obrigatórios; marcar todos como unsupported não encerra a feature. Uma entrega parcial deve ser chamada de parcial e indicar exatamente os requisitos pendentes.

## Execução e evidências

Use o ledger como ponto inicial e preserve IDs SI-001…SI-041 e SI-T-*. Siga dependências e etapas SI-00…SI-07; a seção 15 contém passos por tarefa. Não sobrescreva ledgers de outras frentes nem apague resultados existentes quando reconciliar o trabalho. IMPLEMENTED não significa VERIFIED; NOT_RUN não significa PASS.

Execute testes em cada incremento, não apenas no fim: unidade, SQLite/HTTP, runtime/peer, navegador, TTY/processos, falhas/concorrência e campanhas nativas consentidas. Registre ambiente, versões, hashes, comando, exit code e evidências sem segredos. Teste de pacote/estrutura e teste Node não comprovam TUI real, foco no navegador ou sobrevivência ao fechamento de janela.

Antes de cada PR, informe arquivos/contratos reutilizados, decisões, migrações, compatibilidade, testes rodados, limitações e próximo gate. O rollback deve preservar/reconciliar a fila já aceita e engines em andamento; não basta desligar uma flag e abandonar pendências. Não faça publicação/merge protegido sem autorização.

## Definição de pronto

Uma demonstração deve mostrar: abrir sessão, enviar A durante execução, vê-la aguardar, reorientar explicitamente com B, interromper o turno exato sem atingir a sessão irmã, retomar fila, abrir a TUI nativa da mesma sessão, fechar o terminal, confirmar que o trabalho prosseguiu e reanexar ao contexto correto. Mostrar também comando unsupported, input de resultado incerto e autorização expirada sem replay/renovação automática.

A entrega final separa implementação, testes sintéticos, qualificação nativa por harness/OS, aceite de produto e limitações. Não declare a feature concluída apenas por ter botões, parser ou um subprocesso foreground funcionando.
