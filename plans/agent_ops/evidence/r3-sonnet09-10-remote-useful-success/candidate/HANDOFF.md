# Composição pendente — 09 útil e 10 continuação

Nada foi iniciado. `work-plan.json`, `budget-seed-approved.json`, `paid-work/` e `authorization-record.json` ainda não existem. O materializador recusa enquanto faltar a resposta explícita. A política proposta só será ativada em uma composição futura após Root registrar essa resposta; não altera nenhum checkpoint ou plano anterior.

## Registro da resposta

Root registra a resposta real em `authorization-record.json` nesta pasta, com os campos abaixo. Não pedir ao usuário hash, assinatura ou outra confirmação:

```json
{
  "explicit_user_approval": true,
  "user_response": "<resposta real>",
  "response_reference": "<referência real da resposta>",
  "policy": {
    "limit": 500000,
    "preventive": 480000,
    "max_requests": 5,
    "server_max": 6,
    "new_requests_max": 2,
    "continuation_input_multiplier": 1
  },
  "carry_tokens": 180426,
  "native_charges": 3,
  "server_admissions": 4
}
```

Este bloco é apenas formato; não é um recibo nem resposta recebida.

## Ordem futura, após seleção de Root

1. Usar os comandos já preparados em `../sonnet-after07-proposal-0ls1sihr/lifecycle/commands.json`: prepare, start/select/watch Nexus, start/select/watch Connector. Reutiliza Q e tarefas atuais; nenhum reinstall/force/provider. As novas seleções e observers são requisitos reais do contexto, sem reaproveitar os encerrados.
2. O grant `grant_3fbf…` expira em **2026-11-15 16:24:41 UTC** e já não oferece a janela de600s. Após L3 READY, executar a revisão canônica em `future-commands.json`, conferir escopo/actions/3execuções/60min e `can_issue`, depois emitir uma única vez com `--review` exato. Não usar SQL, `connect` ou reset de perfil. O único trecho que muda no checkpoint é a autorização; sessão07 e demais ancestrais permanecem. Resposta perdida exige observação/recuperação canônica, nunca novo request para esconder incerteza.
3. Materializar uma única vez com o comando pronto em `future-commands.json`. O script não chama HTTP, serviços ou provider: lê autorização, novos recibos L3 e o checkpoint canônico com grant renovado; deriva a semente globalNative5 preservando as três linhas históricas; escreve plano e comandos futuros.
4. Root revisa o plano gerado e só então seleciona `prepare`, `useful`, e eventual `continuation`. O plano mantém BROOT como projeto CLI e connector-project como workspace remoto. A continuação exige resultado útil confirmado, orçamento recalculado e grant válido; qualquer pergunta nativa nessa fase fecha admissão/seleção de ferramenta. `setup` e `useful` mantêm reserva2x; apenas continuação usa1x sobNative5 autorizado.

## Pergunta nativa dentro da validade

`task-prompts.json` é byte-idêntico ao aprovado: única PowerShell com RTK e Python absolutos, stdlib CSV/hashlib/JSON, somente CSV conhecido e relatório esperado. Root pode revisar antecipadamente esses caminhos e o formato do comando. O comando real ainda precisa ser comparado quando a pergunta chegar; não se reaproveita a aprovação07.

O callback publica `fast-native-question.json` (ID/revisão/expiry/tool/commandSHA) antes de qualquer hook lento; o comando fica apenas em `private/native-command-root-view.json`. Ele roda mesmo em páginas sem novos eventos, portanto publicar `root-manually-ready.json` atualiza a flag no próximo poll. Não registrar ready antes de conhecer request/op/session exatos e estar efetivamente disponível.

O seletor `fast_approval.py` continua manual: exige pergunta única, revisão/escopo/hash exatos, observação<=20s e>=30s restantes. Cria uma vez `native-decision.json`; o runner envia uma vez pela rota canônica. TTL120 não muda. Não selecionar se expirou. O plano futuro **não seleciona repetir console/dashboard SVC09** para não atrasar a pergunta; os artefatos07 permanecem separados. O observer opcional independente usa somente GET e só afirma atividade positiva em SUBMITTED+DISPATCHED; estados ausentes/desconhecidos resultam `null`.

Diagnóstico novo registra somente classe/código/etapa da primeira exceção antes da contenção; não inclui mensagens, payloads, comandos ou credenciais. As falhas originais e os limites de observação continuam preservados.
