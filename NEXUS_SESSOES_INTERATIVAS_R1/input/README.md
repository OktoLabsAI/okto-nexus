# Nexus — sessões interativas R1: pacote de implementação

Este é o pacote inicial consolidado para o Codex implementar chat por sessão na UI, entrada nativa de usuário, fila para o próximo turno, steer explícito, comandos conhecidos por capacidade e terminal nativo anexável com detach sem interromper execução.

## Como começar

Entregue este diretório ao Codex e use `PROMPT_CODEX_NEXUS_SESSOES_INTERATIVAS_R1.md`. A especificação normativa é `PLANO_CODEX_NEXUS_SESSOES_INTERATIVAS_UI_CLI_R1.md`. Ela contém 41 tarefas, 148 cenários de aceite, 24 requisitos e 8 etapas de implementação.

Não é uma emenda que dependa de outro plano para explicar o escopo. O produto já existente deve ser auditado e reutilizado. O pacote não implementa a feature nem autoriza acesso a credenciais, execução paga, instalação global, publicação ou alteração da instalação pessoal do usuário.

## Arquivos

| Arquivo | Uso |
|---|---|
| `PLANO_CODEX_NEXUS_SESSOES_INTERATIVAS_UI_CLI_R1.md` | Decisões, arquitetura, comportamento, backlog, testes e fontes. |
| `PROMPT_CODEX_NEXUS_SESSOES_INTERATIVAS_R1.md` | Instrução pronta para iniciar o Codex. |
| `NEXUS_SESSOES_INTERATIVAS_LEDGER_R1.json` | Requisitos, tarefas, dependências, cenários e campos de evidência. |
| `MATRIZ_CAPACIDADES_SESSAO_R1.md` | Diferenças Codex/Pi/Claude e roteiro de qualificação. |
| `MATRIZ_CAPACIDADES_SESSAO_R1.json` | Template estruturado; nenhuma combinação pré-marcada como qualificada. |
| `validate_package.py` | Verificador de integridade e consistência dos documentos. |
| `VALIDACAO_PACOTE_R1.json` | Resultado da validação documental efetuada na preparação. |
| `SHA256SUMS.json` | Hashes dos arquivos do pacote, exceto o próprio manifesto. |

## Decisões essenciais

Enviar pelo chat não cria mensagem no barramento Operator. Busy aguarda próximo turno completo; steer depende de ação explícita e semântica real. Interromper pausa pendências; fechar interface não. A TUI nativa e o chat Nexus são superfícies diferentes da mesma execução governada; resume de conversa salva não comprova attach vivo.

`connect -i/--interactive` abre nativo; `--no-interactive` só conecta; sem flag pergunta ao final em TTY. Sem TTY/JSON não pergunta. Flags são propostas de implementação neste plano. Retomar depois usa sessão exata, nunca --last ou uma cópia da execução.

## Baseline e estado inicial

Nexus: `feature/v0.3.7`, SHA `8b4001fa1db17bf29d0c773eed3535e79fce70cb`.
Core: `feature/v0.0.14`, SHA `497ee2b7a14b99c50cba97eac74f3b00d4863f26`.
Connector: `feature/v0.0.13`, SHA `a4d510080d7a685fa442a4c5c30419952589fe04`.

São referências estáticas, não releases ou instalações verificadas. Reconciliar o HEAD real antes de editar; não fazer reset/clean nem apagar trabalho em curso. Tarefas iniciam TODO, cenários NOT_RUN e matriz sem qualificação nativa. O Codex deve preservar evidências de outras frentes e registrar a implementação/validação desta feature separadamente.

## Conferência do pacote

Execute no diretório extraído, com Python 3.11+:

```sh
python validate_package.py
```

O verificador não acessa rede, não inicia Nexus, não utiliza provedor e não modifica o repositório. Ele verifica hashes, JSON, referências, dependências sem ciclos, cobertura documental e estados iniciais. Depois de editar o ledger durante a implementação, os hashes do pacote original deixam de corresponder; preserve o pacote original como referência.

**Validação do pacote não é teste da aplicação.** Native attach, UI, fila, sinais, Windows/macOS/Linux e fluxo remoto continuam exigindo as campanhas descritas no plano.
