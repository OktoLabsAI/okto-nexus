# M4d1 — Catálogo canônico em lotes e atribuição exata de reservas

Qualificação dirigida concluída: 7/7; cobertura acumulada de 52 casos distintos. M4 continua em andamento.

## Decisão de armazenamento

O Connector usa um `SQLiteJournal` por host (`services/core_host.py`,
`ensure_journal`). O Nexus mantém um journal por sessão (`bootstrap/runtime_host.py`,
`_compose`). No Core, cada journal tem um executor de operações e quotas de
armazenamento/eventos, além dos limites por sessão (`journal.py`, `JournalLimits`).
Unificar fisicamente todos os journals do Nexus compartilharia essas filas e
quotas. Não há evidência de desempenho ou isolamento suficiente para adotar essa
mudança como solução da varredura histórica.

Decisão: manter os journals separados e usar a sessão canônica como catálogo de
localização. A migração 145 acrescenta `local_journal_name` com índices por nome e
por preenchimento pendente. Não é um ledger adicional de processos, uma prova de
liberação ou um checkpoint de execução. M5 continua responsável por compartilhar
políticas e contratos entre os adaptadores, sem exigir arquivos físicos iguais.

## Implementação

- Preenchimento transacional em lotes de até 128 sessões. Cada lote concluído
  sai do índice de pendências; uma interrupção retoma os restantes. O preenchimento
  não cria journals nem invoca harnesses.
- Aberturas novas registram a localização antes de autorizar/compor o runtime,
  inclusive antes do ponto em que a autorização pode abrir um journal sem binding.
- A auditoria de arquivos percorre páginas de até 128 entradas e confere nomes
  por índice. Não monta um conjunto com todas as sessões/arquivos em memória.
  Arquivos sem correspondência ou ausência do ledger conservam o bloqueio.
  Sidecars do ledger sem o arquivo principal também não são um armazenamento vazio.
- Reservas ocupadas e planos de recuperação consultam a sessão exata. Reservas
  provisórias ainda exigem sua associação durável no Core. Uma reserva ocupada
  invalida o checkpoint anterior, como no M4c.
- A descoberta de agentes consulta sessões ainda não verificadas e registros de
  recuperação pendentes/de geração antiga. Um agente sem journals pendentes ainda
  precisa atualizar sua geração de prontidão; não fica esquecido por esse filtro.
- A recuperação de um agente verifica apenas seus caminhos pendentes. A auditoria
  do diretório compartilhado deixa de ser repetida por cada trabalhador de agente.

## Limites ainda abertos

A auditoria do diretório ainda acontece na inicialização. Seu custo de enumeração
continua proporcional ao número de arquivos; somente o consumo de memória é
limitado em lotes. Não confundir custo constante de consultas após o preenchimento
com custo constante do startup completo.

O limite anterior para recuperação de muitas sessões ainda não verificadas e
a primeira verificação de seus journals continuam pendentes. Remover esses
limites, estabelecer uma fronteira durável de auditoria que permita tirá-la da
admissão e garantir orçamento/justiça entre streams são os próximos passos M4d.
Nenhuma instalação global ou gate novo de UI faz parte deste checkpoint.

## Campanha instalada e correções de sincronização

A campanha ampla executou 52 casos, com **50 aprovados e duas falhas**. Os
arquivos de entrada permaneceram congelados durante a execução. As falhas foram:

1. O caso de container com abertura `OUTCOME_UNKNOWN` exigia `READY` na resposta
   imediata do endpoint de retry. O endpoint observava o trabalhador por um segundo
   e retornou corretamente `RECOVERING`. A reprodução isolada passou sem mudanças
   no produto. O teste agora exige que a recuperação automática convirja **antes**
   de chamar o retry; mantém o limite de 20 segundos, o estado final, a prova de
   contenção e a proibição de replay.
2. O caso de encerramento gracioso expirou nos 40 segundos de preparação do
   processo descartável. O arquivo de pronto ainda não existia; o encerramento
   nem havia sido provocado. Essa preparação cria banco, dois peers nativos e
   três conexões remotas. Ela agora tem prazo próprio de 120 segundos e registra
   sua duração. O limite de recuperação após o encerramento continua em 20 segundos;
   o prazo de shutdown continua em 30 segundos. Os casos de kill e kill antes do
   binding passaram na campanha original.

Uma revalidação intermediária aprovou seis dos sete casos relacionados. No corte
forçado, o teste encerrava o redirector `python.exe` do venv no Windows, sem
comprovar que o PID efetivo do servidor havia terminado. O `ServeLock` recusou
corretamente esse dono ainda vivo. A hipótese inicial de prontidão antecipada não
explicava essa falha: o traceback aponta para a aquisição do lock, antes do boot.

O fixture agora usa o interpretador base com os mesmos caminhos explícitos de
pacotes e informa seu próprio PID; o teste exige igualdade com o processo que
vai encerrar. A espera por retomada também exige inicialização concluída,
dispatcher ativo e ausência de agentes bloqueados. Um conjunto vazio antes da
inicialização não é usado como sinal de prontidão. A proteção do lock no produto
não foi alterada nem contornada.

Somente três arquivos de testes/fixture foram ajustados após a campanha ampla.
Os sete casos relacionados estão sendo reexecutados contra a **mesma wheel**,
com nova verificação dos bytes instalados e das entradas congeladas. Os relatórios
amplo e intermediário continuam registrados como falha, separadamente da rodada
final; seus resultados não serão apresentados como execuções sem falhas.

O aviso de stack após dois minutos no caso de 100 mil sessões ocorreu durante
a inserção dos dados sintéticos, antes da consulta medida. O caso passou. Isso
não mede latência de startup do produto com 100 mil arquivos reais.

As consultas medidas consumiram 63 instruções da VM SQLite para consultar o
catálogo e 142 para a parte SQL do startup, em 1 mil, 10 mil e 100 mil sessões.
Esses bancos sintéticos já tinham o catálogo preenchido, somente três sessões
pendentes e nenhum arquivo de journal. O resultado não inclui o custo de backfill
nem da enumeração inicial de arquivos.

Os testes de composição dos adaptadores usam peers determinísticos. Os testes
de término utilizam processos descartáveis reais sob contenção no Windows; não
representam execução nos provedores reais. Na interface da instalação global
M3c, Agents continuou LIVE com Pi, Claude e Codex locais ONLINE e pool do Pi 4/5.
Essa conferência foi somente leitura e não qualifica o M4d1 pela UI.


Rodada final: 7/7 passaram na mesma wheel, sem alteração das entradas durante a campanha. Recuperação após os três tipos de encerramento: 5,20 s, 6,36 s e 4,57 s. Os relatórios anteriores permanecem registrados como falhas.

Incidente posterior na instalação global M3c: geração 69 permaneceu RECOVERING após timeout ao registrar RECOVERY_PUBLICATION_DELAYED em 2026-10-17T02:03:25Z, que acionou contenção compartilhada. Os três registros individuais continuam READY. O processo 18616 continuou vivo; nenhuma reinicialização foi usada no diagnóstico. A observação ONLINE acima é anterior ao incidente e não representa o estado atual. M4d1 não corrige esse caminho.
