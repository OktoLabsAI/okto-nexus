# M3p — recusa de abertura local antes da autorização

## Escopo fechado

Uma falha na preparação local, antes de `authorize_r4`, colocava o agente inteiro em recuperação e interrompia sessões saudáveis. O novo registro durável associa a recusa à operação original. O reconciliador aguarda o produtor dessa sessão, confirma no Core a ausência de claim e nascimento nativo, publica um receipt `PREPARATION_FAILED` sem efeito e aposenta somente a sessão que falhou.

Se um handoff já consumiu uma reserva de capacidade, o Core libera a reserva e seu slot físico `capacity:<reservation_id>` pela identidade exata. A recuperação permanece pendente quando falta prova; não assume que ausência de resposta equivale a ausência de execução.

## Evidência

- Antes da mudança, a falha injetada em `ApprovedLocalLaunch` parava uma sessão irmã saudável. Depois, dois modos de capacidade preservaram a irmã e aceitaram um novo turno.
- Um corte entre o fato persistido no Core e o receipt no Server foi retomado após recriar a aplicação no mesmo home; houve um único resultado terminal, aposentadoria local e nova abertura.
- Um handoff real com capacidade consumida falhou antes da autorização; o receipt foi `PREPARATION_FAILED`, a reserva exata terminou `RELEASED` e uma nova sessão abriu. O teste inicialmente revelou a tentativa incorreta de liberar o slot `capacity:<id>` como se pertencesse à operação de abertura; a correção usa a transição de capacidade do Core.
- Regressão de isolamento, recusa de lease inicial, aposentadoria de sessão não aberta e handoff reservado: **39 passed** (source checkout).
- Wheel Nexus 0.3.1 SHA-256 `5eab2bdfe53a98ec514467b6259fe8c4c7ea4db4453826d473298d59c0b1971f`, instalada em venv descartável. Com `pytest -o pythonpath=`, **4 passed** nos três cenários novos (o primeiro parametrizado em dois modos). O módulo `okto_nexus` foi carregado de `site-packages`.
- `py_compile`, Ruff nos arquivos novos e `git diff --check` passaram. Há apenas um aviso preexistente de depreciação Starlette/httpx nos testes.

## Limite

Este checkpoint qualifica a recusa local comprovadamente anterior à autorização e sua recuperação. Não conclui M3 inteiro nem atribui causa ao incidente anterior de todos os agentes em Recovering. Falhas após início de autorização continuam na contenção conservadora existente. Core e Connector não foram alterados. Os testes reais pela UI do milestone M2/M3 já constam em `ui-a-installed-restart-evidence.md`; este checkpoint técnico não fez novo rollout global.
