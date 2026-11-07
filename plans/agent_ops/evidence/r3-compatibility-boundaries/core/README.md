# RG-06 — complemento de importação e credenciais

Requisito literal, plano fixo linha 973: “Core importado sem sockets/processos/credenciais; dependências entre aplicações continuam proibidas.”

**Recomendação:** RG-06 pode ser considerado VERIFIED para as revisões atuais no escopo Windows/local instalado, combinando a verificação estática atual das fronteiras com a auditoria complementar abaixo. Não encontrei lacuna literal concreta restante. Não alterei o checkout, ledger ou status; a decisão de registro cabe ao root.

A evidência `5545dbde` importou os 131 módulos e impôs guards de socket/processo/thread/arquivo, mas declarou corretamente duas limitações: não instrumentou acesso ao ambiente nem APIs nativas de credenciais, e reteve apenas resumo manual do stdout. Ela sozinha não provava o componente “credenciais”.

## Execução complementar observada

`run.py` cria um subprocesso `python -I -B` do venv CI existente, com ambiente construído do zero, HOME/USERPROFILE/APPDATA/TEMP sintéticos, stdin DEVNULL e stdout/stderr em pipes. Nenhum ambiente de usuário é herdado. O único canário tem valor explicitamente fictício e nunca é resolvido por uma API real de credenciais. Não há criação/leitura/remoção de entrada no cofre, provider, daemon ou serviço pessoal.

`audit.py` verifica o wheel Core `5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb`: **165 arquivos** iguais à fonte e instalação, **131 arquivos Python** aceitos pelo verificador existente de dependências do Core. Depois importa todos os **131 módulos** sob os guards ativos. Nenhum módulo de Nexus ou Connector é carregado.

O relatório bruto real é `stdout.json`, retido byte a byte pelo launcher e vinculado pelo SHA em `invocation.json`. Resultado: **PASS**, zero eventos proibidos, zero lookup de ambiente originado no Core, zero acesso às APIs de credenciais instrumentadas. Há **255 lookups de dependências**, registrados com nome e caller, sem valores: oito pares relativos a timezone, diretório de configuração/base Python, desabilitação de plugins Pydantic e locale. Não são contados como ausência de todo acesso ao ambiente.

Os guards cobrem `os.getenv`, `os.environ` e `nt.environ` pelo mesmo mapping, inclusive enumeração; todos os 18 entry points callable `win32cred.Cred*` exportados nesta instalação; `win32crypt.CryptUnprotectData`; carregamento/resolução dinâmica de símbolos ctypes; e os guards prévios de socket/processo/thread/arquivo. Nove controles negativos exercitam caminhos representativos e todos são bloqueados antes da operação real. A revisão estática adicional localiza todos os usos atuais de `os.environ` do Core dentro de funções/métodos de runtime, sem executá-los.

Os mesmos guards ficam ativos durante os 131 imports. Isso é cobertura completa da lista de módulos importados e das superfícies instrumentadas, não instrumentação universal de qualquer extensão C/syscall. A distinção não cria um requisito extra de tracer universal: as APIs concretas usadas pelo código atual, suas fronteiras estáticas e os acessos observados foram conferidos.

## Recusas preservadas e exceção de console

`initial/` preserva a primeira recusa; `diagnostic/` preserva a segunda com frames e símbolo. Ambas pararam em `GetStdHandle`, vinculado por `click._winconsole` durante import de MCP → httpx → Click. A recusa era excessiva para este requisito, não um acesso a credenciais nem bug de produto.

A execução final permite somente a lista explícita revisada de símbolos console/buffer quando o caller é `click._winconsole`. Foram observados nove eventos: oito símbolos e `shell32`. `GetStdHandle` consulta handles padrão; stdin está fechado para entrada interativa. As APIs de credenciais continuam bloqueadas. As primeiras saídas não foram sobrescritas; não houve nova rodada após o PASS final.

## Fronteiras entre aplicações e limites

`application-boundaries.json` refaz a verificação literal AST das fontes atuais Nexus/Connector. Nenhuma aplicação importa a outra. As quatro chamadas dinâmicas existentes foram revisadas: iterador de tools Nexus, dois imports de famílias fixas attention dentro de Nexus, e auto-import Connector para versão. Todos permanecem no namespace da própria aplicação. O verificador Core existente também recusa imports externos não declarados, aplicações irmãs e cargas dinâmicas fora do registro permitido.

`report.json` contém a recomendação, revisions/hashes, contagens derivadas do stdout e limites. `manifest.json` é a allowlist pública: scripts, stdout/stderr reais, invocações, revisão estática e relatórios; nenhum banco, home, credential dump ou arquivo pessoal. As saídas referem-se apenas ao import instalado Windows das versões atuais; não qualificam runtime de provider, credenciais em uso, M1/M2, outros sistemas ou versões futuras.
