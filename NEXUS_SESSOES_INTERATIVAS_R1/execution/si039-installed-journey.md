# SI-039 installed Nexus, Connector and Core journey

A fresh Windows virtual environment installed Nexus 0.3.8 with `serve-lite`
and the pinned Connector 0.0.15 and Core 0.0.16 wheels from the offline cache.
Both consumers require the same Core version. The verifier compared all
1,145 hashed installed package files with the three wheel RECORDs, validated
the Core R4 manifest and passed the dependency and offline lock checks.
Product, frontend, pins and lock inputs match the Nexus wheel build.
[Package digests, baseline and observations](si039-installed-journey.json)

The installed Connector daemon negotiated R4 over a real loopback WebSocket.
The production Nexus HTTP app served the JavaScript and CSS byte for byte
from the installed wheel. The Pi 0.87.1 process used a deterministic extension
in an isolated profile with external network calls blocked.

1. One work request started a turn on the reviewed Pi connection. The
   installed `session list` command found the exact session by the confirmed
   binding and workspace.
2. An authenticated Edge browser opened the exact scoped conversation in
   operational Home. Active showed the collaborator, and the conversation
   showed one copy of the prompt.
3. The installed `session attach` command opened the read-only Pi transcript
   in Windows ConPTY. Ctrl+C returned the exact detach receipt and restored
   the console modes. The attachment was durably detached, and the original
   Pi process was still alive.
4. The fixture released the held response. The browser showed one copy in
   the same conversation and the CLI listed the same session again. The
   native history contained one user message, and the database held one open,
   one submitted turn and one result. A canonical close retired the session
   and the native process exited.

The final browser/CLI journey and 61 installed regressions passed. A separate
live HTTP/MCP smoke passed with two authenticated agents, 54 tools and a
confirmed canonical Server stop. Earlier attempts corrected a URL comparison,
a terminal-read readiness race and a cleanup check that still expected a
synthetic process. One earlier test runner was stopped after its native
session had already closed canonically. The final run completed its normal
cleanup.

This covers integration and installed-package verification for SI-T-I05 on
Windows loopback. It used a fixture operator vault, approved candidate
selection and synthetic model responses. Real-provider campaigns,
cross-machine verification and human acceptance retain their existing gates.
The increment changes evidence and the ledger. Reverting the commit removes
those records without a runtime or database rollback.

## Reconstrução da distribuição no Windows

O Nexus `949ca8a9` gerou a distribuição de código-fonte e, a partir dela, o wheel 0.3.8. Os 815 arquivos rastreados do pacote ficaram idênticos no checkout, no arquivo-fonte e no wheel reconstruído, incluindo os sete arquivos da Home e as 190 migrações. Os metadados e os pontos de entrada do CLI também conferiram. O Connector 0.0.15 e o Core 0.0.16 instalados vieram dos pins do manifesto da CI. Seus arquivos correspondem aos respectivos checkouts após normalizar as terminações de linha.

O wheel do ensaio anterior continha 42 arquivos que só existiam em `build/lib`, incluindo 40 bundles antigos e dois módulos retirados. Nenhum fazia parte do pacote no checkout atual. O wheel reconstruído tem os mesmos bytes nos 815 arquivos em uso. Para repetir o build de validação, use `uv build --offline --out-dir <diretório-novo>`, que monta o wheel a partir da distribuição de código-fonte. [Auditoria do wheel anterior](si038-codex-campaign-preflight.md#revalidação-do-wheel-atual-no-windows)

O `twine check --strict` passou para os dois artefatos e a instalação offline conferiu as dependências. A instalação base com Core carregou o Nexus. A variante `serve-lite` respondeu à rota de protocolo e serviu o HTML, o JavaScript e o CSS da Home com os mesmos bytes do wheel. Os dois testes de instalação rodaram sem o Connector opcional. O smoke HTTP/MCP usou dois agentes autenticados do ambiente descartável, observou 54 ferramentas e confirmou a saída do servidor após a parada canônica. [Comandos, hashes e resultados](si039-installed-journey.json)

A regressão executada pelo verificador da CI fora do checkout aprovou 407 casos, incluindo CLI, fila, anexação, retomada, recibos e Quick Connect. O único caso pulado exige um pseudoterminal POSIX. [Relatório estruturado](si039-installed-journey.json)

O marco atualiza o artefato local e as evidências de instalação. Dispensa migração. A reversão do registro usa o commit. O gate de campanha de SI-T-I05 segue pendente.

## Auditoria do candidato Windows em `f2bbb856`

A distribuição de código-fonte e o wheel do dashboard atual contêm os mesmos 817 arquivos rastreados do pacote, incluindo 190 migrações e sete arquivos da Home. O conteúdo das duas distribuições é idêntico entre si. A comparação com o Git registrou 15 arquivos idênticos e 802 com diferença apenas na terminação de linha. O HTML aponta para o único bundle JavaScript empacotado. [Hashes e comparação](si039-installed-journey.json)

O Connector 0.0.15 e o Core 0.0.16 fixados na CI correspondem aos checkouts `2b0000a1` e `94aeb596`. A instalação isolada em Python 3.13 validou o conteúdo dos três wheels carregados de `site-packages` e passou nas verificações offline de lock e dependências. A instalação base inicializou com o Core e com o Connector opcional ausente. Com `serve-lite`, a rota de protocolo e a Home retornaram HTTP 200, e os bytes servidos do JavaScript e do CSS corresponderam aos arquivos do wheel.

O smoke HTTP/MCP em loopback confirmou 54 ferramentas, entrega de mensagem, conclusão de handoff, leitura do artefato criado, geração de `shared.md` e a saída do processo após a parada canônica. O ensaio usou identidades descartáveis. A suíte instalada ampliada roda em separado e terá seu resultado registrado após concluir. Este commit atualiza as evidências e dispensa migração. [Resultados e comandos](si039-installed-journey.json)

## Regressão instalada de 811 casos e inicialização do teste SSE

A suíte ampliada terminou com 809 aprovados, um ignorado por exigir um pseudoterminal POSIX e uma falha. O verificador confirmou que os arquivos de entrada conservaram seus hashes. A falha ocorreu enquanto o pai esperava a primeira confirmação do servidor descartável, antes do snapshot e da abertura do stream. A repetição isolada com o wheel atual reproduziu a mesma falha. O SQLite da primeira tentativa chegou a migrar o esquema, sem commits de atividades da fixture.

O teste agora reserva 90 segundos para o carregamento inicial do servidor descartável. Cada comando seguinte conserva o limite de 20 segundos, e os limites de espera do cliente Node continuam em oito segundos. Os seis testes focados passaram com o wheel atual. A prova de SSE conferiu commit antes da assinatura, commit durante a desconexão e atualização após lacuna de retenção. O cliente e o servidor descartáveis encerraram com código zero. [JUnit, fases do stream e hashes dos wheels](si039-installed-journey.json)

O marco altera o teste e as evidências, sem migração. Reverter o commit restaura a espera anterior da fixture.
