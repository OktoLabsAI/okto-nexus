# Server lane — contrato defensivo em navegador real

Seis checks passaram contra o bundle `index-Dcu4bArB.js`, com a aplicação real,
SQLite migrado e HTTP loopback. O harness injeta14 ocorrências válidas de domínio
na porta de consulta canônica pré-autorizada:6 Server,4 do projeto A e4 de B.
Não existe produtor global real novo nem linha NULL inválida nas tabelas fonte.

- Contadores Needs you são4/4/8 em A/B/Todos e não incluem as6 ocorrências Server.
  Projeto, agente e Work state não atribuem itens Server a projetos.
- Páginas reais `/home/attention` e `/home/server-attention` conservam identidades
  canônicas distintas, sem duplicar ou misturar partições.
- Mark seen usa POST canônico real: mesmo attention_id/source_revision e
  preference_revision0→1. Repetir a revisão antiga retorna409, sem sucesso
  roteado. Fatos, totais, revisões e páginas do projeto permanecem iguais.
- Pausa bloqueia preferências; projeto vazio mantém a faixa Server separada.
- Partial/403 roteados somente nos GETs comprovam freshness independente e
  limpeza do payload protegido. Não representam revogação real de credenciais.
- Summary e páginas canônicas clássicas passaram22 GETs com filtros de projeto,
  agente, categoria, kind, prioridade, estado e visto. O baseline autorizado
  inclui16 ocorrências:14 do probe e2 watches existentes legítimos.

A primeira rodada passou os cinco checks Home, mas o adaptador de teste SQL
expunha apenas `filtered` e recusava filtros usados pelo App clássico. Seus
500/503 não foram aceitos como rodada final limpa. Somente a subclasse da
fixture foi adaptada para expor `viewing`/`filtered` completos e aplicar os
filtros canônicos às ocorrências de contrato. Clock de consulta fixo no seed;
budget padrão de5segundos preservado. Nenhum código de produto foi corrigido
para acomodar o harness.

A rodada final teve zero pageErrors e apenas o403 de GET deliberado no console.
O processo fixture encerrou com exit0 pelo handle próprio, o fechamento do
browser próprio retornou0 e seu PID ficou ausente, sem força ou browser pessoal.
As fontes de servidor já existiam antes do READY e seus8 pins de import conferem;
o script do cliente foi comparado integralmente ao código executado pelo CLI.

As capturas são dados sintéticos de contrato, não incidentes reais. Elas mostram
a Home; não certificam o tempo de atualização do badge lateral de Attention.
