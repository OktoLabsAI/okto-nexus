# Okto Nexus — plano consolidado de Quick Connect
## CLI simples, projeto por Git/CWD e ID do Harness persistente

**Versão do plano:** QCONNECT-R1 · edição inicial consolidada · 17/11/2026  
**Destinatário:** Codex / executor com capacidade intermediária.  
**Natureza:** especificação completa de desenvolvimento; nenhuma implementação ou campanha de teste do Nexus foi executada na preparação deste pacote.  
**Escopo:** Quick Connect gerenciado, seleção/retomada de conexões, descoberta local do nome do projeto, ID do Harness, persistência, colisões, confirmação e compatibilidade.  
**Conteúdo:** 33 tarefas, 147 cenários de aceite, 20 requisitos e 7 etapas de implementação.

## Comece por este pacote

Este documento contém todos os requisitos da feature em uma única especificação. O Codex não precisa receber outro plano, aplicar emendas ou comparar documentos para começar.

Use `PROMPT_CODEX_NEXUS_QUICK_CONNECT_R1.md` como instrução de entrada. Este Markdown é a fonte normativa. `NEXUS_QUICK_CONNECT_LEDGER_R1.json` contém o acompanhamento inicial, com todas as tarefas em `TODO` e todos os cenários em `NOT_RUN`. O backlog está na seção 12; os cenários completos, na seção 13.

O produto já possui mecanismos de configuração, daemon, catálogo, Home e recuperação. Eles são a base a reutilizar, não pré-requisitos documentais externos. Antes de implementar, conferir o checkout real e preservar alterações e registros de outras frentes em andamento. Não refazer a UI nem os adaptadores nativos por conveniência do CLI.

## Decisões de produto

| Tema | Comportamento obrigatório |
|---|---|
| Comando principal | `okto-nexus connect [harness] [project-name] [--id HARNESS_ID]`, com flags legadas preservadas. |
| Atalhos | `okto-nexus codex`, `okto-nexus claude` e `okto-nexus pi` usam o mesmo fluxo de `connect`. |
| CWD | É o contexto físico padrão; `--project` explícito seleciona outro diretório. O nome posicional não é um caminho. |
| Nome do projeto | Escolhas explícitas concordantes → associação Nexus validada → nome do origin Git local inequívoco → basename do working tree → basename do diretório físico selecionado. |
| Git | Somente sugestão local de nome, sem rede, escrita de configuração ou autoridade sobre workspace/raiz. |
| Identificação pública | **ID do Harness** / **Harness ID**. O campo técnico único é `connect_id`; `--id` é opcional. |
| Geração automática | Baseada no harness, como `codex`, `claude`, `pi`; sufixos só após intenção explícita de adicionar outra conexão. |
| Unicidade | ID definitivo único por Server + workspace, inclusive entre máquinas. Nunca sobrescrever a conexão ocupante. |
| Retomada e colisões | Retomada explícita em TTY quando permitida; outro ID para uma nova conexão; scripts recebem conflito estruturado quando não podem retomar de modo exato. |
| Confirmação | Um resumo final com projeto/fonte, raiz, harness efetivo, ID, host e efeitos novos. Personalizar exige revisão nova. |
| Resultado | Sucesso informa o ID definitivo antes do prompt; proposta, reserva ou configuração parcial não são conexão concluída. |
| Recuperação | A própria intenção e seu recibo têm precedência sobre falso conflito de ID. Reconectar não repete teste/tarefa, não recria agente e não renova grant. |

Nomes de componentes, rotas e campos novos são propostas de contrato. Reutilizar equivalentes do checkout que satisfaçam o mesmo comportamento. As referências de código indicam um snapshot documentado, não uma nova auditoria do HEAD feita nesta consolidação.

---

# 1. Baseline e integração com o produto existente

## 1.1 Snapshot de referência do código

| Item | Referência |
|---|---|
| Repositório principal | `OktoLabsAI/okto-nexus` |
| Branch de referência | `feature/v0.3.5` |
| SHA de referência | `2463c05833f533bc5a5676a5644774cff949ca28` |
| Versão declarada | `0.3.5` em `pyproject.toml` |
| Python mínimo declarado | `>=3.11` |
| Dependência Core declarada | `okto-nexus-connector-core==0.0.14` |

A branch, a versão declarada e o pacote instalado pelo usuário são coisas diferentes. Não foi verificada uma instalação em execução. Não foram executados testes, comandos Nexus, harnesses ou chamadas pagas para preparar este pacote. O executor deve registrar HEAD, working tree, instruções do repositório e diferenças posteriores, sem retornar automaticamente a este SHA. [S01]

## 1.2 O que já existe — não reconstruir

| Base existente | Evidência / uso correto |
|---|---|
| `main.py` despacha subcomandos conhecidos | Acrescentar aliases explícitos de harness nessa entrada. Hoje ela não despacha `codex`, `claude` e `pi` como comandos raiz. [S02] |
| `connect.py` aceita `--client`, `--project`, `--profile`, `--new-connection`, `--plan`, `--approve`, `--json`, `--no-chat` | Introduzir posicionais e `--id` preservando os significados atuais; hoje o parser de `--client` usa `choices`, impedindo o fallback interativo para enum inválido. [S03] |
| `project_profile()` já usa `Path.cwd()` quando `--project` está ausente | CWD não é uma descoberta nova. Separar a referência física atual da resolução do nome lógico, hoje derivado principalmente do diretório. [S03] |
| `connection_choices.py`, `connection_picker.py`, `canonical_connections.py` | Já existe seleção de retomar/adicionar, catálogo completo limitado e associação de conexões vindas do dashboard/Connector. Não reintroduzir criação cega de perfis. [S04–S05] |
| `connection_project.py` | Revalida vínculos do projeto pela fonte canônica e pelo caminho. Não é ainda um seletor genérico de projetos por nome. [S06] |
| `connection_reservation.py` | Reserva local de intenção, identificador estável, proteção de caminhos e locks curtos de catálogo já existem. Evoluir o checkpoint, sem uma segunda saga independente. [S07] |
| `TerminalConnection.review/apply/observe` | Já possui revisão, teste, recuperação e observação. Separar resolução da intenção da execução desses métodos. [S08] |
| `connection_setup.py` | Finish transacional e recibos por intenção já existem. O vínculo definitivo do ID público deve participar dessa fronteira, não ser uma gravação tardia sem recuperação. [S09] |
| `ConnectionCatalog` e consultas SQLite | Catálogo canônico paginado, autenticado e com revisão já existe. Extender seus campos de leitura, sem inferir autoridade de arquivos locais. [S10] |
| `configuration.alias` e validação de binding | Alias interno existe, mas seu conflito é limitado por agente/executor/workspace; isso não garante unicidade pública em todo o projeto. Não substituir seu significado silenciosamente. [S11] |
| Documentação de conexão 0.3.5 | Já descreve retomar/adicionar, perfis automáticos interativos, scripts com perfil estável e distinção entre configurar e executar. [S12] |

**Delta principal:** gramática curta + resolvedores contextuais + namespace público de identificação + resultado consistente. O custo não está em reinventar daemon ou adaptadores; está principalmente na resolução correta, compatibilidade e persistência do nome público.

## 1.3 Invariantes da implementação

1. A nova entrada coleta a intenção do usuário e utiliza os serviços canônicos de revisão, setup, execução e recuperação. Não cria outro coordenador.
2. O dashboard permanece opcional para todo o ciclo cotidiano pelo terminal. A Home só projeta o ID já registrado, sem nova tela ou lista de execução.
3. Identidade do agente, conexão canônica, sessão, atalho local e ID do Harness são conceitos distintos. Nome amigável não concede permissão.
4. Git fornece uma sugestão de nome. CWD/`--project` definem o contexto físico, e a raiz aprovada só muda por decisão explícita.
5. Seleções existentes e parâmetros explícitos prevalecem sobre descoberta. Nenhuma mudança de origin ou branch renomeia uma conexão salva.
6. Retomar uma conexão, adicionar outra, continuar uma sessão e recuperar um envio pendente são intenções distintas. Não converter uma na outra silenciosamente.
7. A unicidade do ID é garantida pelo Server. Não fabricar essa garantia usando somente arquivos locais, nem completar uma conexão sem recibo verificável.
8. Uma revisão final reúne as escolhas e os efeitos novos; escolher um item de menu não aprova teste, autorização ou Finish.
9. Scripts e JSON não recebem prompts nem alternativas aplicadas automaticamente. Resultado incerto conserva seus checkpoints e metadados de efeito.
10. A compatibilidade com comandos, perfis, bindings, recibos, UI, Connector e modo participant existentes é obrigatória. Não redesenhar esses componentes para facilitar esta entrega.
11. Ler uma lista ou abrir a Home não cria nomes, renova grants ou inicia inferência. Atribuição de nome a conexão antiga exige operação de metadados autorizada.
12. Testes já documentados no repositório não são evidência automática desta feature. Preservar as evidências existentes e executar os critérios afetados antes de marcar verificação.

---

# 2. Objetivo, contrato público e requisitos

O usuário deve conseguir entrar numa pasta e executar:

```sh
okto-nexus connect codex
okto-nexus connect codex my-awesome-project
okto-nexus connect claude --id reviewer
okto-nexus connect pi my-awesome-project --id documenter
okto-nexus claude
```

**Os posicionais, aliases raiz e `--id` acima são interfaces a implementar.** O comando legado já existente continua válido:

```sh
okto-nexus connect --client codex --project .
```

A forma pública passa a ser:

```text
okto-nexus connect [HARNESS] [PROJECT_NAME] [--id HARNESS_ID] [opções existentes]
okto-nexus <codex|claude|pi> [PROJECT_NAME] [--id HARNESS_ID] [opções compatíveis]
```

## 2.1 Requisitos rastreáveis

| ID | Requisito obrigatório |
|---|---|
| QC-R01 | Aceitar harness e nome de projeto posicionais, preservando flags legadas. |
| QC-R02 | Oferecer aliases raiz explícitos `codex`, `claude`, `pi` para o mesmo fluxo. |
| QC-R03 | Capturar e considerar CWD; `--project` continua caminho, não nome lógico. |
| QC-R04 | Resolver projetos autorizados por identidade/nome e vínculo físico; criar somente após revisão explícita. |
| QC-R05 | Sugerir nome por escolha explícita → associação Nexus validada → origin Git local inequívoco → basename da raiz do working tree → basename da raiz física selecionada; nenhuma origem Git confere identidade ou autoridade. |
| QC-R06 | Separar descoberta do nome de raiz de execução; preservar CWD/--project e exigir escolha explícita para qualquer ampliação, inclusive subdiretórios, monorepos e worktrees. |
| QC-R07 | Harness ausente/desconhecido ou indisponível gera escolha guiada em terminal interativo, sem executar texto arbitrário. |
| QC-R08 | Aceitar `--id` opcional e gerar um identificador amigável quando ausente numa adição. |
| QC-R09 | Garantir unicidade do ID definitivo por Server + workspace, com persistência, concorrência e recuperação. |
| QC-R10 | Usar ID do Harness (Harness ID na UI inglesa) em confirmação, seletores, conflito e sucesso; perfil técnico permanece interno ou em ajuda avançada/JSON. |
| QC-R11 | ID existente nunca é sobrescrito: retomada explícita quando compatível, outro ID para nova conexão, conflito estruturado não interativo e recuperação da própria intenção antes de colisão. |
| QC-R12 | Preservar retomar/adicionar, identidade, grants, sessões e escolhas existentes. |
| QC-R13 | Reunir projeto, origem do nome, diretório, harness real, ID do Harness e efeitos novos na revisão final única; personalização invalida aprovação anterior e cancelamento não produz setup. |
| QC-R14 | Sucesso Quick Connect sempre informa o ID definitivo criado, reutilizado ou associado. |
| QC-R15 | JSON/noninteractive não abre prompts, não escolhe ambiguidades e não bloqueia stdin. |
| QC-R16 | Reusar setup, revisão, reserva, recibos, catálogo e daemon canônicos. |
| QC-R17 | Preservar topologia remota: CWD do operador não vira caminho do Connector. |
| QC-R18 | Mostrar o ID na projeção UI existente, sem novos menus e sem roteamento de mensagens por alias implícito. |
| QC-R19 | Migrar/adotar conexões antigas sem renomear identidade, binding, sessão ou perfil. |
| QC-R20 | Comprovar parser, domínio, HTTP, concorrência, CLI e instalação; distinguir testes simulados de execução real. |

## 2.2 Fora de escopo desta feature

Não implementar outro multiplexer/PTY, instalar harness automaticamente, fazer login no provedor automaticamente, clonar repositórios, criar pastas implicitamente, descobrir credenciais de terceiros, usar LLM para escolher projeto, alterar política de autorização, ampliar grants, criar roteamento MCP por apelido, adicionar nova tela ou reescrever Core.

Não introduzir aqui uma gramática nova completa para `okto-nexus-connector`. A compatibilidade de leitura/retomada e a preservação de seu onboarding são obrigatórias; futuras mudanças de seu parser precisam de contrato específico. O wizard, a aprovação remota, o daemon e a retomada existentes no Connector devem continuar funcionando; este plano exige essa regressão, não um novo CLI paralelo no host remoto.

---

# 3. Gramática determinística e compatibilidade

## 3.1 Regras do parser

1. `HARNESS` e `PROJECT_NAME` são strings opcionais, nessa ordem. Um único posicional após `connect` é sempre harness. Não interpretar uma palavra desconhecida como projeto para tentar fazê-la funcionar.
2. O alias raiz injeta o harness: `okto-nexus claude projeto` equivale semanticamente a `okto-nexus connect claude projeto`. Não reinvocar subprocesso, shell, `sys.argv` global ou outro CLI.
3. Subcomandos canônicos têm precedência absoluta. `service`, `serve`, `work`, `admin` etc. nunca são candidatos a harness.
4. Aliases raiz pertencem a uma allowlist derivada do registro de harnesses públicos. Comando raiz desconhecido retorna erro e ajuda; o fallback de seleção para harness desconhecido vale dentro de `connect`.
5. Remover o `choices=` do argumento que precisa de recuperação interativa; validar depois do parse completo. Sintaxe inválida continua erro de gramática.
6. Usar `allow_abbrev=False` nos parsers envolvidos. Um flag digitado incorretamente não pode ser abreviação de uma opção com efeitos.
7. Consumir os argumentos próprios antes de encaminhar opções de serviço. Validar a sobra contra o parser real do serviço; não enviar posicionais sobrando ou flags desconhecidos até um `ensure_running`.
8. `--help`, alias `--help`, excesso de posicionais, opções conflitantes e erro sintático não abrem cofre, serviço, inventário ou reserva.
9. O parser precisa funcionar no Python mínimo 3.11. Não utilizar facilidades recentes de argparse sem fallback comprovado. [W01]
10. Exemplos com espaços exigem aspas do shell: `connect codex "Minha aplicação"`. O programa recebe argv já separado; não faz uma nova interpretação por shell.

### Combinações e conflitos

| Entrada | Resultado |
|---|---|
| `connect codex app` | harness=codex; nome lógico=app; raiz=CWD. |
| `connect codex app --project /repo` | nome lógico=app; raiz explícita=/repo. |
| `connect codex --client codex` | Aceitar redundância concordante e normalizar uma vez. |
| `connect codex --client claude` | `ARGUMENT_CONFLICT`, antes de efeitos. |
| `connect --client codex --project .` | Legado preservado; não reinterpretar `.` como label. |
| `connect --client codex app` | Não adivinhar: o posicional app é harness e conflita; orientar `connect codex app`. |
| `connect codex app extra` | Erro de gramática. |
| `connect codex --profile old --id reviewer` | Revalidar se profile e ID resolvem a mesma conexão; não permitir precedência silenciosa. |
| `connect codex app --workspace-id W` | W é identidade exata; nome precisa corresponder ao catálogo atual, ou erro/revisão sem renomear W. |
| `connect --id reviewer` | Resolver projeto; se reviewer existir, inferir seu harness após revalidação; se não, pedir harness. |
| `connect codex --new-connection --id reviewer` e ID já vinculado | Conflito: uma intenção de adicionar não pode retomar implicitamente. |
| `connect codex app --mode participant` | Neste contrato, erro específico de combinação não suportada; orientar fluxo participant legado sem iniciar setup. |

`--agent` seleciona identidade canônica; `--new-agent` propõe uma identidade; `--name` é nome de apresentação; `--profile` é atalho local; `--id` é o identificador público da conexão. Combinações devem concordar na tupla canônica, não em semelhança textual.

## 3.2 Registro único de harnesses

Reutilizar `project_preset.CLIENTS` como origem inicial do mapeamento público para adaptador (`codex`, `claude`, `pi`), ou extrair uma função declarativa compartilhada sem mudar defaults de preset. Não manter três listas divergentes em help/parser/picker.

O registro de tokens aceitos não é prova de instalação, versão qualificada, login do provedor ou autoridade. Esses estados permanecem distintos na apresentação.

Normalize somente tokens de harness: `Codex` pode virar `codex`, com aliases conhecidos explicitamente documentados. Não fazer correção fuzzy e executar automaticamente. Um `codxe` pode sugerir Codex, mas a pessoa confirma a escolha.

## 3.3 Exemplos de recuperação interativa

```text
Harness “codxe” não reconhecido.
Escolha um harness com integração disponível neste host:
  1. Codex       — detectado; prontidão ainda não verificada
  2. Claude Code — detectado; prontidão ainda não verificada
  3. Pi          — não detectado
  0. Cancelar
```

Um harness suportado mas não detectado explica o motivo e oferece outro candidato ou cancelar; não executa instalação automática. Múltiplas instalações do mesmo harness exigem escolha por candidato. Inventário inacessível/desatualizado é “não confirmado”, nunca “não instalado”.

Somente candidatos aprováveis pelo contrato atual podem seguir ao teste. Verificação de versão/protocolo e teste com modelo permanecem efeitos consentidos, não parte oculta da listagem.

---

# 4. CWD, Git e seleção do nome do projeto

## 4.1 Separar sugestão, seleção e autorização

| Conceito | Significado |
|---|---|
| `invocation_cwd` | Diretório de onde o comando partiu, capturado uma vez. |
| `physical_context_root` | `--project` explícito, se fornecido; senão CWD. É também a base da descoberta Git local. |
| `git_worktree_root` | Raiz que o Git identifica para o checkout que contém o contexto físico, quando comprovável. Só metadado/sugestão, não permissão. |
| `project_name` | Nome escolhido para exibir/localizar ou propor um projeto; não é um caminho nem identidade. |
| `project_name_source` | `explicit`, `existing_nexus`, `git_origin`, `git_worktree`, `directory` ou `manual`. |
| `execution_root` | Diretório efetivamente aprovado para executar o harness. Não muda por descobrir a raiz Git. |
| `workspace_id` | Identidade canônica do projeto. Nome do repo, URL, branch e basename não a substituem. |
| Mapeamento do host | Associação aprovada de executor/realização a uma raiz; continua sendo a fonte de verdade da execução. |

**Exemplo decisivo:** em `/repos/monorepo/apps/api`, Git pode sugerir `monorepo`, mas a raiz padrão de execução continua `/repos/monorepo/apps/api`. Usar `/repos/monorepo` exige escolha explícita, revisão atual e as validações de diretório existentes. Dois clones ou worktrees com o mesmo origin não viram o mesmo workspace automaticamente.

Se `--project /repos/B` estiver explícito e CWD for `/repos/A`, a descoberta parte de B. O contexto original A pode constar no resumo quando útil, mas não fornece o nome do repo para B. Não chamar `os.chdir` global.

## 4.2 Precedência fechada

1. **Seletores explícitos concordantes.** `--workspace-id`, perfil/binding exatos e nome posicional são restrições, não uma disputa em que o último argumento vence. Nome informado prevalece sobre sugestões automáticas; se contradiz a identidade exata selecionada, retornar conflito ou solicitar correção, sem renomear o projeto existente.
2. **Associação Nexus válida da raiz física.** Sem nome explícito, um workspace confirmado é reutilizado e seu nome preservado. Não consultar Git para tentar renomeá-lo. Várias associações exigem seleção.
3. **Origin local inequívoco do checkout.** Para sugerir o nome de um projeto ainda não resolvido, extrair o último componente do caminho do `remote.origin.url` válido e retirar apenas o sufixo terminal `.git`. Não usar branch, owner, host ou nome do perfil.
4. **Basename da raiz do working tree.** Usar quando Git comprovou a raiz, mas origin está ausente, inválido ou ambíguo. Não selecionar `upstream`, outro remote ou o primeiro de uma lista por conveniência.
5. **Basename da raiz física selecionada.** Fallback quando Git está indisponível, não identifica working tree ou não fornece dado utilizável. Com `--project`, o basename é dele; caso contrário é o CWD. Se vazio, impróprio ou inválido para label, pedir nome explícito em vez de inventar.

Nome obtido de Git é **sugestão**. Ele pode pré-preencher “Registrar novo projeto” ou ordenar correspondências, mas nunca autoriza unir projetos por nome/URL. Quando a sugestão coincidir com projeto de raiz diferente, aplicar 4.5. Nomes homônimos permanecem desambiguados por workspace e metadados autorizados.

## 4.3 Descoberta Git somente local e limitada

Implementar um adaptador de leitura pequeno e testável. Não usar APIs GitHub/GitLab, `fetch`, `pull`, `ls-remote`, autenticação, credential helper, SSH, checkout, clone, hooks, filtros, Git status ou instalação automática. A fonte é a configuração já disponível na máquina, não o estado de um servidor remoto.

`git rev-parse --show-toplevel` identifica o diretório do working tree; ausência de working tree é um resultado possível, não motivo para criar um. Git oferece consulta de configuração por escopos, incluindo opções para suprimir includes, e possui metadados compartilhados/específicos de worktree. Usar essas interfaces, sem presumir que `.git` seja sempre uma pasta. [W03–W05]

**Contrato do runner proposto:**

- Executável Git de instalação confiável encontrado pelo mecanismo da aplicação/ambiente do usuário. Não acrescentar CWD/repositório à busca; recusar resultados baseados em entradas relativas inseguras ou um `git`/`git.exe` do próprio projeto. Não há necessidade de procurar o binário no disco inteiro.
- Argumentos como vetor, `shell=False`, stdin fechado, pager e prompts desabilitados. Allowlist estrita de leitura `rev-parse` e `config`; nenhum argumento executável vem de um remote ou label.
- Sanear, para esse processo de descoberta, overrides que desviem o repo ou injetem configuração, como `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` e `GIT_CONFIG_COUNT`/pares. Não modificar o ambiente global do usuário. Não reescrever nem contornar `safe.directory`.
- Orçamento inicial proposto: até 2 segundos para a descoberta inteira, até 6 invocações locais e até 64 KiB por resposta, com limite total documentado. Encerrar os processos próprios no timeout. Não repetir indefinidamente nem bloquear o primeiro uso; medir nas plataformas suportadas.
- Para origin, consultar exclusivamente a configuração local efetiva do repo/working tree, de forma limitada e sem includes externos. Valores origin globais/sistema e regras `insteadOf` não devem redirecionar a sugestão. Se a versão Git/plataforma não permitir determinar escopo com segurança, usar fallback com motivo explícito.
- Uma base de leitura possível é `git -C <root> config --local --no-includes --null --get-all remote.origin.url`, complementada somente quando necessário para configuração de worktree comprovada. O Codex deve testar a sintaxe na versão Git suportada; não supor que essa linha isolada cubra worktreeConfig. Ler a configuração específica sem habilitar ou alterar a extensão.
- Distinguir: Git ausente; fora de repo; bare sem working tree; origin ausente; origin ambíguo/inválido; timeout; config inacessível; propriedade duvidosa. Essas falhas degradam **a sugestão do nome**, não a validação de projeto/autoridade do Nexus.

Os retornos do Git não são confiáveis por definição. Raiz Git precisa ser um diretório coerente com o checkout/contexto observado; um `core.worktree` inesperado não autoriza sair do contexto selecionado. Não ler instruções, scripts ou manifests do projeto para inferir credenciais, comandos ou permissões.

### Parsing de origin e segurança da saída

Aceitar formas localmente parseáveis: HTTPS/HTTP, SSH URL, SCP-like (`git@host:org/repo.git`), `file://` e paths locais de remote. O parser distingue drive Windows de sintaxe SCP. Outros transports/remote helpers produzem fallback; nunca invocá-los.

Usar só o último componente de caminho não vazio, retirando um `.git` terminal. Validar o candidato pelo contrato do label do Nexus. Não transformar `%2f`, `%5c`, controles ou invisíveis em um caminho/label executável; não fazer decoding ou sanitização que oculte uma ambiguidade. Se for inválido, seguir o fallback e explicar a origem efetivamente usada.

**Múltiplos valores distintos de origin são ambiguidade**, ainda que terminem no mesmo basename. Valores exatamente repetidos podem ser deduplicados; não usar o primeiro/último silenciosamente. O ID de Harness continua derivado do harness, não do origin.

URL completa, userinfo, tokens, query e fragmento não aparecem na UI, stdout/stderr, JSON, logs, reserva, fingerprint persistido ou telemetria. Persistir apenas nome candidato/selecionado, source e reason, e raiz descoberta quando necessária e autorizada. Capturas de exceções nunca imprimem stderr/config bruto. Não prometer que uma remoção de URL detecta todo dado sensível possível; validar/minimizar o label também.

### Worktrees, submodules e monorepos

Working tree ligado usa seu checkout atual, não o diretório de metadados `.git/worktrees/...` como nome. Configuração comum e de worktree são tratadas por escopo; conflitos de valores usam fallback. Sem origin, o basename é o do working tree atual, não o de outro checkout.

Submodule ou repo aninhado usa o repositório mais próximo identificado pelo Git; não promover automaticamente ao superproject. Branch/detached HEAD não muda a regra do nome. Em monorepo, sugerir o nome do repo não junta projetos já separados, não muda o diretório e não define uma nova política de autorização.

## 4.4 Resolver e apresentar o projeto

**A. Capturar entradas físicas.** Validar CWD/`--project` e preservar as rotinas existentes de canonicalização e `directory_identity`. Diretório inacessível não vira home do usuário. Não mudar `_same_local_path` globalmente.

**B. Fixar destino.** Resolver Server/home/operator-profile antes de procurar workspaces. Não selecionar outro Server por ter um projeto homônimo. Falha do remoto não inicia um Server local substituto.

**C. Aplicar restrições e associação Nexus.** Resolver IDs/perfil exatos e a associação da raiz antes de descoberta Git. Catálogo incompleto/inacessível é `PROJECT_CATALOG_UNCONFIRMED`, não “nenhum projeto”.

**D. Sugerir nome quando necessário.** Usar a cadeia 4.2 com provenance. Isso pode ser feito localmente antes/depois das leituras autorizadas, mas não substitui a obrigatoriedade de completude do catálogo. Sem associação inequívoca, mostrar projetos e “Registrar este diretório como novo projeto”, com a sugestão preenchida.

**E. Fechar seleção na revisão.** O usuário pode personalizar o nome, escolher projeto existente ou cancelar. Seleções não gravam workspace. A revisão final reúne nome/origem e raiz de execução com o restante dos efeitos; não pedir uma confirmação isolada do nome e depois outra igual do setup.

| Contexto | Decisão |
|---|---|
| Nome/ID exatos compatíveis | Preservar; Git não substitui a escolha. |
| Perfil/binding salvo compatível | Reutilizar o nome/ID/raiz salvos e revalidar fonte canônica; não redescobrir Git para renomear. |
| Root associado a um workspace | Reutilizar e exibir `existing_nexus`. |
| Root associado a vários workspaces | Lista autorizada; nenhuma escolha por recência. |
| Root sem associação e origin utilizável | Pré-preencher sugestão `git_origin`, sujeita à seleção/revisão. |
| Origin não utilizável, working tree válido | Pré-preencher basename com `git_worktree` e motivo resumido. |
| Sem Git utilizável | Basename físico com `directory` e motivo apropriado. |
| Label derivado coincide com vários workspaces | Desambiguar; Git não prova qual deles é correto. |
| Catálogo falha | Recusar seleção; fallback Git não converte a falha em permissão para criar. |

## 4.5 Nome do repo não expande raiz de execução

Raiz efetiva começa como `--project` ou CWD. Raiz Git pode ser exibida como informação secundária ou opção em Personalizar, nunca aplicada silenciosamente.

Exemplo: CWD `/repos/A`; projeto B já mapeado a `/repos/B`. Em TTY pode-se oferecer usar explicitamente a raiz aprovada de B, selecionar outro projeto ou cancelar. Se `--project /repos/A` estiver explícito, é uma restrição: pedir correção em nova invocação, não substituir a flag. Fora de TTY retornar `PROJECT_DIRECTORY_MISMATCH` com apenas os detalhes autorizados.

Mudar para uma raiz ancestral é uma mudança de escopo potencial e entra na revisão; não basta mostrar “nome vindo do Git” para autorizar. Associar outra raiz a um workspace existente continua usando os contratos atuais, não uma associação implícita por label. Git no computador do operador remoto não prova diretório, repo ou identidade no host Connector.

## 4.6 Revisão, retomada e modo plan

Nome escolhido, origem segura, raiz e ID proposto entram na intenção persistida. Alterar esses dados por Personalizar recompõe o fingerprint da revisão; `--approve` antigo é recusado. Depois de aprovar, recuperar a intenção congelada — não renomear projeto/ID porque o origin ou a branch mudaram.

Se somente metadados Git mudarem depois da confirmação, o nome aprovado permanece; isso não modifica permissões nem invalida por si só a identidade do diretório. Mudança real de raiz, link, mapeamento, host ou autoridade continua sendo revalidada pelos contratos canônicos e pode bloquear o setup.

**Compatibilidade de `--plan`:** conservar o contrato de não executar subprocessos de descoberta/probe. Não chamar Git nesse modo. Usar uma seleção previamente salva e concordante, se existente, identificando-a como saved; sem ela, aplicar o fallback de diretório/nome explícito e informar `git_discovery=not_run_plan`. Não afirmar que consultou origin. A aplicação por `--approve` usa o nome revisado, não o substitui por uma nova descoberta Git. O comando interativo comum pode ler os metadados Git locais antes da revisão, mas não faz alterações Git.

## 4.7 Projeto novo

Registrar projeto continua significando criar o workspace e o mapeamento no setup aprovado, usando pasta existente. Não fazer `mkdir`, `git init`, clone, checkout ou instalação durante seleção/confirmar/cancelar.

O namespace público do ID depende do workspace canônico, não de um nome Git. Dois processos iniciando no mesmo diretório precisam reconciliar drafts conforme o capítulo 6. Dois clones ou projetos homônimos não podem compartilhar uma identidade de projeto por inferência.

---

# 5. ID do Harness (`--id`): nome público, unicidade e colisões

## 5.1 Nome público, chave técnica e escopo

O usuário escolhe `--id reviewer` e vê **ID do Harness: reviewer**. Nas superfícies atualmente em inglês, usar **Harness ID**. O nome significa a conexão daquele harness no projeto, não a família Codex/Claude/Pi nem o processo/sessão momentâneo.

**Usar `connect_id` como chave técnica única** no envelope Quick Connect, nos DTOs e no armazenamento. Não introduzir um segundo campo independente chamado `harness_id` e não renomear `agent_id` ou `connection_id`. `--id` é o parâmetro público. Se o checkout tiver um schema já publicado para a mesma finalidade, registrar sua compatibilidade antes de modificá-lo, sem dois caminhos de escrita divergentes.

| Conceito | Responsabilidade |
|---|---|
| ID do Harness / `connect_id` | Nome amigável estável de uma conexão em um workspace do Server. |
| Harness / `harness` | Família selecionada: codex, claude, pi etc. |
| `agent_id` | Identidade de coordenação e permissões. Não muda por rótulo. |
| `binding_id` e referência completa | Associação canônica de execução validada. |
| `session_id` | Cada contexto de execução; várias sessões podem compartilhar um ID do Harness. |
| `profile` | Atalho técnico local de configuração/checkpoints. Fica no JSON/detalhes/ajuda avançada e na compatibilidade dos scripts. |
| Papel generalista | Função do agente/preset; se exibido, rotular Função do agente. Nunca chamar de ID nem de perfil identificador. |
| `setup_intent_id` | Intenção idempotente de configuração, distinta do ID amigável. |

No fluxo básico, não pedir nome de profile nem imprimir “Perfil: Assistente de projeto” como identificação. O resumo usa harness, projeto, diretório e ID do Harness; permissões/efeitos continuam claros, em linguagem legível.

Namespace definitivo: **`(server_id, workspace_id, normalized_connect_id)`**. O ID é único no projeto inteiro, independentemente de agente, família de harness ou máquina. Projetos/Servers diferentes podem usar o mesmo nome. Uma resolução pelo nome nunca concede autoridade.

## 5.2 Validação e geração

Aceitar 1–64 caracteres ASCII, começando por letra, com letras/dígitos/`_`/`-` depois; normalizar letras para minúsculas e mostrar o resultado na revisão. Recusar paths, controles, espaços/invisíveis e truncamento silencioso. Não aplicar essa regra retroativamente a IDs canônicos antigos. Não usar ID do Harness como nome de arquivo.

Sem `--id`, a base automática é o **harness selecionado**, não o projeto, o Git, a branch ou o papel do agente: `codex`, `claude`, `pi`. Depois de uma escolha de adicionar, propor `codex-2`, `codex-3` etc. se necessário. Uma repetição simples não cria outro harness.

Consultar disponibilidade é uma prévia, não garantia. A reserva transacional garante exclusividade. Se a proposta aprovada colidir antes de reservar, exigir proposta/revisão nova; não aprovar o próximo sufixo automaticamente. Salvar proposta e intenção para que retries não gerem nomes novos.

IDs já vinculados não são reciclados silenciosamente após remoção/desativação. Tombstone/histórico impede que um comando antigo abra outro binding. Associação de nome a uma conexão antiga é só metadado autorizado, não novo setup produtivo.

## 5.3 Matriz definitiva de colisão

| Caso | TTY | JSON / não interativo |
|---|---|---|
| Sem ID e sem conexão | Propor nova conexão e ID automático. | Exigir seletores/intenção estáveis conforme contrato anterior; não adivinhar projeto. |
| Sem ID e há conexões | Picker retomar/adicionar/cancelar. | Seleção requerida se ambíguo; sem novo ID alternativo automático. |
| ID existente, mesmo harness e seletores concordantes | Oferecer Retomar como opção principal, Adicionar outra com outro ID e Cancelar. A escolha explícita com resumo pode concluir a confirmação de retomada. | Sem `--new-connection`, a seleção exata pode retomar determinísticamente após revalidação; nenhuma nova autorização/teste. |
| ID existente, harness diferente | Exibir o harness real. Permitir usar a conexão existente explicitamente, escolher outro ID, solicitar sugestão ou cancelar, observadas as restrições de 5.5. | `HARNESS_ID_ALREADY_EXISTS`, sem substituição do harness/ID. |
| `--new-connection` com ID ocupado por outra intenção | Somente outro ID, sugestão ou cancelar. Não oferecer retomar como resultado da adição. | Conflito estruturado. |
| ID reservado pela própria intenção recuperável | Recuperar essa intenção. | Recuperar mesma intenção/recibo, inclusive retry com `--new-connection`. |
| ID reservado por outra intenção | Mostrar ocupado/pendente e opções de outro ID/cancelamento, sem tomar a reserva. | Pending/conflito conforme estado confirmado; nunca “livre” por falta de resposta. |
| ID revogado, desabilitado ou retired | Mostrar diagnóstico/estado; não reativar, não reciclar nem renovar grant. | Retorno de indisponibilidade/conflito, preservando a ocupação. |
| IDs/flags exatos apontam a conexões diferentes | Recusar inconsistência; não usar menu para ignorar `--profile`, `--agent`, `--binding-id` ou root explícitos. | `ARGUMENT_CONFLICT`/equivalente; nenhum selector vence silenciosamente. |
| ID de conexão inacessível | Mensagem genérica sem detalhes que o solicitante não pode ver. | Mesma proteção de autorização; não enumerar material privado. |

**Precedência de recuperação:** antes de declarar ID ocupado, tentar recuperar a intenção explicitamente retida e validar seu fingerprint. A própria criação commitada é resultado recuperável, não colisão. O texto do ID sozinho não prova que duas invocações sejam a mesma intenção. Mudança de harness/root/ID numa intenção pendente não é retry válido.

## 5.4 Exemplo de conflito entre harnesses

```text
$ okto-nexus connect claude --id implementer

O ID do Harness "implementer" já está em uso neste projeto.

Conexão existente:
  ID do Harness: implementer
  Harness:       Codex
  Projeto:       okto-nexus
  Estado:        conforme a fonte canônica atual

O que deseja fazer?
  1. Utilizar a conexão existente (Codex)
  2. Escolher outro ID para o Claude
  3. Sugerir um ID para o Claude
  0. Cancelar
```

Estado e host só aparecem quando confirmados/autorizados; não escrever “Conectado” a partir da mera existência do registro. Se houve `--new-connection`, a opção 1 não aparece. IDs candidatos exibidos na opção 3 ainda não estão reservados nem são uma conexão concluída.

A opção 1 é uma **mudança explícita de intenção do usuário**, não conversão automática. A tela final deve dizer Codex/implementer, conservar o pedido original para diagnóstico não sensível quando apropriado e revalidar a referência real. Uma configuração/admissão anterior de Claude não é reutilizada para Codex.

Ao escolher outro ID, o harness solicitado permanece Claude. Ao pedir sugestão, ela vem de `claude`/`claude-2`, não do harness que ocupa o nome. Ao cancelar, não há setup/teste/grant/rename; efeitos de serviço/metadados já solicitados são relatados corretamente e não desfeitos arbitrariamente.

## 5.5 Restrições à escolha da conexão existente

A opção de utilizar a existente só é oferecida quando ela está visível, é elegível para retomada e seus seletores exatos são compatíveis. Não ignorar um `--agent`, perfil, binding, workspace, host ou `--project` que aponte a outro contexto. Nessa situação, pedir correção dos argumentos ou outro ID; não produzir uma configuração inesperada.

Se a raiz do binding difere do CWD sem `--project` explícito, aplicar o fluxo de escolha de raiz do capítulo 4 e incluir a mudança no resumo. Nome igual nunca redireciona para outro Server/projeto/host sem decisão. Estado indisponível não impede diagnóstico, mas impede apresentar retomada como conexão operacional pronta.

Depois da seleção, revalidar revisões, namespace, tupla canônica e pendências antes de qualquer efeito. Colisão detectada no Server depois de uma escolha local retorna ao mesmo tratamento seguro. Não contornar política nem adicionar force-overwrite a esta feature.

## 5.6 Código e resposta estruturada de conflito

Código público proposto para colisão confirmada: **`HARNESS_ID_ALREADY_EXISTS`**. Se o checkout já publica `CONNECT_ID_CONFLICT`, conservar seu contrato interno/legado e mapear na fronteira pública Quick Connect com testes de compatibilidade; não alterar registros históricos. Não confundir com `CONNECT_ID_PENDING` ou resultado de setup desconhecido.

Exemplo do novo contrato; campos comuns legados de efeitos devem continuar presentes conforme o que realmente ocorreu:

```json
{
  "state": "conflict",
  "code": "HARNESS_ID_ALREADY_EXISTS",
  "quick_connect": {
    "version": 1,
    "status": "conflict",
    "connect_id": "implementer",
    "requested_harness": "claude",
    "suggested_connect_id": "claude",
    "suggestion_status": "not_reserved"
  }
}
```

O exemplo usa `connect_id` como a única chave técnica para o ID do Harness. A sugestão pode ser omitida/null quando indisponível ou sem autorização. Não enviar prompt por stdin e não aplicar automaticamente a sugestão em script. `possible_effect` e flags de lifecycle/metadados refletem o estágio real; não declarar “nenhum efeito” apenas porque o conflito precedeu o setup.

---

# 6. Persistência, atomicidade e recuperação do ID

## 6.1 Decisão arquitetural

Há dois mecanismos diferentes:

* **Reserva local de intenção:** protege o processo de onboarding e permite recuperar `profile`, seleção e setup ID. Reusar `connection_reservation.py`.
* **Registro público no Server:** garante unicidade por workspace e resolve o ID para a referência canônica. Precisa de persistência compartilhada; um JSON no computador do usuário não basta.

Não repurpor `configuration.alias`: seu namespace atual é mais estreito [S11]. Para novas conexões, os dois valores podem coincidir quando isso for compatível, mas o contrato público e suas restrições devem permanecer explícitos. Uma conexão antiga pode conservar alias interno diferente.

Proposta mínima: tabela/serviço auxiliar **`connection_public_ids`**, ou equivalente existente após auditoria, contendo `server_id`, namespace de projeto, `connect_id`, estado da reserva/vínculo, `setup_intent_id`, referência completa do binding quando disponível, revisão e timestamps. Não guardar chave, transcript, resultado ou autoridade de execução nessa estrutura.

Estados auxiliares sugeridos: `reserved`, `bound`, `retired`. Não são estados do runtime. Unicidade transacional no namespace; correlação idempotente com a intenção de setup; FK/validação para as referências apropriadas. Alterações e consultas usam os serviços do Server, não SQL escrito pelo CLI.

## 6.2 Workspace existente

1. Resolver e autorizar projeto/host/conexão; selecionar o ID proposto.
2. Persistir proposta na reserva local e incluir ID, namespace e intenção no material de revisão.
3. Após aprovação exata, reservar o ID no Server **antes do teste com modelo**; a operação tem idempotency key e fingerprint semântico.
4. Se o ID já foi tomado por outra intenção, parar antes do teste; apresentar outra proposta/revisão. Não aprovar automaticamente o próximo sufixo.
5. O Finish canônico vincula reserva→binding e grava `connect_id` no recibo, na mesma transação do setup.
6. Resposta perdida é recuperada pelo setup ID e pelo recibo; não repetir criação, grant ou teste.

A reserva é um efeito de metadados explícito. Não representa agente criado, sessão pronta ou execução autorizada. Não segurar transação de banco/lock global enquanto pede input ou aguarda provedor. Concorrência SQLite deve usar a estratégia transacional do projeto e tratar busy/conflict de forma limitada; UNIQUE e transação são a garantia, não um SELECT seguido de INSERT desprotegido. [W02]

## 6.3 Projeto novo sem workspace_id

Não inventar workspace_id em uma referência autorizada. Antes do Finish existe apenas uma **proposta de ID**, persistida na intenção, não um ID público definitivo.

Se o setup atual já dispõe de um draft estável de projeto, reutilizá-lo como namespace técnico temporário para exclusão. Caso não exista, usar um token opaco de reserva de projeto, criado pelo Server a partir do host e da identidade de diretório que ele pode comprovar, label e revisão aprovada. O token é metadado de preparação, não um workspace pronto nem permissão. Não armazenar path privado em índice público ou derivá-lo somente de texto enviado pelo cliente.

No Finish, criar/confirmar o workspace pelos serviços atuais e promover a reserva para `(server_id, workspace_id, connect_id)` na mesma transação que o binding e recibo. Se a resolução de projeto ficou obsoleta — por exemplo outro setup registrou o mesmo diretório/projeto no intervalo — abortar sem duplicação e exigir resolução/revisão nova. Não associar automaticamente a outra intenção, nem criar workspace vazio antecipado.

Quando o backend não puder provar exclusão de drafts equivalentes, não prometer unicidade definitiva antes do Finish. O aceite obrigatório continua: nenhum sucesso devolve dois bindings para o mesmo namespace/ID, e nenhum conflito cria efeitos canônicos parciais. Testes de corrida devem incluir dois primeiros connects no mesmo diretório e um label duplicado em outro projeto.

## 6.4 Atualização dos contratos existentes

Acrescentar um membro opcional e versionado de metadados públicos ao request/recibo de setup do Server — nome proposto `public_connection`. Deve conter somente a seleção de ID, modo proposto/explicitado e referência/revisão da reserva pertinente.

O membro participa do hash de revisão e da comparação idempotente. Atualizar validação HTTP, tipos, allowlists e persistência conjuntamente. Não inserir campos novos no objeto Core de configuração sem necessidade: transportar o metadado no envelope de produto preserva o protocolo nativo.

Requests antigos sem o membro continuam válidos e mantêm seus hashes/recibos. Não recalcular recibos históricos com defaults novos. Repetir um Finish antigo retorna seu resultado antigo. Recuperar/vincular o nome público de uma conexão antiga é uma operação de metadados separada, autorizada, por tupla canônica exata.

Extensões de API propostas, caso não haja equivalentes:

```text
GET  /api/v1/runtime-management/connections/public-ids?...  # resolve/exibe, sem escrita
POST /api/v1/runtime-management/connections/public-ids/reserve
POST /api/v1/runtime-management/connections/public-ids/associate-existing
```

Esses nomes são propostas. Preferir handlers/coordenadores equivalentes já existentes. O vínculo definitivo de uma conexão nova fica no Finish, não num POST posterior obrigatório. Associação de conexão antiga não chama Finish de configuração, não substitui binding e não concede grant.

## 6.5 Cancelamento, falha e limpeza

Antes de confirmar setup: cancelamento é cancelamento, nunca sucesso de conexão. Depois de emitir efeitos, Ctrl+C interrompe a observação e conserva checkpoints. Reserva cujo resultado não foi confirmado não é expirada/reutilizada às cegas.

Limpeza de reserva exige leitura dos recibos canônicos e prova de que não existe vínculo/teste/Finish em estado incerto. Prazo sozinho não prova ausência de efeitos. Expiração de um metadado não deve cancelar trabalho, liberar capacidade ou autorizar repetição.

Uma falha de gravação do atalho local depois do commit do Server retorna estado explícito `configured_shortcut_pending` com ID e referência canônicos recuperáveis. Não alegar que nada foi criado; não desfazer grants ou binding automaticamente. O próximo comando recupera e repara somente o atalho.

Lock order: adotar a ordem atual por profile e catálogo; qualquer extensão precisa de tabela de ordem única e teste de interleaving. Locks locais não substituem unicidade no Server, e não devem ficar bloqueando o catálogo durante uma pergunta interativa.

---

# 7. Fluxo completo e sucesso observável

## 7.1 Sequência de execução

```text
parse e validação sem efeitos
  → capturar CWD / raiz explícita / destino
  → normalizar harness público
  → iniciar/reutilizar Server local quando permitido (ou inspecionar em --plan)
  → obter catálogos autorizados e completos
  → preservar seletores/associação Nexus OU sugerir nome por Git/fallback
  → resolver projeto, proveniência do nome e raiz independente
  → resolver ID/conexão e intenção retomar/adicionar
  → selecionar instalação quando necessário
  → recuperar intenção pendente OU preparar revisão
  → confirmar revisão única com nome/origem, raiz, harness, ID e efeitos novos
  → reservar ID / executar setup canônico
  → recuperar e validar recibo / vincular ID definitivo
  → emitir resultado positivo com ID
  → entrar no prompt de trabalho somente quando compatível com TTY/--no-chat
```

Resolver um alias já vinculado pode evitar seleção de harness. Retomar conexão não exige que o mesmo executável exista no computador do operador quando a execução é remota; a evidência deve vir do host correspondente.

## 7.2 Revisão final única e resultado humano

O fluxo básico reúne num mesmo resumo:

```text
$ okto-nexus connect codex

Harness:           Codex
Projeto sugerido:  okto-nexus
Origem do nome:    Repositório Git (origin local)
Diretório atual:   /repos/okto-nexus/src
Executar em:       /repos/okto-nexus/src
ID do Harness:    codex
Host:              Este computador
Operação:          Criar conexão

Efeitos: registrar a conexão/identidade conforme o preset revisado,
configurar permissões e executar o teste de conexão descrito abaixo.
O teste pode consumir o provedor. Nenhuma tarefa do projeto será enviada.
[exibir limites e efeitos reais do setup canônico atual]

1. Confirmar a revisão
2. Personalizar
0. Cancelar
```

Exemplo ilustrativo. O nome vindo da raiz Git não altera `Executar em`; usar outra raiz passa por Personalizar. A função generalista/permissões podem ser resumidas, mas nunca ocupam o campo **ID do Harness**. Não colocar profile técnico na revisão básica.

**Uma confirmação final para os efeitos novos.** Seleção em lista, resolução de colisão e edição de campos preparam a revisão, não aprovam teste ou Finish. Personalizar retorna ao mesmo resumo e produz hash novo. Não somar uma confirmação do nome Git e outra confirmação idêntica do setup. Uma mudança adicional de efeitos, uma corrida ou uma etapa do protocolo que realmente exija consentimento distinto continua podendo demandar nova revisão; simplicidade não elimina essa proteção.

Retomada compatível não reaplica preset/teste/grant. A própria ação Retomar pode ser a confirmação final quando o resumo já identifica exatamente projeto, raiz, harness e ID, sem efeitos produtivos novos. Fora de TTY, usar seletores/revisão exatos; não perguntar.

Após Finish e ID bound confirmados, emitir antes de entrar no chat:

```text
Conexão configurada.
  ID do Harness: reviewer
  Harness:       Claude Code
  Projeto:       my-awesome-project
  Origem:        nome informado
  Diretório:     D:\Projetos\my-awesome-project
  Operação:      nova conexão
  Serviço:       em execução
  Sessão:        ainda não verificada

Para voltar:
  okto-nexus connect claude my-awesome-project --id reviewer
```

Na retomada, escrever “Conexão reutilizada” com o mesmo ID do Harness. IDs técnicos ficam no JSON/detalhe. Cancelamento/plano/reserva não usa essa mensagem positiva; teste temporário não é sessão de trabalho. `configured` não prova que o harness está executando uma tarefa.

## 7.3 Resultado estruturado

Preservar os campos existentes e acrescentar um envelope opcional/versionado, sem alterar à força consumidores antigos. Exemplo de contrato proposto:

```json
{
  "state": "configured",
  "server_id": "<server>",
  "agent_id": "<agent>",
  "workspace_id": "<workspace>",
  "binding_id": "<binding>",
  "profile": "<atalho-local>",
  "session_state": "not_checked",
  "work_state": "not_submitted",
  "quick_connect": {
    "version": 1,
    "status": "connected",
    "connect_id": "reviewer",
    "connect_id_status": "bound",
    "operation": "created",
    "harness": "claude",
    "project_name": "my-awesome-project",
    "project_name_source": "explicit",
    "name_discovery": {"status": "not_needed", "reason": "explicit_name"},
    "execution_location": "local",
    "project_root": "<raiz-local-aprovada>",
    "cwd_resolution": "exact_mapping",
    "resume_argv": ["okto-nexus", "connect", "claude", "my-awesome-project", "--id", "reviewer"]
  }
}
```

`project_name_source` informa a origem da escolha; para retomada salva, manter a provenance anterior e informar `name_discovery.status=saved` quando útil, sem afirmar redescoberta. `name_discovery` não contém URL/credencial Git. Campos são aditivos no envelope v1 e opcionais para clientes anteriores; não alterar recibos históricos.

`operation` permite `created`, `reused` ou `associated_existing`. `resume_argv` é um vetor, não string executada por shell. Na apresentação, escapar/quotar para a plataforma; não incluir segredos. Em remoto, não expor path do host se o contrato não o autoriza; usar null/metadado pertinente.

Regra testável: **`quick_connect.status=connected` implica `connect_id_status=bound`, ID não vazio e referência canônica revalidada.** Plano, reserva, cancelamento, teste pendente, configuração parcial e erro não satisfazem essa regra.

IDs propostos em `--plan` ficam em campo `proposed_connect_id`, nunca em `connect_id_status=bound`. `configured_shortcut_pending` é progresso parcial recuperável, não resultado positivo completo. Scripts não devem inferir conexão criada somente de exit 0, pois o contrato legado também usa 0 para plano/revisão/cancelamento. Preservar códigos existentes e documentar os estados.

## 7.4 Noninteractive, JSON e revisão

`--json` e stdin não TTY nunca abrem menus e nunca entram em chat. Harness/projeto/ID não resolvidos retornam `selection_required` com código, alternativas autorizadas, completude do catálogo e efeitos efetivamente solicitados. Opções inválidas são erros, não fallback para outra configuração.

Manter a regra 0.3.5 de que uma adição não interativa requer `--profile` estável. O novo `--id` não substitui o idempotency key do setup. Não derivar uma intenção apenas do nome do harness ou de uma combinação sujeita a colisões. Perfil técnico fica escondido no caminho interativo, mas continua disponível para automação.

Exemplo de automação proposta, usando serviço já pronto:

```sh
okto-nexus connect codex my-awesome-project --id builder --new-connection \
  --profile automation-builder --project /repos/app --plan --json

okto-nexus connect --profile automation-builder --approve <REVISAO_EXATA> --json
```

`--plan` não inicia serviço, não executa binário Git/harness/provedor e não reserva ID canônico novo. Aplica a regra de provenance salva/fallback explícito do capítulo 4; não precisa de Git para preparar uma revisão válida. Pode salvar proposta local como hoje. Revalidação canônica atual pode materializar metadados de revisão: preservar o relato `canonical_metadata_revalidation_requested`, sem prometer efeito zero indevidamente. [S05, S12]

O comando comum pode iniciar o daemon para obter catálogos. Um cancelamento depois desse passo não significa que nenhum efeito ocorreu; não parar o daemon automaticamente. Distinguir efeitos de lifecycle, metadados, teste e configuração quando preencher a resposta.

---

# 8. Compatibilidade e projeção na aplicação

## 8.1 Perfis e conexões antigos

Sem migração em massa no startup. Não renomear arquivos existentes, não alterar `agent_id`, não reemitir credenciais e não completar reservas antigas por suposição.

Um Quick Connect que seleciona uma conexão antiga sem ID oferece associar o nome automaticamente sugerido ou fornecido, por uma operação curta de metadados com revisão da referência atual. Após associar, devolver `associated_existing`; não repetir teste, Finish de setup, modelo, alteração de policies ou grant.

Chamadas legadas de leitura/retomada por perfil continuam funcionando sem associação forçada. Podem omitir o envelope `quick_connect` se não participaram do novo contrato; não inventar um ID definitivo. Toda chamada da nova experiência que declara `quick_connect.status=connected`, porém, precisa concluir a associação.

Se uma administração avançada substituir um binding, o ID público não pode seguir por semelhança de agente/nome. Uma transferência para o sucessor exige o fluxo canônico explícito de substituição, referência anterior e revisão validadas, alteração atômica e auditoria. Se esse fluxo não transportar o metadado no primeiro recorte, manter a referência antiga identificada como indisponível e exigir revisão; não apontar para outra sessão automaticamente.

O catálogo e a Home podem apresentar `connect_id` quando existente e o rótulo anterior quando ausente. GET não gera nem grava nomes públicos. Alterações no registry atualizam a revisão do catálogo para que paginação e caches não misturem versões.

## 8.2 UI, nomenclatura e coordenação

A Home/seletores existentes mostram, por exemplo, `reviewer · Claude Code`, com o rótulo ID do Harness/Harness ID quando o campo precisa ser nomeado. A função/preset generalista não substitui esse ID; profile técnico só aparece em detalhe avançado/JSON. O detalhamento continua baseado nos IDs canônicos, e várias sessões permanecem separadas. Não criar tela “IDs” ou “Quick Connect”.

Esse nome não passa automaticamente a ser alvo de MCP `send`, handoff ou autorização. Nesta entrega ele seleciona conexões no CLI e as identifica na UI. Um eventual roteamento de agentes por nome teria outro contrato para evitar confusão entre conexão e identidade.

A interface não transforma `--id` em rename global do agente. Ela pode mostrar o nome público da conexão e o nome/role do agente em lugares apropriados.

## 8.3 Remoto, Connector e participante MCP

No Server local, root=CWD/`--project` é caminho do host de execução. Em acesso remoto por `--operator-profile`, é apenas contexto/atalho local, salvo um mapeamento remoto aprovado que precisa ser explicitamente selecionado. Não resolver o path remoto pelo filesystem do cliente.

Retomar um binding remoto autorizado pelo catálogo continua permitido e pode usar um ID público já registrado. Criar uma conexão remota continua passando pelo Connector/remote setup atual. `--new-connection` não deve começar um Server local como fallback quando o remoto estiver indisponível.

IDs públicos ficam no Server para evitar colisão entre máquinas. Não incluir metadados novos em mensagens Core/Connector sem contrato validado; a referência pode ser projetada pelo catálogo sem mudar o protocolo de execução. Clients antigos que desconhecem o ID preservam seu binding e rótulos atuais.

`--mode participant` é preservado no CLI legado. A gramática curta cobre execução gerenciada; rejeitar a mistura de posicionais/`--id` novos com participant com ajuda específica, sem reinterpretar alias como credencial ou adaptador. Expandir a feature para participantes é evolução separada, não requisito escondido de reescrever esse subsistema.

---

# 9. Organização da implementação

## 9.1 Mudanças existentes e propostas

| Área | Arquivos existentes a revisar | Delta |
|---|---|---|
| Entrada | `adapters/inbound/cli/main.py` | Allowlist de aliases e ajuda; corrigir erro genérico que hoje menciona MCP stdio para comandos desconhecidos. |
| Parser/fluxo | `adapters/inbound/cli/connect.py` | Normalização da nova gramática, resolução antes de setup e resumo de sucesso. |
| Catálogos CLI | `connection_choices.py`, `connection_picker.py`, `canonical_connections.py`, `connection_project.py` | Name/root/ID, picker de recuperação, conflitos e completude. |
| Intenção | `connection_reservation.py` | Persistir seleção/ID proposto e recuperar a mesma operação. |
| Facade | `application/terminal_connection.py` | Transportar metadados versionados na revisão e recuperar ID pelo recibo. |
| Catálogo Server | `application/connection_catalog.py`, `adapters/outbound/sqlite/connection_catalog.py` | Expor ID e revisão, resolver namespace sob autorização. |
| Setup | `application/connection_setup.py`, handlers/tipos HTTP correspondentes | Reserva/vínculo na transação certa; requests legados preservados. |
| Diretórios | `application/execution_local_realizations.py` e utilitários existentes | Reusar provas de diretório; Git não altera root/autoridade. |
| Sugestão Git (nova) | Adaptador local pequeno proposto, isolado de domínio/HTTP | Leitura limitada, parsing seguro, provenance mínima, fallback e testes worktree/submodule. |
| Preset | `application/project_preset.py` | Fonte declarativa de tokens/adaptadores, sem alterar permissões. |
| UI | Projeções/seletores de conexões da Home e do onboarding no checkout real | Exibir ID já registrado; nada de nova navegação. |
| Docs/testes | `docs/terminal-connect.md`, help e suites atuais | Exemplos novos + testes de regressão e recibos. |

Arquivos novos sugeridos, apenas quando a separação trouxer clareza: `quick_connect_args.py` (funções puras), `quick_connect_resolution.py`, `connection_public_ids.py` (serviço/porta/adapter) e `quick_connect_output.py`. Para Git, um adaptador `git_project_hint.py` ou equivalente segue o padrão real de subprocessos; domínio/resolução recebe um DTO simples, não chama shell. Não criar framework genérico de comandos nem replicar o serviço atual. As paths propostas devem seguir as fronteiras reais do repositório.

## 9.2 Contratos internos sugeridos

Definir DTOs tipados antes de alterar o fluxo principal:

```text
QuickConnectIntent
  invocation_style: canonical | shorthand | legacy
  requested_harness: string|null
  requested_project_name: string|null
  requested_connect_id: string|null
  explicit_project_path / profile / workspace / topology selectors
  interactive / json / plan / approve_revision / new_connection

ResolvedProject
  server_id, workspace_id|null, display_name
  invocation_cwd, execution_root|null, host_ref
  resolution_source, mapping_revision, directory_evidence_ref
  new_project_intent_ref|null

ResolvedConnectionChoice
  action: resume | add | recover | associate_existing
  full canonical binding_ref|null
  profile, setup_intent_id, requested/proposed_connect_id
  public_id_revision/reservation_ref|null
  catalog_complete, issues, pending_checkpoint_ref

QuickConnectOutcome
  version, status, connect_id|null, proposed_connect_id|null
  operation, canonical_refs, profile, effects, resume_argv
```

Não passar esses DTOs diretamente para Core. Normalizar de forma pura, selecionar usando fontes autorizadas e converter para o envelope canônico. Não usar `any`/dicionários abertos para contornar validação.

## 9.3 Estados de erro mínimos

| Código proposto | Significado / comportamento |
|---|---|
| `HARNESS_UNKNOWN` | Token não reconhecido; menu em TTY, erro estruturado fora dele. |
| `HARNESS_NOT_DETECTED` | Inventário completo não encontrou instalação; explicar, não instalar. |
| `HARNESS_INVENTORY_UNCONFIRMED` | Fonte incompleta/stale; não escolher fallback silencioso. |
| `PROJECT_SELECTION_REQUIRED` | Mais de um candidato ou nenhuma seleção definida. |
| `PROJECT_DIRECTORY_MISMATCH` | Nome/ID e raiz não concordam; exige decisão explícita/correção. |
| `PROJECT_CATALOG_UNCONFIRMED` | Não foi possível provar lista completa; Git não transforma essa falha em permissão para criar. |
| `CONNECT_ID_INVALID` | ID do Harness viola a gramática; mensagem humana usa o rótulo público. |
| `HARNESS_ID_ALREADY_EXISTS` | ID do Harness pertence a outra conexão; menu/erro conforme intenção. Mapear código interno/legado CONNECT_ID_CONFLICT sem sobrescrever histórico. |
| `CONNECT_ID_PENDING` | Registro reservado/resultado ainda não confirmado. |
| `CONNECT_ID_UNSUPPORTED_SERVER` | Server antigo não suporta garantia do novo ID; não produzir pseudo-sucesso. |
| `ARGUMENT_CONFLICT` | Posicional/flag/perfil contraditório; nenhum efeito de setup. |
| `QUICK_CONNECT_MODE_UNSUPPORTED` | Nova gramática misturada a modo fora deste contrato. |

Preferir códigos equivalentes já existentes, com compatibilidade documentada. Mensagens exibem decisão prática e comando para correção, sem vazar segredos. Resultados incertos mantêm `possible_effect` e checkpoint; não são convertidos em falha limpa.

---

# 10. Migração, isolamento e rollback

Migrações de metadados públicos são aditivas e usam a próxima revisão real do checkout. Não escolher número de migration neste documento. Registrar índices/constraints e testar colisões/replay.

Clientes antigos não precisam conhecer o novo membro opcional. Cliente novo em Server antigo deve detectar capacidade antes de gravar, retornando instrução para upgrade/fluxo legado; nunca declarar unicidade global com cache local.

Se a nova camada for desabilitada, flags e perfis antigos continuam funcionando; dados de ID são preservados e os executores continuam. Não restaurar banco anterior nem apagar vínculos enquanto agentes estão ativos.

Requests/recibos antigos precisam de testes golden: ausência do campo novo não altera hash ou política. Retenção de IDs aposentados não deve depender da retenção curta de eventos de runtime.

Metadados Git não são enviados ao Server em formato bruto. Proveniência mínima participa do envelope somente quando necessária; nenhum URL ou hash reversível de credencial é armazenado. A sugestão Git não autentica o proprietário do repo nem prova seu acesso ao workspace.

Segredos ficam nos cofres e mecanismos existentes. Nenhuma opção nova recebe token em argv; nenhuma saída de sucesso contém chave de agente, cookie, segredo de provedor ou conteúdo do prompt. Nomes de catálogo passam por escaping de terminal e JSON, não por interpretação como comandos.

# 11. Etapas de implementação e marcos

| Etapa | Conteúdo | Gate |
|---|---|---|
| QC-00 | Baseline, contratos, compatibilidade e fixtures | G0: regras fechadas e delta confirmado. |
| QC-01 | Gramática, aliases raiz, recuperação de harness e vocabulário público | G1: parser/ID do Harness sem efeitos indevidos. |
| QC-02 | CWD, sugestão Git/fallback, projeto lógico e raiz explícita | G2: nome útil sem associação ou ampliação implícitas. |
| QC-03 | ID do Harness, reserva, Finish, colisões e associação antiga | G3: unicidade/decisão explícita/recuperação comprovadas. |
| QC-04 | Revisão final única, fluxo ponta a ponta e saída positiva | G4: primeiro e segundo harness sem profile manual nem dupla confirmação redundante. |
| QC-05 | Compatibilidade UI/legado/remoto e hardening | G5: nenhuma regressão de autoridade ou navegação. |
| QC-06 | Qualificação, docs, pacote e relatório | G6: entrega rastreável; limitações não executadas explícitas. |

QC-01 e partes de QC-02 podem avançar em paralelo depois dos contratos. Não liberar “Quick Connect concluído” só com novos argumentos; ID persistente e resultado recuperável são parte obrigatória. Não alterar a Home inteira para suportar um campo de identificação.

A próxima seção contém tarefas pequenas e seus testes. `IMPLEMENTED` não significa `VERIFIED`. Estados do ledger: tarefas `TODO/IN_PROGRESS/IMPLEMENTED/VERIFIED/BLOCKED`; cenários `NOT_RUN/PASS/FAIL/BLOCKED`. Prova reutilizada deve registrar SHA/ambiente e ser repetida quando as fronteiras afetadas mudarem.


# 12. Backlog executável

Todas as tarefas abaixo fazem parte da entrega inicial. Seus IDs seguem a ordem de implementação; as dependências são obrigatórias. Cada tarefa começa em `TODO`. Registrar arquivos, commit e evidências ao avançar. Reutilizar um mecanismo existente só atende à tarefa quando os critérios correspondentes forem verificados.

## QC-00 — Baseline, contratos e fixtures

**Gate:** G0: escopo reconciliado e regras fechadas.

### QC-001 — Reconciliar o checkout e a implementação existente

**Estado:** TODO. **Dependências:** nenhuma.  
**Requisitos:** QC-R16, QC-R20.  
**Áreas:** AGENTS.md/CI; connect.py; registros existentes de desenvolvimento da UI e do onboarding.

1. Registrar branch, HEAD, status e mudanças em curso; preservar trabalho local.
2. Comparar módulos citados com o snapshot; identificar testes existentes e fontes de schema.
3. Registrar o que já atende a esta especificação e as diferenças de contrato; reaproveitar a Home, o onboarding e os mecanismos de conexão já implementados.
4. Registrar diferenças entre o snapshot de referência e o checkout real. Inicializar o ledger deste pacote sem modificar os registros e as evidências dos demais trabalhos em andamento.

**Aceite:** Baseline e mapa de delta verificáveis; nenhum reset/checkout destrutivo.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16, QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-002 — Fixar gramática e decisões de resolução

**Estado:** TODO. **Dependências:** QC-001.  
**Requisitos:** QC-R01, QC-R02, QC-R03, QC-R04, QC-R05, QC-R06, QC-R11, QC-R13, QC-R15.  
**Áreas:** DTOs de intenção; parser e topologia.

1. Escrever tabela de casos dos capítulos 3–4 e tipar intenção/resultado de resolução.
2. Decidir como compor opções de serviço sem sobras indevidas; preservar Python 3.11.
3. Documentar no ADR o tratamento de root conflitante e a exceção de --plan.
4. Fixar a distinção entre sugestão Git, seleção de workspace e raiz autorizada; definir colisões TTY/JSON e a exceção de leitura Git em --plan (não executar subprocessos).

**Aceite:** Um mesmo argv tem uma interpretação; erros de sintaxe não iniciam serviço.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16, QC-T-C01, QC-T-C02, QC-T-C03, QC-T-C04, QC-T-C05, QC-T-C06, QC-T-C07, QC-T-C08, QC-T-C09, QC-T-C10, QC-T-C11, QC-T-C12, QC-T-C13, QC-T-C14, QC-T-C15, QC-T-C16, QC-T-C17, QC-T-C18, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10.

### QC-003 — Modelar namespace público e preparar fixtures

**Estado:** TODO. **Dependências:** QC-001.  
**Requisitos:** QC-R08, QC-R09, QC-R12, QC-R19.  
**Áreas:** schema de bindings/alias; fixtures SQLite e catálogos.

1. Conferir o namespace de alias interno e fixar o metadado público separado.
2. Desenhar transação para workspace existente e draft novo, com idempotência e revalidação.
3. Criar fixtures de dois Servers, workspaces homônimos, múltiplos hosts, legado e setup incerto.

**Aceite:** ADR de ID público com schema/recuperação; fixtures não confundidas com qualificação real.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18, QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

## QC-01 — Gramática, aliases, escolha de harness e vocabulário público

**Gate:** G1: parser e seletores corretos, sem efeitos indevidos.

### QC-004 — Implementar normalização de posicionais e flags

**Estado:** TODO. **Dependências:** QC-002.  
**Requisitos:** QC-R01, QC-R15.  
**Áreas:** main.py; connect.py; quick_connect_args.py proposto.

1. Extrair parse puro e tratar posicionais antes de opções de serviço.
2. Adicionar --id e regras de concordância sem remover --client/--project/--profile.
3. Desabilitar abreviação; recusar excesso, unknown flag e combinações fora do escopo.

**Aceite:** Tabela de gramática automatizada; entradas legadas mantêm semântica.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16.

### QC-005 — Implementar aliases raiz e ajuda inicial

**Estado:** TODO. **Dependências:** QC-004.  
**Requisitos:** QC-R02.  
**Áreas:** main.py; help.

1. Adicionar allowlist codex/claude/pi direcionando à mesma normalização.
2. Preservar precedência dos comandos de produto e help sem efeitos.
3. Trocar erro genérico de comando desconhecido por diagnóstico correto; não abrir picker para service digitado errado.

**Aceite:** Alias equivale ao connect correspondente; nunca chama shell/subprocesso para redespachar.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16.

### QC-006 — Unificar registro e picker de harness

**Estado:** TODO. **Dependências:** QC-004.  
**Requisitos:** QC-R07.  
**Áreas:** project_preset.py CLIENTS; connection_picker.py; runtime-options.

1. Reusar registro declarativo; normalizar case e aliases conhecidos.
2. Validar token depois do parse; em TTY recuperar unknown/not-detected com lista.
3. Distinguir inventário stale, múltiplas instalações e restrição de política; preservar candidate_ref.

**Aceite:** Erro de enum não mata o fluxo interativo nem executa caminho fornecido pelo usuário.

**Cenários relacionados:** QC-T-B01, QC-T-B02, QC-T-B03, QC-T-B04, QC-T-B05, QC-T-B06, QC-T-B07, QC-T-B08, QC-T-B09, QC-T-B10.

### QC-007 — Fixar comportamento não interativo

**Estado:** TODO. **Dependências:** QC-004, QC-006.  
**Requisitos:** QC-R15.  
**Áreas:** connect.py; output; argument validation.

1. Garantir que JSON e stdin não TTY não chamem input/chat.
2. Serializar alternativas/reason/catalog_complete e preservar efeitos reais.
3. Conservar perfil estável em adição automatizada; --id não substitui a intenção.

**Aceite:** Processo não bloqueia em automação e stdout JSON permanece parseável.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16, QC-T-B01, QC-T-B02, QC-T-B03, QC-T-B04, QC-T-B05, QC-T-B06, QC-T-B07, QC-T-B08, QC-T-B09, QC-T-B10, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10.

### QC-008 — Adotar ID do Harness como vocabulário público

**Estado:** TODO. **Dependências:** QC-004.  
**Requisitos:** QC-R10, QC-R14.  
**Áreas:** help/pickers/output; DTOs JSON; rótulos frontend de conexão.

1. Padronizar textos básicos como ID do Harness em português ou Harness ID no frontend inglês atual; não iniciar uma tradução global.
2. Manter connect_id em contratos/armazenamento, --id na CLI e --profile como opção técnica avançada. Não criar outra identidade chamada harness_id.
3. Remover Perfil: Assistente de projeto e nomes de arquivo dos resumos básicos; quando a função do agente for relevante, rotular Função do agente, separadamente.
4. Atualizar templates de confirmação, sucesso, conflito, reconnect e golden outputs; UI usa o mesmo nome público e referências canônicas.

**Aceite:** Usuário vê o identificador escolhido/gerado e não precisa inventar um perfil; campos técnicos legados continuam disponíveis sem quebra de JSON.

**Cenários relacionados:** QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24.

## QC-02 — CWD, sugestão Git/fallback e seleção do projeto

**Gate:** G2: nome útil sem associação ou expansão de raiz implícitas.

### QC-009 — Resolver CWD e raiz explícita com proveniência

**Estado:** TODO. **Dependências:** QC-002.  
**Requisitos:** QC-R03, QC-R06, QC-R17.  
**Áreas:** project_profile; terminal_target; directory_identity.

1. Capturar CWD uma vez; --project válido prevalece como diretório físico de descoberta e execução, mantendo invocation_cwd para diagnóstico.
2. Separar diretório físico, raiz Git, nome sugerido, workspace e ID do Harness; descoberta do nome nunca amplia raiz de execução.
3. Preservar canonicalização e provas de diretório; detectar symlink/junction alterado entre revisão e Finish sem lowercase global ou os.chdir.

**Aceite:** Destino físico é conhecido e uma troca exige decisão registrada.

**Cenários relacionados:** QC-T-C01, QC-T-C02, QC-T-C03, QC-T-C04, QC-T-C05, QC-T-C06, QC-T-C07, QC-T-C08, QC-T-C09, QC-T-C10, QC-T-C11, QC-T-C12, QC-T-C13, QC-T-C14, QC-T-C15, QC-T-C16, QC-T-C17, QC-T-C18.

### QC-010 — Descobrir metadados Git locais com limites e privacidade

**Estado:** TODO. **Dependências:** QC-002, QC-009.  
**Requisitos:** QC-R05, QC-R06, QC-R20.  
**Áreas:** adapter Git local proposto; runner de subprocessos existente; tests Git isolados.

1. Localizar Git de instalação confiável sem procurar executável no repositório; invocar allowlist rev-parse/config por argv sem shell, stdin fechado e orçamento total limitado.
2. Detectar working tree a partir da raiz física selecionada e origem local inequívoca; tratar .git como arquivo/worktrees/submodules com Git, não por concatenação de paths.
3. Retornar somente basename seguro, raiz descoberta, source/reason e estado. Nunca persistir/imprimir URL bruta, userinfo, query, fragmento ou stderr bruto.
4. Tratar Git ausente, timeout, safe.directory e configuração inválida como descoberta não confirmada com fallback, sem modificar config, autenticar ou fazer rede.
5. Em help/erro de gramática/--plan não executar Git. Na retomada/recovery priorizar seleção salva, sem recalcular nome.

**Aceite:** Fixtures comprovam consulta local limitada, sem rede/mutação e com raiz de execução inalterada; falha Git não vira ausência de catálogo Nexus.

**Cenários relacionados:** QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26.

### QC-011 — Estender consulta de projetos autorizados

**Estado:** TODO. **Dependências:** QC-009.  
**Requisitos:** QC-R04, QC-R05, QC-R17.  
**Áreas:** connection_project.py; workspaces API; ConnectionCatalog.

1. Mapear os serviços reais de workspace e conexões, incluindo projetos sem conexão.
2. Adicionar projeção paginada filtrada quando necessário; comprovar completude e revisão.
3. Resolver nome exato/ID e root com fontes canônicas; não expor roots remotos indiscriminadamente.
4. Nome derivado de Git só ordena/sugere opções; não usar URL, repo-name, branch, CWD ou labels homônimos como chave de workspace ou autorização.

**Aceite:** Nomes duplicados geram escolha; catálogo incompleto nunca autoriza criar duplicata.

**Cenários relacionados:** QC-T-C01, QC-T-C02, QC-T-C03, QC-T-C04, QC-T-C05, QC-T-C06, QC-T-C07, QC-T-C08, QC-T-C09, QC-T-C10, QC-T-C11, QC-T-C12, QC-T-C13, QC-T-C14, QC-T-C15, QC-T-C16, QC-T-C17, QC-T-C18.

### QC-012 — Aplicar precedência do nome e conservar a raiz aprovada

**Estado:** TODO. **Dependências:** QC-010, QC-011.  
**Requisitos:** QC-R05, QC-R06, QC-R13.  
**Áreas:** quick_connect_resolution proposto; connection_project.py; ResolvedProject/checkpoint.

1. Resolver seletores explícitos concordantes e associações Nexus antes de usar Git; origem Git não seleciona nem renomeia workspace por conta própria.
2. Aplicar origin local inequívoco → basename do working tree → basename da raiz física; respeitar --project e fornecer source/reason sem URL.
3. CWD em subpasta mantém subpasta por padrão. Raiz Git é opção explícita, nunca expansão de permissões; monorepos, clones e worktrees distintos não são mesclados.
4. Persistir nome escolhido e proveniência mínima na intenção, sem guardar segredo Git. Personalização invalida revisão; recuperação usa intenção congelada.
5. Em --plan usar seleção salva ou fallback de diretório rotulado não verificado; nunca alegar consulta Git que não ocorreu.

**Aceite:** Mesma entrada resolve deterministicamente a sugestão; resumo mostra nome e diretório independentes; escolhas explícitas e projetos existentes são preservados.

**Cenários relacionados:** QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26.

### QC-013 — Implementar seletor e proposta de projeto novo

**Estado:** TODO. **Dependências:** QC-011, QC-006, QC-012.  
**Requisitos:** QC-R03, QC-R04, QC-R05, QC-R06, QC-R13.  
**Áreas:** CLI picker; TerminalConnection.review.

1. Reutilizar associação exata e autorizada quando inequívoca. Caso contrário apresentar seleção/criação com nome sugerido e fonte produzidos por QC-012.
2. Manter CWD/--project como raiz padrão; oferecer raiz Git/raiz aprovada ancestral somente como alteração explícita, com impacto mostrado na revisão.
3. Permitir personalizar o nome e voltar à mesma revisão final; não criar diretório nem workspace ao navegar nas escolhas; não duplicar confirmações de setup.

**Aceite:** Criar projeto não cria diretório nem modifica mapeamento de outro projeto.

**Cenários relacionados:** QC-T-C01, QC-T-C02, QC-T-C03, QC-T-C04, QC-T-C05, QC-T-C06, QC-T-C07, QC-T-C08, QC-T-C09, QC-T-C10, QC-T-C11, QC-T-C12, QC-T-C13, QC-T-C14, QC-T-C15, QC-T-C16, QC-T-C17, QC-T-C18, QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26.

### QC-014 — Revalidar projetos em retomada e concorrência

**Estado:** TODO. **Dependências:** QC-013.  
**Requisitos:** QC-R04, QC-R05, QC-R06, QC-R12.  
**Áreas:** canonical_connections.py; selection/reservation; setup preconditions.

1. Incluir referência/revisão de resolução nos checkpoints novos.
2. Detectar mudança entre catálogo, seleção e Finish; não escolher projeto substituto.
3. Tratar drafts equivalentes de primeiro projeto sem criar workspaces duplicados silenciosamente.
4. Retomada recupera nome/ID já persistidos sem redescobrir Git para renomear. Mudança apenas de remote/branch não reconfigura conexão; mudança de raiz continua sujeita à validação canônica.

**Aceite:** Corridas de projeto falham/revisam com estado preservado e sem identidade canônica parcial.

**Cenários relacionados:** QC-T-C01, QC-T-C02, QC-T-C03, QC-T-C04, QC-T-C05, QC-T-C06, QC-T-C07, QC-T-C08, QC-T-C09, QC-T-C10, QC-T-C11, QC-T-C12, QC-T-C13, QC-T-C14, QC-T-C15, QC-T-C16, QC-T-C17, QC-T-C18, QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

## QC-03 — ID público, reserva, Finish, colisões e legado

**Gate:** G3: unicidade, decisões e recuperação comprovadas.

### QC-015 — Adicionar registro canônico de IDs públicos

**Estado:** TODO. **Dependências:** QC-003.  
**Requisitos:** QC-R08, QC-R09.  
**Áreas:** migration aditiva; serviço/porta/adapter public IDs.

1. Implementar validação compartilhada e uniqueness por Server/workspace.
2. Representar reserva e vínculo sem duplicar o runtime; não usar nomes como paths.
3. Adicionar revisão/consultas autorizadas e transações de alocação com rollback.

**Aceite:** Duas instâncias concorrentes não vinculam o mesmo ID ao mesmo workspace.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18.

### QC-016 — Reservar proposta e preservar intenção

**Estado:** TODO. **Dependências:** QC-015, QC-014.  
**Requisitos:** QC-R08, QC-R09, QC-R16.  
**Áreas:** connection_reservation.py; public ID reservation.

1. Reusar profile/intent/checkpoint, registrando pedido explícito ou proposta automática.
2. Reservar no Server após aprovação antes do teste quando namespace existir; drafts novos seguem capítulo 6.
3. Recuperar resposta perdida por mesma intenção; não renovar indevidamente nem reatribuir nome ocupado.

**Aceite:** Reexecução da mesma intenção recupera o mesmo nome; conflito precede teste quando detectável.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18, QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

### QC-017 — Integrar ID ao request, Finish e recibo

**Estado:** TODO. **Dependências:** QC-016.  
**Requisitos:** QC-R09, QC-R14, QC-R16.  
**Áreas:** terminal_connection.py; connection_setup.py; schemas HTTP.

1. Transportar membro versionado opcional no envelope de produto.
2. Incluir nome/namespace/revisão no hash; confirmar binding do ID junto ao Finish.
3. Preservar requests/recibos antigos sem campo; testar falha entre todas as gravações.

**Aceite:** Setup e vínculo público commitam juntos ou retornam recuperação parcial explícita; não há sucesso falso.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18, QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

### QC-018 — Resolver e associar conexões antigas

**Estado:** TODO. **Dependências:** QC-015, QC-017.  
**Requisitos:** QC-R11, QC-R12, QC-R19.  
**Áreas:** public ID resolve/associate; catalog; canonical association.

1. Resolver --id por namespace e revalidar a tupla completa.
2. Associar metadado a conexão antiga mediante ação autorizada, sem Finish produtivo.
3. Preservar ID desativado/retired; negar rename/rebind implícito.
4. Consultar recuperação pelo fingerprint da própria intenção antes de classificar ID bound como colisão; ID amigável sozinho não prova propriedade de uma intenção.

**Aceite:** Adotar nome não cria agente, grant, sessão ou teste e não altera alias interno legado.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18.

### QC-019 — Qualificar locks, reservas incertas e tombstones

**Estado:** TODO. **Dependências:** QC-017, QC-018.  
**Requisitos:** QC-R09, QC-R16.  
**Áreas:** SQLite concurrency; local file locks; cleanup rules.

1. Documentar ordem de locks e manter transações curtas.
2. Cobrir duas máquinas, duas intenções iguais/diferentes e perda de resposta.
3. Limpeza só quando ausência de efeitos é comprovada; IDs vinculados não são reciclados automaticamente.

**Aceite:** Resultados incertos não liberam um nome para abrir outro contexto por engano.

**Cenários relacionados:** QC-T-E01, QC-T-E02, QC-T-E03, QC-T-E04, QC-T-E05, QC-T-E06, QC-T-E07, QC-T-E08, QC-T-E09, QC-T-E10, QC-T-E11, QC-T-E12, QC-T-E13, QC-T-E14, QC-T-E15, QC-T-E16, QC-T-E17, QC-T-E18, QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

### QC-020 — Tratar colisão de ID com decisão explícita e sem sobrescrita

**Estado:** TODO. **Dependências:** QC-018, QC-006, QC-008.  
**Requisitos:** QC-R09, QC-R11, QC-R12.  
**Áreas:** connection_picker.py; public ID resolver; CLI structured errors.

1. Implementar matriz do capítulo 5: mesmo harness, harness diferente, ID pendente, ID revogado/retired, --new-connection e própria intenção recuperável.
2. Em TTY permitir retomar conexão real, escolher outro ID, solicitar sugestão ou cancelar conforme elegibilidade. Retomada incompatible com harness solicitado exige escolha explícita, nunca troca silenciosa.
3. Com --new-connection e ID de outra intenção, remover a alternativa retomar: outro ID/sugestão/cancelamento. Preservar a recuperação idempotente da própria criação.
4. Não TTY: retorno estruturado para colisão; sem sugestão aplicada, prompts ou novo ID automático. Retomada exata determinística sem --new-connection continua válida.
5. Revalidar tupla/estado/namespace depois da escolha e antes do efeito; não expor dados de conexão inacessível e não transformar erro de catálogo em ID livre.

**Aceite:** Nenhuma escolha sobrescreve, reativa ou amplia a conexão ocupante; a seleção produz a intenção correta ou cancela, inclusive sob corrida.

**Cenários relacionados:** QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24.

## QC-04 — Revisão final, fluxo completo e resultado positivo

**Gate:** G4: primeiro e segundo harness sem nome técnico de perfil nem confirmação redundante.

### QC-021 — Consolidar a revisão final e congelar escolhas aprovadas

**Estado:** TODO. **Dependências:** QC-019, QC-012, QC-008, QC-020.  
**Requisitos:** QC-R05, QC-R06, QC-R10, QC-R11, QC-R13.  
**Áreas:** TerminalConnection.review; quick_connect output; review fingerprint; retomada sem efeito.

1. Montar um resumo com harness efetivo, projeto/nome+fonte, CWD/raiz efetiva quando distintos, ID do Harness, host e efeitos de teste/autorização/configuração.
2. Seleções intermediárias não autorizam setup. Confirmar/Personalizar/Cancelar fazem parte da mesma revisão final; não acrescentar confirmação de nome seguida de confirmação idêntica de setup.
3. Personalização de nome, ID, harness, host ou raiz recompõe hash/revisão e exige aprovação atual. Não reusar --approve antigo.
4. Retomada exata não reaplica teste/preset/grant; a escolha Retomar acompanhada do resumo pode ser a confirmação final. Não TTY exige decisões exatas por flags/receipt.
5. Persistir somente dados necessários, emitir ID bound no sucesso antes do chat e preservar relato honesto de lifecycle/metadados já solicitados após cancelamento ou colisão.

**Aceite:** Uma confirmação de setup para uma seleção nova e inequívoca; escolhas e efeitos legíveis, sem autorização oculta ou segunda transação de configuração.

**Cenários relacionados:** QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24.

### QC-022 — Orquestrar Quick Connect no fluxo existente

**Estado:** TODO. **Dependências:** QC-007, QC-014, QC-019, QC-021.  
**Requisitos:** QC-R01, QC-R05, QC-R08, QC-R10, QC-R11, QC-R12, QC-R13, QC-R16.  
**Áreas:** connect.py; TerminalConnection; pickers.

1. Encadear resolução e setup sem duplicar review/apply/observe.
2. Preservar caminho retomar/adicionar, prompts existentes e filtros de harness.
3. Manter recuperação de grants/testes/sessões separada da simples reconexão.
4. Usar picker explícito de colisão e revisão consolidada; selecionar outra conexão invalida escolhas incompatíveis sem reinterpretar flags exatas silenciosamente.

**Aceite:** Primeiro e segundo harness entram no mesmo projeto sem profile manual em TTY.

**Cenários relacionados:** QC-T-A01, QC-T-C01, QC-T-C02, QC-T-E04, QC-T-E11, QC-T-G06, QC-T-H01, QC-T-I09.

### QC-023 — Implementar resumo positivo com ID

**Estado:** TODO. **Dependências:** QC-022, QC-008.  
**Requisitos:** QC-R10, QC-R13, QC-R14.  
**Áreas:** quick_connect_output proposto; _display.

1. Imprimir ID do Harness, harness efetivamente selecionado, nome/origem do projeto, diretório aprovado e operação antes do prompt.
2. Não mostrar perfil técnico nem Project assistant como identificador. Reservar --profile para ajuda avançada, recuperação técnica e JSON; retorno básico usa --id.
3. Produzir resume_argv seguro; distinguir configurado de sessão ativa, nome proposto de bound, criação de reutilização e conflito de resultado incerto.

**Aceite:** Usuário sabe o ID definitivo sem sair do prompt; cancel/review não usam mensagem de sucesso.

**Cenários relacionados:** QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10.

### QC-024 — Versionar JSON e efeitos por estágio

**Estado:** TODO. **Dependências:** QC-023.  
**Requisitos:** QC-R10, QC-R11, QC-R14, QC-R15.  
**Áreas:** DTO outcome; JSON serialization.

1. Adicionar quick_connect.version/status sem quebrar campos legados.
2. Preservar proposed versus bound, partial/unknown e efeitos de lifecycle/metadados.
3. Validar invariantes e exemplos JSON com testes golden.
4. Conservar quick_connect.connect_id como chave de dados única; acrescentar provenance segura e código público de colisão documentado. Não introduzir harness_id com valor independente nem expor remote bruto.

**Aceite:** connected sempre contém ID bound; retorno legado sem envelope não é vendido como Quick Connect completo.

**Cenários relacionados:** QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10.

### QC-025 — Recuperar commit com falha de persistência local

**Estado:** TODO. **Dependências:** QC-024.  
**Requisitos:** QC-R09, QC-R12, QC-R14.  
**Áreas:** atomic_json; canonical receipt lookup; resume.

1. Injetar falha depois do Finish e antes do arquivo de perfil.
2. Retornar configured_shortcut_pending com referência recuperável e sem replay.
3. Reparar apenas o atalho em retomada, validando namespace e Server.

**Aceite:** Conexão canônica não se duplica porque o disco do cliente falhou.

**Cenários relacionados:** QC-T-G01, QC-T-G02, QC-T-G03, QC-T-G04, QC-T-G05, QC-T-G06, QC-T-G07, QC-T-G08, QC-T-G09, QC-T-G10, QC-T-G11, QC-T-G12, QC-T-G13, QC-T-G14, QC-T-G15.

## QC-05 — Compatibilidade de UI, legado e acesso remoto

**Gate:** G5: dados e autoridade preservados nas superfícies existentes.

### QC-026 — Projetar ID no catálogo e UI existente

**Estado:** TODO. **Dependências:** QC-018, QC-024, QC-008.  
**Requisitos:** QC-R10, QC-R11, QC-R18, QC-R19.  
**Áreas:** ConnectionCatalog; connection DTOs frontend; Home seletor.

1. Adicionar campo nullable e revisão de catálogo; GET não associa nomes.
2. Mostrar connect_id quando presente mantendo referências e fallbacks existentes.
3. Não adicionar menu e não alterar alvos MCP/handoff por nome.
4. Rótulos curtos ID do Harness/Harness ID, mesmo namespace e conflito do CLI; UI não renomeia agent_id, profile nem sessões por alterar a apresentação.

**Aceite:** CLI e Home identificam a mesma conexão; múltiplas sessões mantêm IDs próprios.

**Cenários relacionados:** QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-027 — Preservar remoto, participant e Server antigo

**Estado:** TODO. **Dependências:** QC-022, QC-026.  
**Requisitos:** QC-R05, QC-R06, QC-R15, QC-R17, QC-R19.  
**Áreas:** terminal_target; remote setup; participant legacy; capability detection.

1. Testar retomada remota com workspace explícito e root local não transferido.
2. Rejeitar nova gramática em participant com ajuda antes de efeitos; preservar comandos antigos.
3. Detectar Server sem public IDs; não criar namespace só no cache e afirmar sucesso.
4. Git do computador do operador não atribui nome ou raiz à execução remota por inferência. Manter metadados do host e o fluxo Connector atual.

**Aceite:** Sem fallback local indevido, chamada de Connector inventada ou efeito de autoridade por alias.

**Cenários relacionados:** QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-028 — Cobrir migração de perfis e recibos legados

**Estado:** TODO. **Dependências:** QC-025, QC-027.  
**Requisitos:** QC-R12, QC-R19.  
**Áreas:** legacy fixtures; setup receipts; profile parsing.

1. Abrir perfis pré-0.3.5 e 0.3.5 sem sobrescrever campos privados/desconhecidos.
2. Validar golden hashes e execução por --profile/--client/--project.
3. Reexecutar os testes existentes de seleção retomar/adicionar afetados pelo parser.

**Aceite:** Nenhuma quebra de script legado ou nova autorização na reconexão.

**Cenários relacionados:** QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

## QC-06 — Qualificação, documentação, pacote e entrega

**Gate:** G6: evidências, limitações e rollback registrados.

### QC-029 — Executar matriz integrada e adversarial

**Estado:** TODO. **Dependências:** QC-026, QC-027, QC-028.  
**Requisitos:** QC-R05, QC-R06, QC-R10, QC-R11, QC-R13, QC-R20.  
**Áreas:** unit/SQLite/HTTP/CLI tests.

1. Executar cenários com relógio controlado e barreiras de concorrência.
2. Repetir os testes afetados da interface, do onboarding e da aplicação; não usar somente busca de strings no código como prova.
3. Registrar saídas, SHAs, falhas e cenários não executados separadamente.
4. Executar os cenários de descoberta Git e de decisão sobre IDs ocupados, incluindo ausência de rede, proteção de segredos no origin, TTY/JSON e nenhum setup após cancelamento.

**Aceite:** Ledger associa evidência real a cada cenário sem promover fixture a harness real.

**Cenários relacionados:** QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26, QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24, QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-030 — Validar experiência no terminal e plataformas

**Estado:** TODO. **Dependências:** QC-029.  
**Requisitos:** QC-R03, QC-R07, QC-R14, QC-R20.  
**Áreas:** TTY/pseudoterminal tests; Windows/POSIX shell; packaged CLI.

1. Testar teclado/Enter/cancelamento, espaços/Unicode em paths, quoting e resize.
2. Verificar linhas JSON sem ANSI e mensagens de erro sem secrets.
3. Executar binário instalado do pacote; documentar cada OS efetivamente usado.
4. Testar locale/rótulos, fallback Git, prompts de conflito, stdin reservado e limites reais de subprocesso; não confundir teste de fixtures Git com teste Nexus/harness.

**Aceite:** Comandos documentados funcionam no ambiente declarado; suporte não testado fica explícito.

**Cenários relacionados:** QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10, QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-031 — Executar jornada real isolada consentida

**Estado:** TODO. **Dependências:** QC-030.  
**Requisitos:** QC-R05, QC-R10, QC-R11, QC-R12, QC-R13, QC-R14, QC-R20.  
**Áreas:** harness real já suportado; workspace descartável.

1. Com consentimento, conectar um harness sem ID e outro com ID explícito no mesmo projeto.
2. Confirmar IDs na UI, sair e retomar, sem recriar grants/testes.
3. Registrar custos/limpeza conforme práticas do repo; não executar usando credenciais pessoais sem autorização.
4. Na campanha consentida, usar clone com pasta diferente do nome Git; testar ID ocupado por outro harness e confirmar que nenhum binding existente foi modificado.

**Aceite:** Campanha real separada dos testes sintéticos; sem consentimento marcar NOT_RUN/BLOCKED, não PASS.

**Cenários relacionados:** QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-032 — Atualizar documentação e prompt operacional

**Estado:** TODO. **Dependências:** QC-029.  
**Requisitos:** QC-R01, QC-R03, QC-R05, QC-R06, QC-R10, QC-R11, QC-R13, QC-R14, QC-R15.  
**Áreas:** docs/terminal-connect.md; README/help; troubleshooting.

1. Documentar CWD versus nome lógico, --id versus agent/profile e aliases raiz.
2. Publicar exemplos testados interativos/JSON/legado, conflitos e estados parciais.
3. Explicar que criar projeto não cria diretório e que conectar não envia tarefa.
4. Documentar precedência Git/fallback, raiz independente, rótulo ID do Harness, menu de colisão, contrato JSON compatível e revisão final única.

**Aceite:** Exemplos não prometem gramática ou estado além dos testes; notas de migração disponíveis.

**Cenários relacionados:** QC-T-A01, QC-T-A02, QC-T-A03, QC-T-A04, QC-T-A05, QC-T-A06, QC-T-A07, QC-T-A08, QC-T-A09, QC-T-A10, QC-T-A11, QC-T-A12, QC-T-A13, QC-T-A14, QC-T-A15, QC-T-A16, QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26, QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24, QC-T-H01, QC-T-H02, QC-T-H03, QC-T-H04, QC-T-H05, QC-T-H06, QC-T-H07, QC-T-H08, QC-T-H09, QC-T-H10, QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

### QC-033 — Empacotar, revisar gates e definir rollback

**Estado:** TODO. **Dependências:** QC-030, QC-031, QC-032.  
**Requisitos:** QC-R16, QC-R19, QC-R20.  
**Áreas:** wheel/sdist/frontend; release report; rollback.

1. Conferir instalação limpa com dependências do checkout e metadados públicos na UI.
2. Demonstrar desabilitar nova entrada mantendo perfis/IDs/daemon e dados.
3. Relatar implementação, qualificação e bloqueios; não publicar release/deploy automaticamente.
4. O gate G6 exige todos os requisitos deste plano, incluindo Git, vocabulário, colisões e confirmação; registrar limitações reais e preservar o namespace público e os recibos ao reverter a apresentação.

**Aceite:** G6 decidido por evidências; não encerrar a feature se ID/concurrency/CWD estiverem apenas documentados.

**Cenários relacionados:** QC-T-D01, QC-T-D02, QC-T-D03, QC-T-D04, QC-T-D05, QC-T-D06, QC-T-D07, QC-T-D08, QC-T-D09, QC-T-D10, QC-T-D11, QC-T-D12, QC-T-D13, QC-T-D14, QC-T-D15, QC-T-D16, QC-T-D17, QC-T-D18, QC-T-D19, QC-T-D20, QC-T-D21, QC-T-D22, QC-T-D23, QC-T-D24, QC-T-D25, QC-T-D26, QC-T-F01, QC-T-F02, QC-T-F03, QC-T-F04, QC-T-F05, QC-T-F06, QC-T-F07, QC-T-F08, QC-T-F09, QC-T-F10, QC-T-F11, QC-T-F12, QC-T-F13, QC-T-F14, QC-T-F15, QC-T-F16, QC-T-F17, QC-T-F18, QC-T-F19, QC-T-F20, QC-T-F21, QC-T-F22, QC-T-F23, QC-T-F24, QC-T-I01, QC-T-I02, QC-T-I03, QC-T-I04, QC-T-I05, QC-T-I06, QC-T-I07, QC-T-I08, QC-T-I09, QC-T-I10.

# 13. Matriz completa de aceite

Todos os 147 cenários começam em `NOT_RUN`. Os testes desta matriz são requisitos da entrega, não resultados obtidos na elaboração do pacote. Cada `PASS` precisa de evidência recuperável. Usar barreiras e relógio controlado nas corridas; fixtures/CLI não equivalem a uma campanha com harness real.

## A. Gramática e aliases

### QC-T-A01 — Dois posicionais
**Dado:** argv connect codex app. **Quando:** normalizar. **Então:** harness codex e nome app; nenhum path derivado de app.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A02 — Apenas harness
**Dado:** argv connect codex. **Quando:** normalizar. **Então:** projeto fica não resolvido até CWD/catálogo.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A03 — Sem posicionais
**Dado:** argv connect. **Quando:** normalizar. **Então:** wizard autorizado, sem erro de argumentos.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A04 — Alias raiz
**Dado:** argv claude app --id reviewer. **Quando:** comparar ao connect equivalente. **Então:** mesma intenção normalizada, sem subprocesso.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A05 — Precedência de subcomando
**Dado:** argv service status. **Quando:** despachar. **Então:** service original, sem resolução de harness.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A06 — Comando raiz desconhecido
**Dado:** argv claud. **Quando:** despachar. **Então:** erro útil e sugestões, nenhum daemon/picker de connect.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A07 — Duplicação concordante
**Dado:** connect codex --client codex. **Quando:** normalizar. **Então:** uma única escolha codex.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A08 — Duplicação conflitante
**Dado:** connect codex --client claude. **Quando:** normalizar. **Então:** erro antes de lifecycle ou reserva.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A09 — Nome com espaços
**Dado:** argv já separado com Minha aplicação. **Quando:** normalizar. **Então:** label preservado como uma string.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A10 — Posicional em excesso
**Dado:** connect codex app extra. **Quando:** parse. **Então:** erro de gramática sem efeitos.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A11 — Flag desconhecido
**Dado:** connect codex --clinet pi. **Quando:** parse completo. **Então:** erro e nenhuma sobra encaminhada ao daemon.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A12 — Sem abreviação
**Dado:** connect codex --pro /tmp. **Quando:** parse. **Então:** não assumir --project nem --profile.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A13 — Help puro
**Dado:** connect --help e claude --help. **Quando:** executar help. **Então:** sem cofre/HTTP/FS de configuração/serviço.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A14 — Legado preservado
**Dado:** connect --client codex --project .. **Quando:** normalizar. **Então:** path e token mantêm semântica histórica.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A15 — Mistura ambígua
**Dado:** connect --client codex app. **Quando:** normalizar. **Então:** conflito documentado, não converter app em projeto por heurística.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

### QC-T-A16 — Participant incompatível
**Dado:** connect codex app --mode participant. **Quando:** normalizar. **Então:** erro específico sem entrar em setup managed ou alterar MCP.  
**Nível:** unidade + CLI. **Estado:** NOT_RUN.

## B. Harness e inventário

### QC-T-B01 — Enum inválido em TTY
**Dado:** connect codxe com inventário válido. **Quando:** escolher Codex na lista. **Então:** seguir somente após escolha explícita.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B02 — Enum inválido em JSON
**Dado:** connect codxe --json. **Quando:** executar. **Então:** selection_required/código e alternativas, sem input.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B03 — Enum ausente
**Dado:** vários harnesses detectados. **Quando:** connect em TTY. **Então:** lista útil com cancelar.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B04 — Instalação ausente
**Dado:** Claude suportado, nenhum candidato confirmado. **Quando:** selecionar Claude. **Então:** motivo/alternativa, nenhuma instalação automática.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B05 — Inventário stale
**Dado:** fonte não atual. **Quando:** listar. **Então:** não classificar como ausência ou selecionar outro.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B06 — Dois candidatos
**Dado:** duas instalações Codex. **Quando:** resolver harness. **Então:** escolha de candidate_ref; não usar primeira por ordem.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B07 — Permissão negada
**Dado:** candidato detectado mas can_configure false. **Quando:** selecionar. **Então:** bloqueio de política mantido.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B08 — Texto malicioso
**Dado:** token com separadores shell. **Quando:** resolver. **Então:** nunca executar o texto como comando.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B09 — Case normalizado
**Dado:** connect CoDeX. **Quando:** resolver. **Então:** codex pela regra pública, sem fuzzy silencioso.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

### QC-T-B10 — Listagem passiva
**Dado:** catálogo existente. **Quando:** abrir picker. **Então:** nenhum version probe ou turno pago antes de consentimento.  
**Nível:** unidade + integração CLI/HTTP. **Estado:** NOT_RUN.

## C. CWD e projeto

### QC-T-C01 — CWD já associado
**Dado:** um vínculo exato autorizado. **Quando:** connect codex sem nome. **Então:** workspace reutilizado sem lista redundante.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C02 — CWD novo
**Dado:** pasta existente sem associação e sem metadados Git utilizáveis. **Quando:** connect codex. **Então:** oferta de projetos/criar, basename só sugestão identificada; nenhuma criação antes da revisão.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C03 — Label explícito
**Dado:** label único e raiz correspondente. **Quando:** connect codex app. **Então:** workspace correto, label não vira pasta.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C04 — Label inexistente
**Dado:** projeto app ausente. **Quando:** connect codex app. **Então:** proposta de novo workspace, confirmação antes de Finish.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C05 — Label duplicado
**Dado:** dois projetos autorizados chamados app. **Quando:** resolver. **Então:** lista identificada; sem TTY erro estruturado.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C06 — ID exato
**Dado:** --workspace-id W e nome concordante. **Quando:** resolver. **Então:** W e nenhum substituto.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C07 — Nome/ID discordante
**Dado:** --workspace-id A e nome de B. **Quando:** resolver. **Então:** conflito; não renomear A.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C08 — Override físico
**Dado:** CWD /A, --project /B. **Quando:** resolver. **Então:** /B como raiz explícita e CWD original registrado.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C09 — Raiz diferente em TTY
**Dado:** nome B cuja raiz /B difere de CWD /A. **Quando:** selecionar B. **Então:** confirmação da mudança, sem os.chdir global.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C10 — Raiz explícita não substituída
**Dado:** --project /A e nome B mapeado /B. **Quando:** resolver. **Então:** conflito, não oferecer troca automática de --project.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C11 — Root diferente em script
**Dado:** sem TTY e mapa discordante. **Quando:** resolver. **Então:** PROJECT_DIRECTORY_MISMATCH, sem setup.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C12 — CWD inexistente
**Dado:** diretório foi removido. **Quando:** resolver. **Então:** diagnóstico, nenhum fallback para home.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C13 — Subdiretório
**Dado:** CWD /repo/sub, origem Git válida e apenas /repo registrado. **Quando:** resolver. **Então:** sugerir nome do repositório sem herdar raiz /repo; mudança exige escolha explícita e revisão final.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C14 — Link alterado
**Dado:** symlink/junction muda após revisão. **Quando:** testar/Finish. **Então:** revalidação detecta drift, sem aprovação antiga aproveitada.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C15 — Plataforma de paths
**Dado:** diferenças de case/separador. **Quando:** comparar evidência. **Então:** respeitar utilitários canônicos, sem lowercase global.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C16 — Catálogo incompleto
**Dado:** uma página falha ou cursor/revisão muda. **Quando:** resolver/criar. **Então:** recusa de seleção; não criar projeto substituto.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C17 — Sem mkdir
**Dado:** proposta de novo projeto no CWD. **Quando:** cancelar/aprovar. **Então:** nenhuma criação de pasta/git clone em ambos.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

### QC-T-C18 — Dois primeiros connects
**Dado:** mesma raiz e label em duas intenções. **Quando:** executar com barreiras. **Então:** workspace não duplicado silenciosamente; conflito reavaliado.  
**Nível:** unidade + SQLite/HTTP + CLI. **Estado:** NOT_RUN.

## D. Sugestão Git, fallback, raiz e privacidade

### QC-T-D01 — Nome do origin HTTPS
**Dado:** clone /repos/copia com origin https://host/org/projeto.git. **Quando:** descobrir nome. **Então:** sugerir projeto com source git_origin; raiz física continua /repos/copia.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D02 — Origin SSH formato SCP
**Dado:** origin git@host:org/projeto.git. **Quando:** descobrir. **Então:** sugerir projeto sem chamar SSH ou rede.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D03 — Origin ssh URL com porta
**Dado:** origin ssh://git@host:2222/org/projeto.git. **Quando:** parsear localmente. **Então:** sugerir projeto e não incorporar usuário/host/porta ao nome.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D04 — Origin local
**Dado:** origin file:///srv/git/projeto.git ou caminho local de repositório. **Quando:** extrair basename. **Então:** sugerir projeto sem abrir outro repositório nem resolver sua existência.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D05 — Sem origin
**Dado:** working tree /repos/projeto com origin ausente. **Quando:** descobrir. **Então:** usar basename do working tree com source git_worktree, não upstream ou branch.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D06 — Origins conflitantes
**Dado:** origin retorna dois valores distintos. **Quando:** descobrir. **Então:** não escolher primeiro/último; usar root basename já comprovado e motivo origin_ambiguous.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D07 — Outros remotes não substituem origin
**Dado:** origin ausente e remotes upstream/personal distintos. **Quando:** descobrir. **Então:** usar basename Git; não escolher remote arbitrário.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D08 — Git indisponível
**Dado:** binário Git não encontrado e diretório válido. **Quando:** conectar. **Então:** usar basename físico e motivo git_unavailable, sem instalar Git.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D09 — Diretório sem Git
**Dado:** CWD válido fora de repo. **Quando:** conectar. **Então:** fallback basename físico com source directory; fluxo continua sob confirmação.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D10 — Git lento ou inválido
**Dado:** timeout, saída excessiva ou configuração malformada. **Quando:** descobrir. **Então:** respeitar orçamento e fallback explícito; não travar prompt ou tratar catálogo Nexus como vazio.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D11 — Remote inválido e caracteres de controle
**Dado:** origin inválido ou basename com ANSI/invisíveis/percent-encoded separador. **Quando:** parsear e renderizar. **Então:** rejeitar candidato e usar fallback seguro; nenhum comando executado ou caractere de controle impresso.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D12 — Working tree ligado
**Dado:** checkout com .git como arquivo apontando a metadados compartilhados. **Quando:** descobrir. **Então:** usar working tree atual e origin permitido; não presumir .git/config como caminho direto.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D13 — Configuração específica de worktree
**Dado:** worktreeConfig com origin somente no config.worktree e configuração comum válida. **Quando:** consultar configuração local. **Então:** considerar escopo worktree comprovado; ambiguidades entre valores geram fallback, nenhuma escrita de configuração.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D14 — Submodule ou repo aninhado
**Dado:** CWD dentro de repo Git próprio contido em outro. **Quando:** descobrir. **Então:** usar repositório mais próximo que contém a raiz física; não promover para superproject.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D15 — Monorepo sem expansão
**Dado:** CWD /mono/apps/api e origin monorepo.git. **Quando:** preparar revisão. **Então:** nome pode ser monorepo; raiz de execução permanece /mono/apps/api até escolha explícita.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D16 — Clones/worktrees homônimos
**Dado:** duas raízes e mesmo nome derivado de origin. **Quando:** resolver projeto. **Então:** não mesclar workspace, binding ou ID do Harness por igualdade de nome/URL.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D17 — Nome explícito prevalece
**Dado:** nome posicional meu-servico e origin repo.git. **Quando:** resolver nome. **Então:** meu-servico preservado; seletores exatos incompatíveis geram conflito, não rename.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D18 — Associação existente prevalece
**Dado:** CWD mapeado a Projeto X e origin mudado para Y. **Quando:** retomar. **Então:** Projeto X e ID existentes preservados sem nova configuração ou teste.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D19 — Override físico de descoberta
**Dado:** CWD /A, --project /B e origins diferentes. **Quando:** resolver. **Então:** Git consulta /B, guarda invocation_cwd /A e não sugere o repo de A.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D20 — Dubious ownership
**Dado:** Git recusa por safe.directory. **Quando:** descobrir. **Então:** diagnóstico sem stderr bruto; não gravar safe.directory nem contornar segurança; fallback físico sob confirmação.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D21 — Ambiente Git redirecionado
**Dado:** GIT_DIR/GIT_WORK_TREE/GIT_CONFIG_COUNT apontam a outro repo. **Quando:** descobrir pelo CWD. **Então:** sanear override para esta consulta; não usar repositório ou config injetados como fonte da sugestão.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D22 — Executável falso no CWD
**Dado:** arquivo git/git.exe na pasta de projeto com PATH relativo inseguro. **Quando:** localizar Git. **Então:** não executar binário vindo da pasta do projeto; usar instalação confiável ou fallback explícito.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D23 — Help e plan sem subprocessos Git
**Dado:** --help ou --plan com/sem sugestão salva. **Quando:** executar. **Então:** nenhum Git/harness/provedor iniciado; plan sem proveniência confiável declara fallback não verificado.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D24 — Repositório bare ou raiz imprópria
**Dado:** sem working tree ou raiz física sem basename útil. **Quando:** sugerir. **Então:** não inventar working tree; fallback válido ou solicitar nome explícito, sem mudar o diretório.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D25 — Privacidade do origin
**Dado:** origin inclui usuário/token, query e fragmento. **Quando:** descobrir/revisar/persistir/JSON. **Então:** extrair somente componente seguro; URL, credenciais e stderr bruto ausentes dos arquivos, saída e telemetria.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

### QC-T-D26 — Recuperação depois de alteração Git
**Dado:** setup aprovado/pendente com nome congelado, origin ou branch alterados. **Quando:** recuperar mesma intenção. **Então:** não renomear projeto/ID nem invalidar pedido só por metadados Git; revalidar raiz e autorização reais.  
**Nível:** unidade + fixtures Git locais + CLI; sem provedor. **Estado:** NOT_RUN.

## E. ID do Harness e namespace

### QC-T-E01 — ID explícito novo
**Dado:** --id reviewer livre. **Quando:** adicionar. **Então:** reviewer vinculado ao binding correto.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E02 — ID automático inicial
**Dado:** sem ID e namespace livre. **Quando:** adicionar Codex. **Então:** codex persistido e retornado.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E03 — Segundo mesmo harness
**Dado:** codex existente, usuário escolhe adicionar. **Quando:** continuar. **Então:** codex-2 proposto e vinculado após revisão.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E04 — Repetição não adiciona
**Dado:** codex existente, sem --new-connection. **Quando:** repetir connect codex. **Então:** retomar/adicionar, sem geração automática de irmão.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E05 — Unicidade entre agentes
**Dado:** agente A já tem reviewer no projeto. **Quando:** agente B pede reviewer. **Então:** conflito público apesar do alias interno distinto.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E06 — Unicidade entre hosts
**Dado:** host A usa reviewer no projeto. **Quando:** host B pede reviewer. **Então:** constraint compartilhada impede segundo binding.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E07 — Namespace entre projetos
**Dado:** projeto A tem reviewer. **Quando:** criar reviewer em B. **Então:** permitido; resolução exige projeto correto.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E08 — Namespace entre Servers
**Dado:** Server A tem reviewer. **Quando:** criar reviewer em Server B. **Então:** permitido sem cruzar cache/topologia.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E09 — Case do ID
**Dado:** --id Reviewer e reviewer. **Quando:** normalizar/reservar. **Então:** mesma chave normalizada.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E10 — ID inválido
**Dado:** ID com path/ANSI/espaço invisível/tamanho excedido. **Quando:** validar. **Então:** erro; nunca nome de arquivo nem truncamento silencioso.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E11 — ID existente concordante
**Dado:** mesma tupla e harness. **Quando:** connect --id reviewer. **Então:** em TTY oferecer retomada e confirmá-la explicitamente; em script concordante retomar sem --new-connection; mesmos agent/binding/grants.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E12 — ID harness conflitante
**Dado:** reviewer é Claude e pedido é Codex. **Quando:** resolver. **Então:** menu distingue harness solicitado e existente, outro ID/sugestão/cancelamento; usar o existente exige escolha explícita; scripts retornam conflito.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E13 — ID aposentado
**Dado:** reviewer retired/desativado. **Quando:** nova adição com reviewer. **Então:** não reutilizar para binding diferente.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E14 — Adotar legado
**Dado:** binding sem ID. **Quando:** associar reviewer. **Então:** somente metadados; nenhum teste, agent create ou grant.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E15 — GET passivo
**Dado:** binding legado sem nome. **Quando:** listar catálogo/Home. **Então:** não atribuir ID por leitura.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E16 — Alias interno preservado
**Dado:** binding alias interno app. **Quando:** associar connect_id reviewer. **Então:** não reescrever configuração histórica.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E17 — Flags conflitantes
**Dado:** --profile A e --id de B. **Quando:** resolver. **Então:** conflito, nenhum seletor ganha silenciosamente.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

### QC-T-E18 — New com ID ocupado
**Dado:** --new-connection --id bound por outra intenção. **Quando:** resolver. **Então:** conflito, não retomar nem renomear automaticamente.  
**Nível:** unidade + SQLite/HTTP. **Estado:** NOT_RUN.

## F. Vocabulário, colisões e revisão final

### QC-T-F01 — Rótulo básico do identificador
**Dado:** primeiro connect com ID automático. **Quando:** revisar/concluir. **Então:** usar ID do Harness (ou Harness ID na interface inglesa), não Perfil/Project assistant como identificador.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F02 — ID explícito independente do perfil
**Dado:** --id reviewer e profile técnico opaco. **Quando:** mostrar confirmação e sucesso. **Então:** reviewer é o ID do Harness; profile interno não precisa ser escolhido nem aparece como nome público.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F03 — Mesmo harness existente em TTY
**Dado:** implementer é Codex, pedido connect codex --id implementer. **Quando:** abrir resolução. **Então:** retomar é opção principal com resumo; adicionar exige outro ID; nada muda antes da escolha.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F04 — Harness diferente e escolha do existente
**Dado:** implementer é Codex, pedido claude --id implementer sem outros seletores contraditórios. **Quando:** escolher explicitamente utilizar Codex. **Então:** revalidar e retomar Codex com resumo correto; não criar/trocar para Claude nem usar aprovação anterior.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F05 — Colisão com ID manual alternativo
**Dado:** implementer ocupado por Codex, pedido Claude. **Quando:** escolher reviewer livre. **Então:** preparar apenas nova conexão Claude/reviewer; conexão implementer intocada.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F06 — Sugestão em colisão
**Dado:** implementer ocupado, Claude solicitado e claude livre. **Quando:** escolher sugerir automaticamente. **Então:** propor claude baseado no harness solicitado, salvar proposta e só reservar após revisão; não trocar ID sem consentimento.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F07 — Cancelar colisão
**Dado:** ID ocupado, serviço possivelmente já iniciado. **Quando:** cancelar. **Então:** nenhum setup/teste/grant/rename; informar lifecycle/metadados reais sem afirmar efeito zero indevido.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F08 — Adição explícita proíbe retomada alternativa
**Dado:** --new-connection com ID bound por outra intenção. **Quando:** mostrar menu. **Então:** somente outro ID, sugestão e cancelar; não oferecer usar a existente como sucesso da adição.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F09 — Adição não interativa em conflito
**Dado:** --new-connection --id ocupado --profile estável --json. **Quando:** executar. **Então:** HARNESS_ID_ALREADY_EXISTS/contrato compatível, sem menu, novo nome aplicado ou teste.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F10 — Retomada determinística não interativa
**Dado:** --id existente e seletores concordantes sem --new-connection. **Quando:** executar --json. **Então:** revalidar referência exata e retornar reused; sem reaprovação produtiva, teste ou grant.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F11 — Harness conflitante em script
**Dado:** Claude solicitado e ID de Codex. **Quando:** executar sem TTY. **Então:** erro estruturado, nunca selecionar Codex ou atribuir claude-2 por conta própria.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F12 — Reserva de outra intenção
**Dado:** ID reservado por outra intenção com resultado pendente. **Quando:** resolver. **Então:** estado pending/occupied, sem tomada da reserva; opções permitidas não ocultam incerteza.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F13 — ID revogado/desativado/aposentado
**Dado:** registro público ainda ocupa nome, binding indisponível. **Quando:** resolver. **Então:** não reativar nem reciclar; diagnóstico e possibilidade de outra conexão com outro ID.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F14 — Retry próprio antes de colisão
**Dado:** Finish commitado sem resposta e --new-connection com perfil/intenção original. **Quando:** repetir. **Então:** recuperar mesmo recibo e ID, sem erro falso de colisão nem grant/teste adicional.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F15 — Mesmo perfil com conteúdo alterado
**Dado:** intenção recuperável e pedido muda harness/root/ID. **Quando:** repetir. **Então:** recusar fingerprint incompatível; não tratar como retry nem sobrescrever checkpoint.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F16 — Colisão não autoriza revelar dados
**Dado:** ID ocupado por conexão não visível ao solicitante. **Quando:** consultar. **Então:** retornar conflito genérico quando autorizado sem expor identidade, host, path ou credenciais alheios.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F17 — Corrida depois da sugestão
**Dado:** nome mostrado livre foi reservado por outra intenção antes do approve. **Quando:** reservar. **Então:** recusar antes do teste e exigir revisão nova; não aceitar próximo sufixo com hash anterior.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F18 — JSON com identificador único
**Dado:** output inclui resumo público e metadados. **Quando:** serializar. **Então:** usar quick_connect.connect_id; não publicar harness_id divergente; código/motivo de colisão documentados.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F19 — Uma confirmação final
**Dado:** nome Git e ID automático resolvidos sem ambiguidade. **Quando:** concluir onboarding interativo. **Então:** um resumo final de efeitos novos, sem confirmação separada de nome e outra idêntica de setup.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F20 — Revisão inclui fontes e raiz
**Dado:** nome veio de Git e CWD é subdiretório. **Quando:** mostrar revisão. **Então:** nome+origem, raiz efetiva, host, harness real, ID e efeitos presentes; nenhuma expansão implícita.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F21 — Personalização invalida aprovação
**Dado:** revisão A seguida de mudança manual de nome/ID/raiz/harness. **Quando:** aplicar hash de A. **Então:** recusa; revisão B precisa de confirmação nova e conexão antiga não muda.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F22 — Rótulos respeitam idioma existente
**Dado:** frontend atual em inglês e documentação/CLI localizada em português. **Quando:** inspecionar templates. **Então:** Harness ID/ID do Harness com mesma semântica; não fazer tradução global ou misturar nomes técnicos no fluxo básico.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F23 — Seletores exatos contraditórios
**Dado:** --profile/--agent/--binding-id fixam B e --id aponta A. **Quando:** resolver conflito. **Então:** não usar menu para ignorar flag exata; recusar ou exigir correção explícita do comando, sem sobrescrita.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

### QC-T-F24 — ID imutável após mudar Git
**Dado:** conexão salva com reviewer e projeto X, remote agora Y. **Quando:** retomar e abrir Home. **Então:** mesmo reviewer e X, mesmas sessões; identificação do harness não deriva do nome Git.  
**Nível:** unidade + CLI TTY/JSON + HTTP/SQLite quando houver efeitos. **Estado:** NOT_RUN.

## G. Recuperação e concorrência

### QC-T-G01 — Reserva antes do teste
**Dado:** workspace conhecido e aprovação válida. **Quando:** colisão ao reservar. **Então:** não iniciar teste pago.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G02 — Duas reservas automáticas
**Dado:** namespace livre e dois add confirmados. **Quando:** concorrer. **Então:** nomes únicos; alteração de proposta requer revisão.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G03 — Resposta de reserva perdida
**Dado:** intenção reservou mas cliente não recebeu. **Quando:** repetir mesma intenção. **Então:** mesma reserva/ID; não alocar outro.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G04 — Reserva não é sucesso
**Dado:** ID reservado sem Finish. **Quando:** imprimir resultado. **Então:** proposed/pending, nunca connected.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G05 — Rollback no Finish
**Dado:** erro após criar binding antes de recibo. **Quando:** abortar transação. **Então:** binding/grant/ID definitivos não ficam parcialmente commitados.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G06 — Resposta Finish perdida
**Dado:** commit completo, HTTP falhou. **Quando:** recuperar setup ID inclusive repetindo --new-connection e perfil original. **Então:** mesmo ID/binding, sem novo teste/grant; recuperação precede conflito por ID ocupado.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G07 — Disco local falha
**Dado:** Finish confirmado, atomic_json falha. **Quando:** retornar e retomar. **Então:** configured_shortcut_pending e reparo somente do atalho.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G08 — Cancelar revisão
**Dado:** revisão nova antes de aprovação. **Quando:** cancelar. **Então:** nenhum setup produtivo; lifecycle já feito descrito corretamente.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G09 — Ctrl+C após efeito
**Dado:** teste emitido. **Quando:** interromper terminal. **Então:** checkpoint preservado; não cancelar servidor/tarefa automaticamente.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G10 — Reserva incerta expira
**Dado:** resultado não determinado. **Quando:** rotina de limpeza. **Então:** não liberar nome para outra conexão só por TTL.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G11 — Hash de review
**Dado:** alterar connect_id após revisão. **Quando:** approve hash anterior. **Então:** recusa antes de efeito.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G12 — Locks sem deadlock
**Dado:** duas adições/perfis com catálogo comum. **Quando:** forçar interleavings. **Então:** ordem única e lock global curto, sem input dentro dele.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G13 — Reusar não renova
**Dado:** grant expirado e binding válido. **Quando:** reconectar. **Então:** ID reusado, grant continua expirado.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G14 — Serviço compartilhado
**Dado:** dois perfis mesmo Server. **Quando:** connect outro harness. **Então:** um daemon apropriado; nenhum daemon por ID.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

### QC-T-G15 — Novo workspace draft
**Dado:** proposta sem workspace_id. **Quando:** commit concorrente do projeto. **Então:** revalidar namespace final; nunca inventar ID público antes do Finish.  
**Nível:** integração transacional + fault injection. **Estado:** NOT_RUN.

## H. Resultado e automação

### QC-T-H01 — ID antes do chat
**Dado:** setup conectado com sucesso. **Quando:** abrir prompt. **Então:** resumo com rótulo ID do Harness e ID definitivo já emitido, sem perfil técnico no caminho básico.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H02 — Resultado criado/reusado
**Dado:** primeiro connect e reconexão. **Quando:** observar output. **Então:** operation correta e mesmo ID na retomada.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H03 — Estado de sessão honesto
**Dado:** configured sem sessão de trabalho. **Quando:** output. **Então:** not_checked/not_submitted, não execução pronta.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H04 — Invariante connected
**Dado:** outcomes variados. **Quando:** validar DTO. **Então:** connected exige ID bound e refs verificadas.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H05 — JSON limpo
**Dado:** --json com erro/seleção/sucesso. **Quando:** capturar stdout. **Então:** documento parseável, sem menu/ANSI/segredo.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H06 — Plan não reserva
**Dado:** --plan com Server pronto. **Quando:** revisar ID. **Então:** proposed_connect_id; sem reserva canônica nova nem teste.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H07 — Plan com Server parado
**Dado:** --plan. **Quando:** executar. **Então:** não subir daemon para satisfazer resolução.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H08 — Adição script sem profile
**Dado:** --new-connection --json --id x. **Quando:** executar. **Então:** selection_required, sem tentativa de inventar idempotency key.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H09 — Quoting de retorno
**Dado:** label/path com espaços/metacaracteres válidos. **Quando:** gerar resume_argv. **Então:** vetor seguro e render próprio por shell; nada executado.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

### QC-T-H10 — Exit 0 legado
**Dado:** plano válido ou cancelamento. **Quando:** inspecionar JSON. **Então:** não afirmar conectado somente pelo exit code.  
**Nível:** CLI + golden JSON. **Estado:** NOT_RUN.

## I. Compatibilidade e jornada integrada

### QC-T-I01 — CLI antiga
**Dado:** fixtures --client/--project/--profile. **Quando:** executar suites. **Então:** fluxos legados e hashes preservados.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I02 — Server antigo
**Dado:** capability de public IDs ausente. **Quando:** novo connect --id. **Então:** erro explícito/upgrade, sem namespace local fictício.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I03 — Retomar remoto
**Dado:** binding remoto aprovado. **Quando:** selecionar por ID. **Então:** tupla exata; CWD local não muda root remoto.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I04 — Remoto indisponível
**Dado:** operator-profile remoto falha. **Quando:** connect. **Então:** não criar Server local substituto.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I05 — Participant legado
**Dado:** init/connect --mode participant legado. **Quando:** executar regressão. **Então:** config/credencial intactas e nenhum efeito managed.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I06 — UI sem novo menu
**Dado:** connect_id persistido. **Quando:** abrir Home/seletores. **Então:** mesmo ID do Harness/Harness ID e mesmas refs; connect_id permanece a única chave de dados desse identificador, múltiplas sessões distintas.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I07 — Privacidade de saída
**Dado:** dados maliciosos e secrets em campos não públicos. **Quando:** render CLI/JSON. **Então:** redação/escaping e nenhum material de segredo.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I08 — Regressão pacote
**Dado:** wheel/sdist gerados. **Quando:** instalar e --help/parse/connect isolado. **Então:** entrada instalada inclui feature e dependências corretas.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I09 — Jornada real consentida
**Dado:** sandbox e harnesses suportados. **Quando:** primeiro automático, segundo explícito, sair/retomar. **Então:** IDs estáveis, projeto comum, nenhum replay na reconexão.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

### QC-T-I10 — Rollback de apresentação
**Dado:** IDs e conexões já existem. **Quando:** desabilitar nova entrada. **Então:** daemon/perfis/bindings/dados continuam operantes.  
**Nível:** integração + instalação + campanha separada. **Estado:** NOT_RUN.

# 14. Validação, evidências e critério de pronto

## 14.1 Execução pelo Codex

Antes de escolher comandos de teste, ler o `pyproject.toml`, instruções do repositório, CI e suites reais do checkout. Reusar o mecanismo de dependências/vendoring já adotado pelo projeto. Não instalar uma versão publicada antiga no lugar da branch sem registrar essa diferença.

Executar unidade de parse/resolução e fixtures Git locais (repo sem origin, URLs SSH/HTTPS, worktreeConfig, submodule, paths, ausência/timeout, ambiente desviado, segredos) com rede bloqueada e sem escrita pelo produto. Criar fixtures durante os testes não autoriza o CLI de produção a criar repositórios. Executar também testes SQLite e HTTP das novas fronteiras; testes de CLI com stdin TTY/não TTY e stdout capturado; testes de concorrência e faults; regressão de setup/receipts; integração dos campos na UI; wheel/sdist instalados em ambiente isolado. A forma da UI não é revalidada somente com busca textual por nome de componente.

Uma campanha com provedor exige consentimento próprio, limite de gasto e projeto descartável. Sem credenciais/autorização, manter cenários reais como `NOT_RUN` ou `BLOCKED`, fornecendo comandos/procedimento e o bloqueio preciso. Não usar o fato de testes sintéticos passarem para declarar prontidão de todos os harnesses e sistemas operacionais.

Arquivos de evidência sugeridos em `plans/quick_connect/`:

```text
baseline.md
adr-parser-cwd-project.md
adr-git-name-hint.md
adr-harness-id-vocabulary-conflicts.md
adr-public-connect-id.md
source-map.md
execution-ledger.json
test-evidence/
compatibility-report.md
release-report.md
```

Iniciar o ledger deste pacote sem importar conclusões de outras frentes automaticamente. Manter intactos os registros existentes de Home, onboarding, Connector e daemon. Cada entrada verificada aponta commit, comando, código de saída, resultado relevante e ambiente. Não anexar banco privado, keys, prompts ou logs sensíveis. O ledger não substitui testes: cada `PASS` deve ser recuperável por evidência.

## 14.2 Jornada obrigatória final

Em um diretório de projeto existente, com Nexus e harnesses disponíveis:

1. `okto-nexus connect codex` resolve CWD, preserva associação existente ou propõe nome por Git/fallback, confirma o resumo final e devolve um **ID do Harness**. Git não altera a raiz de execução.
2. `okto-nexus connect claude --id reviewer` associa outro colaborador ao mesmo workspace, preservando o primeiro.
3. A Home mostra esses IDs junto aos contextos canônicos, sem novo menu ou outra lista de execução.
4. Sair do terminal e reconectar preserva IDs, identidade, modelo, permissões e sessão escolhida; não reaplica teste/grant por simples retomada.
5. `connect codxe` oferece recuperação interativa; `connect codxe --json` retorna seleção requerida sem bloquear.
6. Um projeto homônimo/raiz diferente exige decisão explícita; nenhuma pasta é criada ou trocada silenciosamente.
7. Perder a resposta de Finish e repetir a intenção retorna a mesma conexão e ID.
8. Adicionar o mesmo harness novamente, por intenção explícita, produz um nome distinto sem colidir entre hosts.
9. ID ocupado por outro harness permite decisão explícita em TTY; --new-connection oferece outro ID/cancelamento, não uma retomada alternativa. Scripts recebem conflito estruturado.
10. Um CWD em subdiretório recebe sugestão do repositório sem ampliação de root. Git indisponível/sem origin gera fallback comprovado e não interrompe a configuração de um diretório válido.
11. O fluxo básico usa ID do Harness/Harness ID; profile, agent_id e binding_id não são solicitados como substitutos desse campo.
12. Personalizar recompõe a revisão final; aprovar a revisão antiga é recusado. Conexões salvas não são renomeadas porque o Git mudou.

**Não aceitar** uma entrega que consulta Git pela rede, imprime URL com segredo, altera safe.directory, troca automaticamente CWD pela raiz Git, substitui ID ocupado, oferece profile como nome público, duplica confirmações sem novos efeitos ou usa Git para reidentificar um workspace. Também não aceitar uma entrega que só implementa `nargs='?'`; usa `--id` como sinônimo de profile ou agent_id; gera nomes apenas em memória; gera nomes em GET; trata o diretório atual como autoridade; quebra `--plan` ou scripts; ou transforma erro de enum em execução arbitrária.

## 14.3 Encerramento

O executor apresenta: delta implementado, testes executados e não executados, migrações, contratos públicos, compatibilidade, custos/campanhas, forma de rollback e pendências. Não fazer release/deploy/merge protegido sem autorização.

O gate de implementação requer toda a gramática, CWD, sugestão Git/fallback, namespace público, rótulos, matriz de colisão, revisão final, saída e recuperação funcionando em testes apropriados. O gate de qualificação real só passa com a campanha/ambiente efetivamente comprovados. Declarar separadamente as duas coisas.

# 15. Prompt de arranque

O texto abaixo também está em `PROMPT_CODEX_NEXUS_QUICK_CONNECT_R1.md`. Entregue este pacote ao Codex e use o prompt como instrução inicial.

<!-- INICIO DO PROMPT AUTOCONTIDO -->

### Instrução de entrada

Leia integralmente `PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md` e use `NEXUS_QUICK_CONNECT_LEDGER_R1.json` como registro inicial de execução. Este pacote é autocontido para a feature: contém todos os requisitos, contratos, tarefas e cenários. Não é preciso outro plano nem uma etapa de aplicação de emendas.

O snapshot de referência é `OktoLabsAI/okto-nexus`, `feature/v0.3.5`, SHA `2463c05833f533bc5a5676a5644774cff949ca28`. Ele não obriga retroceder o checkout e não comprova o HEAD atual. Registre branch, HEAD, status, instruções locais, diferenças e dependências antes de editar. Preserve o trabalho em andamento; não faça reset/clean/checkout destrutivo, force-push, deploy, release ou merge protegido.

Há 33 tarefas, 147 cenários, 20 requisitos e 7 etapas. Inicialize o acompanhamento deste plano com TODO/NOT_RUN. Não modifique registros de outras frentes. Reutilize código já existente após verificar os critérios aplicáveis; não crie uma segunda Home, outro daemon ou um setup paralelo.

### Contrato público

```sh
okto-nexus connect [harness] [project-name] [--id HARNESS_ID]
okto-nexus claude
```

Preserve flags e perfis legados. Aliases raiz usam allowlist e o mesmo fluxo; comandos do produto têm precedência. Token de harness desconhecido dentro de `connect` permite seleção guiada somente em TTY. JSON/não TTY nunca bloqueiam stdin nem escolhem candidatos implicitamente.

### Regras obrigatórias

**Nome do projeto:** escolhas explícitas concordantes → associação Nexus validada → origin Git local inequívoco → basename da raiz do working tree → basename da raiz física selecionada. `--project` continua path e prevalece como base física sobre CWD. Nome Git só sugere: não identifica workspace, não renomeia associação existente e não agrupa clones/worktrees. Git pode sugerir o nome a partir de uma subpasta, mas a raiz de execução continua CWD/`--project` até decisão explícita. Seletores exatos contraditórios geram conflito.

**Git local:** consultas permitidas de `rev-parse`/`config`, executável confiável, argv sem shell e limites de tempo/saída. Sem rede, hooks, instalação, autenticação ou escrita de configuração. Não presumir `.git` como pasta em worktrees/submodules. Origin ambíguo/inválido e Git ausente/timeout/safe.directory degradam a sugestão com motivo, não a segurança. Não armazenar/exibir URL completa, tokens, query, fragmento ou stderr bruto. Em `--plan` e help não iniciar Git; usar seleção salva ou fallback claramente não verificado. Recuperação da intenção aprovada não redescobre Git para renomear.

**Vocabulário:** o rótulo básico é **ID do Harness**; no frontend inglês, **Harness ID**. Profile é detalhe técnico, não campo exigido do iniciante. O papel Project assistant é função do agente, não identificador. Usar `connect_id` como chave técnica única; não criar um `harness_id` independente nem reaproveitar `agent_id`, `binding_id` ou `session_id`. IDs automáticos vêm de codex/claude/pi e sufixos, nunca do nome Git.

**Colisões:** unicidade no Server por workspace, inclusive entre hosts. Nunca sobrescrever harness, binding ou permissões do ocupante. Em TTY, ID existente compatível oferece Retomar explicitamente. Harness diferente identifica a conexão real e permite escolher usá-la (apenas com seletores compatíveis), escolher outro ID, pedir sugestão ou cancelar. `--new-connection` com ID de outra intenção não oferece retomada como substituto. Scripts conflitantes recebem erro estruturado; não aplicar sugestão automaticamente. Retomada exata não interativa, sem new, continua válida. Recuperar a própria intenção commitada precede colisão, inclusive com new; nome igual sozinho não prova a mesma intenção. Respeitar reservas incertas, revogados, tombstones e autorização de visibilidade.

**Confirmação:** um resumo final com projeto/fonte, raiz, harness efetivo, ID do Harness, host e efeitos canônicos. Confirmar/Personalizar/Cancelar fazem parte do mesmo fluxo. Selecionar opções não aprova teste; não duplicar confirmação de nome e setup. Personalização exige revisão/hash novo. Consentimento adicional continua necessário se os efeitos efetivamente mudarem. Retomada não renova grants nem repete teste.

**Persistência e resultado:** reutilizar reservas, checkpoints, Finish e recibos existentes. Distinguir ID proposto, reservado e bound; vínculo definitivo na transação correta. Sucesso exibe o ID antes do chat, e JSON só declara connected com ID bound e referência revalidada. Falha após commit retorna estado parcial recuperável; não criar outra identidade porque falhou o disco local. ID aparece na Home existente sem menu/lista nova nem roteamento MCP por alias implícito.

**Topologia:** preservar remoto, participant e daemon. CWD/Git do operador não definem a raiz do Connector; falha remota não cria Server local substituto; não há um daemon por ID. A gramática curta é do caminho gerenciado. Não misturar os novos posicionais com participant sem contrato. Não redesenhar Core ou Connector para facilitar o CLI.

### Execução e evidências

Comece por QC-00. Siga QC-01 a QC-06 e as dependências do backlog completo. Teste parser, Git local, TTY/JSON, aliases, diretórios, concorrência, HTTP, recuperação, compatibilidade e UI. Registre os comandos, ambiente e commit de cada prova. Não marque VERIFIED/PASS com base em presença de arquivo, busca de string ou relato não executado. A validação do pacote confere documentos e referências; não executa o Nexus.

Ao fechar cada etapa, informe arquivos alterados, contratos reutilizados, testes executados e não executados, migrações, efeitos, limitações, rollback e próximo passo. Campanha com provedor/dados reais exige consentimento, limite e ambiente isolado. Sem consentimento, implemente e teste as partes independentes, registre a campanha como NOT_RUN/BLOCKED e não alegue qualificação real.

A entrega só está completa quando o primeiro e o segundo harness podem ser conectados no mesmo projeto, recebem IDs persistentes, tratam colisões, aparecem na UI e são retomados sem duplicar identidades ou repetir efeitos. Não encerrar apenas com os novos argumentos do parser.

<!-- FIM DO PROMPT AUTOCONTIDO -->

# 16. Fontes fixadas e limites da análise

As fontes de código abaixo documentam o snapshot informado na seção 1. A consolidação deste pacote não realizou uma nova consulta ao HEAD nem executou o produto. As referências oficiais são apoio técnico registrado para parser, persistência e descoberta Git; o executor deve conferir a compatibilidade com as versões efetivamente utilizadas. Nenhum documento externo de planejamento é necessário para compreender os requisitos deste pacote. As evidências de implementação e qualificação devem vir do checkout e das campanhas executadas pelo Codex.

- **[S01] Versão e dependências:** `pyproject.toml`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/pyproject.toml
- **[S02] Entrada de comandos e help:** `src/okto_nexus/adapters/inbound/cli/main.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/main.py
- **[S03] Connect: parse, CWD, fluxo e saída:** `src/okto_nexus/adapters/inbound/cli/connect.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/connect.py
- **[S04] Picker de conexão/harness:** `src/okto_nexus/adapters/inbound/cli/connection_picker.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/connection_picker.py
- **[S05] Catálogo e associação canônica no CLI:** `src/okto_nexus/adapters/inbound/cli/canonical_connections.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/canonical_connections.py
- **[S06] Resolução atual de projetos por binding:** `src/okto_nexus/adapters/inbound/cli/connection_project.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/connection_project.py
- **[S07] Reservas de intenção locais:** `src/okto_nexus/adapters/inbound/cli/connection_reservation.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/inbound/cli/connection_reservation.py
- **[S08] Facade review/apply/observe:** `src/okto_nexus/application/terminal_connection.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/application/terminal_connection.py
- **[S09] Finish transacional e recibos:** `src/okto_nexus/application/connection_setup.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/application/connection_setup.py
- **[S10] Catálogo canônico Server:** `src/okto_nexus/application/connection_catalog.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/application/connection_catalog.py
- **[S10b] Projeção SQLite do catálogo:** `src/okto_nexus/adapters/outbound/sqlite/connection_catalog.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/adapters/outbound/sqlite/connection_catalog.py
- **[S11] Namespace real do alias de binding:** `src/okto_nexus/application/execution_binding_proposals.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/application/execution_binding_proposals.py
- **[S12] Guia de conexão da versão inspecionada:** `docs/terminal-connect.md`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/docs/terminal-connect.md
- **[S13] Provas de root e staging local:** `src/okto_nexus/application/execution_local_realizations.py`. Fonte: https://github.com/OktoLabsAI/okto-nexus/blob/2463c05833f533bc5a5676a5644774cff949ca28/src/okto_nexus/application/execution_local_realizations.py

- **[W01] Python 3.11, argparse:** https://docs.python.org/3.11/library/argparse.html — comportamento de posicionais, `parse_known_args` e abreviações; usar recursos compatíveis com o mínimo do Nexus.
- **[W02] SQLite, transações e conflitos:** https://www.sqlite.org/lang_transaction.html e https://www.sqlite.org/lang_conflict.html — suporte às decisões de transação curta, unicidade e tratamento de conflitos. Essas referências não são evidência de que os testes do Nexus foram executados.

- **[W03] Git — rev-parse:** https://git-scm.com/docs/git-rev-parse — identificação de working tree, diretório Git e ausência de working tree. Referência técnica; não comprova implementação do adaptador Nexus.
- **[W04] Git — config:** https://git-scm.com/docs/git-config — leituras por escopo, valores múltiplos, delimitador NUL e controle de includes. A allowlist, orçamento e política de privacidade aqui são requisitos propostos do Nexus.
- **[W05] Git — worktree:** https://git-scm.com/docs/git-worktree — configuração comum/específica e `.git` em checkouts ligados. Não criar a extensão nem alterar configurações para obter uma sugestão.

---
**Controle:** QCONNECT-R1 — edição inicial consolidada. Este documento é a especificação completa da feature. Campos e rotas novos são propostas; nenhuma alteração no repositório ou teste do Nexus foi realizado na preparação deste pacote. Toda mudança de requisito durante a implementação exige decisão registrada, não omissão silenciosa.
