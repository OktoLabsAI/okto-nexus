# Quick Connect — pacote R1 consolidado para o Codex

## Entrada única

Entregue este pacote ao Codex e utilize `PROMPT_CODEX_NEXUS_QUICK_CONNECT_R1.md` como instrução inicial. A especificação completa é `PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md`; o acompanhamento inicial está em `NEXUS_QUICK_CONNECT_LEDGER_R1.json`.

Todos os requisitos estão integrados. Não há plano complementar a aplicar, histórico de emendas a interpretar ou documento de planejamento externo obrigatório. São **33 tarefas, 147 cenários, 20 requisitos e 7 etapas**.

## Conteúdo

| Arquivo | Uso |
|---|---|
| `PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md` | Contratos completos, comportamento, backlog, testes, rollout e prompt incorporado. |
| `NEXUS_QUICK_CONNECT_LEDGER_R1.json` | Requisitos, dependências e vínculo bidirecional tarefa/teste, inicialmente TODO/NOT_RUN. |
| `PROMPT_CODEX_NEXUS_QUICK_CONNECT_R1.md` | Instrução pronta para iniciar a execução. |
| `VALIDAR_PACOTE.py` | Validação local de consistência dos documentos e integridade dos arquivos. |
| `VALIDACAO_PACOTE_R1.json` | Relatório da validação estrutural do pacote; não é teste da aplicação. |
| `SHA256.json` | Checksums dos arquivos do pacote, sem incluir a si próprio nem o ZIP. |
| `LEIA-ME.md` | Este guia de entrada. |

## Escopo integrado

O comando curto `connect [harness] [project-name] [--id HARNESS_ID]`, aliases raiz, CWD, sugestão Git com fallback, projeto lógico separado da raiz física, ID do Harness explícito/automático, retomar/adicionar, conflitos entre IDs, confirmação final, persistência, concorrência, recuperação, JSON/scripts, compatibilidade e exibição na Home existente estão especificados no plano.

## Base de código

Referência documentada: `OktoLabsAI/okto-nexus`, `feature/v0.3.5`, SHA `2463c05833f533bc5a5676a5644774cff949ca28`. Não é uma declaração de HEAD atual ou da versão instalada. Conferir o checkout antes de editar e preservar código em andamento. A primeira tarefa faz essa reconciliação.

O pacote inicia apenas o acompanhamento desta feature. Não sobrescrever registros de outras frentes, nem reconstruir recursos existentes. Nenhum teste do Nexus foi executado para preparar os arquivos.

## Verificação local dos arquivos

Após extrair o ZIP, execute com Python 3.11 ou compatível:

```sh
python VALIDAR_PACOTE.py
```

O script só lê os arquivos do pacote. Não chama rede, Git, Nexus, banco, cofre ou provedor. O ledger pode ser editado durante a implementação; depois disso, os checksums originais servem como referência do pacote entregue, não como hashes do progresso do projeto.
