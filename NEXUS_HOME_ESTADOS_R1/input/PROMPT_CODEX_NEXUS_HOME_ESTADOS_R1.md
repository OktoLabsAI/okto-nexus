# Prompt para o Codex — HOME-STATES-R1

Implemente `PLANO_CODEX_NEXUS_HOME_ESTADOS_BADGES_RESULTS_R1.md` no checkout autorizado do repositório
`OktoLabsAI/okto-nexus`. Comece por HST-00. A referência inspecionada foi
`feature/v0.3.6`, SHA `f28a31a22436c366a4c8dbdf5e3b250d606a61be`, versão declarada 0.3.6 e Core 0.0.14.
Não retorne automaticamente a esse SHA. Registre HEAD, working tree, instruções
do projeto e drift. Não faça reset/clean, force-push, alteração da instalação
pessoal, deploy/release ou campanha paga sem autorização própria.

## Contrato de produto obrigatório

- Manter Active, Needs You e Results na mesma Home. Sem novo menu/quarta coluna.
- Active é harness conectado não globalmente bloqueado: Working ou Idle confirmado.
  Cadastro/processo aberto/silêncio não são prova de Idle; sessão one-shot fechada
  tem rótulo próprio, sem abertura automática de outra sessão.
- Needs You tem dois comportamentos: harness parado por dependência humana comprovada
  aparece com seus pedidos; harness que continua outro trabalho fica Active e apenas
  a solicitação aparece em Needs You. Uma sessão idle não é trabalho independente.
- Badges indicam resposta, aprovação, decisão, verificação ou N ações pendentes.
  Mesma ocorrência não ganha duas apresentações acionáveis ou outro contador no sino.
- Resposta registrada não prova aplicação nativa/retomada. Mostrar confirmação pendente,
  preservar a própria intenção e esperar evidência causalmente posterior correta.
- Results distingue turno, tarefa, verificação, falha, cancelamento, limpeza e reporte
  externo. COMPLETED não significa verificação aprovada sem prova específica.
- Card de harness não vai para Results quando termina. Entrega é objeto separado.

## Implementação

Reaproveite home_harness_board.py, home_harness_blocking.py, relações batch de
home_entries.py, RESULTS/result_item em sqlite/home.py e componentes existentes.
Não recrie Attention, protocolo, runtime, Quick Connect ou navegação.

Antes de implementar, faça mapa de prova por adaptador e tipo de pedido, e origem
real da verificação. Não extrapole item/tool/requestUserInput para Pi/Claude.
Tipos/validadores/backend/frontend precisam evoluir juntos, com compatibilidade.

Reproduza o caminho pausa + polling idêntico + hasPendingUpdate que pode bloquear
HarnessActivityPanel. Separe snapshot, pausa visual e detalhe. Um refresh não exige
fechar/reabrir nem apaga rascunho. Ação sensível continua revalidada canonicamente.

Abra direto uma sessão somente quando a referência exata é explícita ou a unicidade
é comprovada em conjunto completo. Com múltiplas sessões use nomes/estados/projeto;
nunca escolha a mais recente por heurística. Projeto aparece nos cards de All projects.
Retire Reconnect indisponível do destaque, sem simular restart individual de daemon.

## Execução e evidências

Use `NEXUS_HOME_ESTADOS_LEDGER_R1.json` como template de acompanhamento desta frente. Não sobrescreva
ledgers vivos nem promova evidências anteriores sem checar o SHA e as fronteiras.
Execute as 32 tarefas por dependências e os 116 cenários relacionados.
Cada etapa exige testes e relatório com arquivos/contratos, comandos, ambientes,
resultados e limitações. Implementação não é qualificação; fixtures/Node não são
harness real/AT/browser. Sem autorização para campanha, registre NOT_RUN/BLOCKED.

O verificador incluído checa apenas integridade/coerência deste pacote, não testa
Nexus. Reutilize CI e comandos reais do checkout para validar o produto.

Ao concluir, entregue implementação + testes + documentação + pacote com assets
corretos + relatório e rollback. Não mude o default de apresentação nem publique
release sem decisão explícita. Use os gates G0–G6 da especificação.
