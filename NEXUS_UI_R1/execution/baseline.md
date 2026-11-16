# UI-001 — baseline e ownership

Inspeção em 2026-11-16, antes de alterar produto. Dados reproduzíveis em
`baseline.json`; instrução de shell: `C:/Users/jpamb/.codex/RTK.md`.
Não foi encontrado AGENTS.md no repo nem nos ancestrais D:/, D:/Projetos/ e
D:/Projetos/Techridy/. A instrução AGENTS fornecida pelo usuário inclui RTK.
Foram lidos CONTRIBUTING e todos os workflows atuais de Nexus e Connector.

## Checkout e drift

Nexus começou em feature/v0.3.4, HEAD856c7f459d16719aa7dfa54c3dc64c85199cf563.
Somente o pacote fornecido NEXUS_UI_R1 estava untracked. Os três commits após
3d95aad8 são evidências/ledgers/teste de layout; `src`, `frontend`, pyproject e
lock não diferiam do snapshot de análise. Connector estava limpo no SHA de
análise a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b. Core estava limpo em sua
branch feature/v0.0.14. Nenhum checkout foi retrocedido.

`git fetch origin main` foi executado nos dois repos impactados. Nenhum commit
da main ficou ausente dos HEADs existentes; não foi necessário novo merge.
CONTRIBUTING Nexus sugere branch da main; a autorização explícita do usuário
para preservar Home prevalece: branch sucessora da feature atual, contendo main.
Connector exige PR para develop; promoção para main exige PR separada e owner.
Nenhuma proteção/configuração de GitHub foi alterada.

Branches de implementação: Nexus feature/v0.3.5 (versão0.3.5), Connector
feature/v0.0.13 (versão0.0.13). Core permanece0.0.14, exatamente fixado nos dois
produtos; não há necessidade identificada de novo protocolo. Bumps enviados
em9de55d95 e414e3e7 respectivamente. `uv lock --check --offline` PASS.
Nenhuma dependência foi atualizada, instalada globalmente ou publicada.

## Ownership e preservação

Root controla versões, baseline, ledger, checker e integração. Subagente
browser_evidence_review escreve somente source-map.md/navigation-tracking-contract.md;
interrupt_completion somente connection-session-contract.md; native_questions_browser
somente fixtures.py, fixture-contract.md e novos testes tests/ui_simplification/.
As três faixas são disjuntas. App/Home/CLI e repos Connector/Core não têm escritores
concorrentes nesta etapa. Não há como excluir editores humanos externos; qualquer
drift inesperado será inspecionado antes da integração, sem sobrescrever arquivos.

Preservar HomeOverviewService/queries, controller/hook, HomeTarget, inspeções,
MetaHarnessComposer, APIs Attention/setup/receipt, terminal somente leitura,
checkpoints/locks e semântica de work resume. Ledgers HOME-R1/R3 são históricos
independentes, sem migração de PASS automática. Permanecem gates anteriores de
leitor de tela, compreensão humana e continuidade real; fixtures não os resolvem.

## Entradas e qualificação

Os quatro hashes do MANIFESTO fornecido foram verificados antes de editar o
ledger. O plano é imutável. O ledger original está preservado byte a byte em
input-ledger.json; MANIFESTO.json descreve essa entrada original, não o ledger
mutável de execução. O baseline não lê configurações ou credenciais pessoais.

T-BASE-01: inspeção real preservou pacote local e HEAD posterior. T-BASE-02:
ownership explícito e escritores disjuntos estabelecidos antes de editar produto.
São provas de processo; nenhum cenário CLI/browser/provedor é inferido delas.

## Efeitos, reversão e próximo incremento

Até aqui: somente versões, documentação, fixtures e acompanhamento. Sem migration,
serviço iniciado/parado, pedido ao provedor, alteração de grant ou instalação pessoal.
Rollback por revert dos commits novos, preservando a base feature/v0.3.4 e
feature/v0.0.12; não exige reset nem remoção de dados.
Próximo: contratos UI-002/003/004, fixtures UI-005, depois navegação/pendências
globais e seletor CLI obrigatório em faixas independentes.
