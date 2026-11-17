# Prompt para o Codex — Quick Connect QCONNECT-R1

Leia integralmente `PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md` e use `NEXUS_QUICK_CONNECT_LEDGER_R1.json` como registro inicial de execução. Este pacote é autocontido para a feature: contém todos os requisitos, contratos, tarefas e cenários. Não é preciso outro plano nem uma etapa de aplicação de emendas.

O snapshot de referência é `OktoLabsAI/okto-nexus`, `feature/v0.3.5`, SHA `2463c05833f533bc5a5676a5644774cff949ca28`. Ele não obriga retroceder o checkout e não comprova o HEAD atual. Registre branch, HEAD, status, instruções locais, diferenças e dependências antes de editar. Preserve o trabalho em andamento; não faça reset/clean/checkout destrutivo, force-push, deploy, release ou merge protegido.

Há 33 tarefas, 147 cenários, 20 requisitos e 7 etapas. Inicialize o acompanhamento deste plano com TODO/NOT_RUN. Não modifique registros de outras frentes. Reutilize código já existente após verificar os critérios aplicáveis; não crie uma segunda Home, outro daemon ou um setup paralelo.

## Contrato público

```sh
okto-nexus connect [harness] [project-name] [--id HARNESS_ID]
okto-nexus claude
```

Preserve flags e perfis legados. Aliases raiz usam allowlist e o mesmo fluxo; comandos do produto têm precedência. Token de harness desconhecido dentro de `connect` permite seleção guiada somente em TTY. JSON/não TTY nunca bloqueiam stdin nem escolhem candidatos implicitamente.

## Regras obrigatórias

**Nome do projeto:** escolhas explícitas concordantes → associação Nexus validada → origin Git local inequívoco → basename da raiz do working tree → basename da raiz física selecionada. `--project` continua path e prevalece como base física sobre CWD. Nome Git só sugere: não identifica workspace, não renomeia associação existente e não agrupa clones/worktrees. Git pode sugerir o nome a partir de uma subpasta, mas a raiz de execução continua CWD/`--project` até decisão explícita. Seletores exatos contraditórios geram conflito.

**Git local:** consultas permitidas de `rev-parse`/`config`, executável confiável, argv sem shell e limites de tempo/saída. Sem rede, hooks, instalação, autenticação ou escrita de configuração. Não presumir `.git` como pasta em worktrees/submodules. Origin ambíguo/inválido e Git ausente/timeout/safe.directory degradam a sugestão com motivo, não a segurança. Não armazenar/exibir URL completa, tokens, query, fragmento ou stderr bruto. Em `--plan` e help não iniciar Git; usar seleção salva ou fallback claramente não verificado. Recuperação da intenção aprovada não redescobre Git para renomear.

**Vocabulário:** o rótulo básico é **ID do Harness**; no frontend inglês, **Harness ID**. Profile é detalhe técnico, não campo exigido do iniciante. O papel Project assistant é função do agente, não identificador. Usar `connect_id` como chave técnica única; não criar um `harness_id` independente nem reaproveitar `agent_id`, `binding_id` ou `session_id`. IDs automáticos vêm de codex/claude/pi e sufixos, nunca do nome Git.

**Colisões:** unicidade no Server por workspace, inclusive entre hosts. Nunca sobrescrever harness, binding ou permissões do ocupante. Em TTY, ID existente compatível oferece Retomar explicitamente. Harness diferente identifica a conexão real e permite escolher usá-la (apenas com seletores compatíveis), escolher outro ID, pedir sugestão ou cancelar. `--new-connection` com ID de outra intenção não oferece retomada como substituto. Scripts conflitantes recebem erro estruturado; não aplicar sugestão automaticamente. Retomada exata não interativa, sem new, continua válida. Recuperar a própria intenção commitada precede colisão, inclusive com new; nome igual sozinho não prova a mesma intenção. Respeitar reservas incertas, revogados, tombstones e autorização de visibilidade.

**Confirmação:** um resumo final com projeto/fonte, raiz, harness efetivo, ID do Harness, host e efeitos canônicos. Confirmar/Personalizar/Cancelar fazem parte do mesmo fluxo. Selecionar opções não aprova teste; não duplicar confirmação de nome e setup. Personalização exige revisão/hash novo. Consentimento adicional continua necessário se os efeitos efetivamente mudarem. Retomada não renova grants nem repete teste.

**Persistência e resultado:** reutilizar reservas, checkpoints, Finish e recibos existentes. Distinguir ID proposto, reservado e bound; vínculo definitivo na transação correta. Sucesso exibe o ID antes do chat, e JSON só declara connected com ID bound e referência revalidada. Falha após commit retorna estado parcial recuperável; não criar outra identidade porque falhou o disco local. ID aparece na Home existente sem menu/lista nova nem roteamento MCP por alias implícito.

**Topologia:** preservar remoto, participant e daemon. CWD/Git do operador não definem a raiz do Connector; falha remota não cria Server local substituto; não há um daemon por ID. A gramática curta é do caminho gerenciado. Não misturar os novos posicionais com participant sem contrato. Não redesenhar Core ou Connector para facilitar o CLI.

## Execução e evidências

Comece por QC-00. Siga QC-01 a QC-06 e as dependências do backlog completo. Teste parser, Git local, TTY/JSON, aliases, diretórios, concorrência, HTTP, recuperação, compatibilidade e UI. Registre os comandos, ambiente e commit de cada prova. Não marque VERIFIED/PASS com base em presença de arquivo, busca de string ou relato não executado. A validação do pacote confere documentos e referências; não executa o Nexus.

Ao fechar cada etapa, informe arquivos alterados, contratos reutilizados, testes executados e não executados, migrações, efeitos, limitações, rollback e próximo passo. Campanha com provedor/dados reais exige consentimento, limite e ambiente isolado. Sem consentimento, implemente e teste as partes independentes, registre a campanha como NOT_RUN/BLOCKED e não alegue qualificação real.

A entrega só está completa quando o primeiro e o segundo harness podem ser conectados no mesmo projeto, recebem IDs persistentes, tratam colisões, aparecem na UI e são retomados sem duplicar identidades ou repetir efeitos. Não encerrar apenas com os novos argumentos do parser.
