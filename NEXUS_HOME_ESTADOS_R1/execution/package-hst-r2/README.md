# Pacote HST 0.3.7 — preparado, não executado

Os drivers derivam de QC36 e não reutilizam qualquer allocation, prefixo, relatório ou candidato anterior. `package.py` bloqueia **todas** as ações, inclusive `prepare`, enquanto não existir `SOURCE_ASSET_READY.json` emitido a partir do anúncio final do Root. Ainda não há allocation nem READY de pacote.

Formato do gate futuro:

```json
{"source_asset_ready":true,"version":"0.3.7","source_commit":"<COMMIT_FINAL>","assets":{"index.html":"<SHA256>","assets/<BUNDLE_REAL>.js":"<SHA256>","assets/<CSS_REAL>.css":"<SHA256>"}}
```

O commit e cada pin serão conferidos antes de agir. Os nomes reais dos bundles serão lidos do `index.html`, sem depender dos nomes 0.3.6. Não há rebuild Vite neste driver: reutiliza somente o build final autorizado pelo Root, comparando todos os bytes Nexus entre checkout, cópia isolada, wheel, sdist e instalação. A contagem do payload Nexus é calculada; não se presume 1028 arquivos.

Sequência após o gate, todos os comandos com prefixo RTK:

```powershell
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py prepare
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py build
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py install
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py smoke
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py twine
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/package.py audit
rtk proxy python -B NEXUS_HOME_ESTADOS_R1/execution/package-hst/curate.py
```

`prepare` cria novo Temp `nexus-hst-r1-package-*` com venv do Python 3.13.1 (`C:/Python313/python.exe`). `install` usa o runner canônico `tools/ci_installed.py`, lido integralmente: primeiro Nexus+Core sem Connector/Torch, depois serve-lite/dev sem Connector/Torch, e apenas depois Connector de teste. Os pins permanecem Core `ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5` e Connector `4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90`.

Twine verifica exatamente quatro artefatos: Nexus wheel e sdist novos, Core wheel e Connector wheel existentes e não reconstruídos. O sdist contém a cópia `src` e metadados de empacotamento; não se afirma inclusão integral de docs/tests/plans. O helper de build existente foi lido, mas seu rebuild Vite independente não é usado para substituir os assets congelados.

A auditoria roda `-I` fora do checkout, verifica origens dos três módulos no novo prefixo, bytes de todos os seus payloads e ajuda das entrypoints/aliases sem iniciar harness, além da recusa JSON de flag inválida. Não há pytest neste lote. `curate.py` exige sucesso dos passos, ausência de drift de fontes e emite READY com wheel SHA, Python e prefixo congelado antes da delegação de testes/browser.

Após READY poderá ser ligado o smoke HTTP/MCP já preparado em `../installed-live-mcp/`, usando somente esse novo Python, `-I -B`, ambiente pai sanitizado, CWD próprio e prazo externo. Serão registrados stop canônico e saída física; nenhum provider/modelo/conta pessoal será usado. Esse smoke ainda não foi executado.
