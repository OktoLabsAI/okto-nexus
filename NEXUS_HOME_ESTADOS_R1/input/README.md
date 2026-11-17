# Pacote Codex — HOME-STATES-R1

Comece por `PROMPT_CODEX_NEXUS_HOME_ESTADOS_R1.md` e leia `PLANO_CODEX_NEXUS_HOME_ESTADOS_BADGES_RESULTS_R1.md`.

O plano contém 32 tarefas, 116 cenários, 20 requisitos e sete etapas.
Abrange Active com Working/Idle, a dupla natureza de Needs You, badges de ações,
confirmação de retomada, semântica de Results e ajustes do acompanhamento contextual.
É uma especificação consolidada desta frente; não exige aplicar uma revisão anterior.

Arquivos:
- `PLANO_CODEX_NEXUS_HOME_ESTADOS_BADGES_RESULTS_R1.md`: contrato, backlog e cenários completos.
- `NEXUS_HOME_ESTADOS_LEDGER_R1.json`: template TODO/NOT_RUN com dependências e rastreabilidade.
- `PROMPT_CODEX_NEXUS_HOME_ESTADOS_R1.md`: instrução pronta para o executor.
- `verify_package.py`: valida documentos, hashes e referências; não executa Nexus.
- `MANIFEST_SHA256.json`: hashes do pacote.

Validação local do pacote:

```sh
python verify_package.py
```

O baseline de inspeção está fixado no plano. Reconciliar o HEAD atual antes de editar.
Não reconstruir módulos já implementados, não apagar evidências e não executar
campanhas pagas/alterações pessoais/deploy sem consentimento separado.
