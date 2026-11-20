# Modos de conexão no CLI instalado

O executável `okto-nexus.exe` do wheel 0.3.8 rodou em Windows ConPTY contra o app HTTP e o SQLite instalados. O serviço manteve a mesma geração durante toda a rodada. A fixture forneceu o inventário, a leitura de versão e o retorno do teste de conexão. Usou perfis e projetos descartáveis, sem executar um harness ou chamar provedores.

| Cenário | Observação |
| --- | --- |
| SI-T-F02 | `--no-interactive` configurou a conexão com a revisão já aprovada. O processo saiu sem entrada no terminal e sem consultar sessões. |
| SI-T-F03 | Com a revisão já aprovada e sem flag de apresentação, o CLI só perguntou se deveria abrir o harness após confirmar a configuração. Enter selecionou Não e retornou ao shell. |
| SI-T-F04 | `--json` sem flag de apresentação retornou `configured` e `not_requested` sem ler entrada. O `attach_argv` trouxe o ID público, o workspace exato e as opções da instância, em argumentos separados e sem segredos. |
| SI-T-F07 | `--plan -i` exibiu a intenção de abrir o visualizador e gravou apenas o checkpoint de revisão. A consulta ao serviço usou GET e não verificou a versão nem testou a conexão. |
| SI-T-F09 | `--no-chat`, com e sem JSON, respeitou o perfil legado escolhido. O checkpoint e o comando de anexação mantiveram o perfil, sem repetir o teste ou alterar o binding. |
| SI-T-F13 | Após criar o binding, `-i` consultou o catálogo e informou que não havia sessão viva. A configuração ficou confirmada e a leitura posterior do mesmo perfil recuperou o resultado sem repetir o teste. |

O SQLite confirmou quatro bindings e quatro recibos de configuração. A rodada inteira gerou zero sessões, operações de execução, anexações, entradas de sessão ou checkpoints de trabalho. Passaram também 108 regressões de argumentos, conexão pelo terminal e Quick Connect, com importações dos wheels verificadas. O listener de teste e os processos do ensaio foram encerrados. [Dados e hashes](si029-installed-connect-modes.json)

Na preparação, ampliei a largura do ConPTY para capturar cada saída JSON completa. A conferência do perfil legado usa o argumento `--profile` em `attach_argv` e o checkpoint persistido. O escopo desta rodada termina na decisão de apresentação e na recusa por ausência de sessão. A anexação bem-sucedida e a insuficiência de grants permanecem no ledger.

O marco registra evidência, sem alteração de comportamento, pacote ou esquema. O rollback consiste em reverter o commit de evidências.
