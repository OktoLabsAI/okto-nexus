# M3f — Contenção compartilhada causada pelo próprio diagnóstico

## Incidente observado

Na instalação global M3c, geração 69, o processo 18616 permaneceu vivo e a UI
confirmou Pi, Claude e Codex em `LOCAL · RECOVERING`. Os três registros de
recuperação individual continuavam `READY`; o executor compartilhado estava
`RECOVERING`.

O log de 2026-10-17T02:03:25Z identifica o caminho
`defer_publication → _recovery_event → SqliteUnitOfWork.__enter__`. A escrita do
aviso `RECOVERY_PUBLICATION_DELAYED` sofreu `DB_ERROR` retryable por timeout na
admissão FIFO de escritores. O erro secundário escapou para `owner.failed()`,
que interrompeu o despachante e iniciou contenção de todos os recursos locais.

O dump de threads posterior mostrou os workers ociosos. A contenção inicial da
fila de escritores já havia cessado; não foi possível atribuir sua origem a
uma transação específica com a instrumentação disponível. Isso não é evidência
de corrupção do SQLite nem de falha simultânea dos três provedores.

O owner usa o mesmo sinal terminal para contenção e encerramento; a recuperação
de inicialização não reativa esse owner parado. Esse limite permanece no plano
de supervisão M6: não se deve limpar o sinal ou recriar um owner sem primeiro
comprovar encerramento dos produtores e liberação dos recursos antigos.

## Correção

- Timeout transitório ao persistir o aviso `RECOVERY_PUBLICATION_DELAYED`
  mantém esse aviso no log e não derruba o host. A revisão M4d2 restringe
  explicitamente a exceção a esse código: outros registros de recuperação
  também são usados antes de liberar recursos e continuam obrigatórios.
- A escrita dos fatos de execução continua obrigatória. Publicações pendentes
  continuam sendo tentadas pelo owner existente, sem repetir o efeito nativo.
- Falhas não transitórias não são suprimidas.
- A resposta de recuperação manual verifica se o despachante está realmente
  ativo. A mera existência de um objeto `pump` não é mais prova de prontidão.

## Validação e implantação

Passaram 12 testes de fonte e 20 testes do pacote instalado, sem alterações das entradas durante a campanha. A regressão reproduz contenção real da fila de escrita na emissão
do diagnóstico, combinada com indisponibilidade temporária da publicação de
recibos, nos três adaptadores. Também cobre falha permanente e resposta de
recuperação manual com o owner já parado. Os peers de harness desses testes são
determinísticos; a validação real pela interface será registrada separadamente.

O diagnóstico foi realizado antes de qualquer reinício. Para aplicar código ao
processo já contido será necessário encerramento controlado, backup e nova
inicialização; isso não deve ser descrito como recuperação espontânea do M3c.

## Implantação real em 17/10/2026

Correção commitada e enviada em `78e0b5c`, após M4d1 em `b816fd7`.
O sinal de encerramento normal foi aceito pelo processo antigo, mas a versão
M3c continuou em drenagem pendente. Antes da finalização desse PID específico,
foram preservados os stacks e confirmados zero slots ocupados, zero turnos
ativos no ledger e ausência de processos filhos do servidor. Foi necessário
finalizar o processo 18616; não houve limpeza de locks nem edição de estados.
Os 263 bancos foram copiados depois da saída do processo.

Pacotes instalados e comparados byte a byte com os artefatos: Nexus 0.3.1
(539 arquivos), Core 0.0.12 (156), Connector 0.0.10 (98). As dependências também
foram verificadas. Core e Connector são os artefatos M3e já publicados nas
branches, sem mudança adicional de código neste incidente.

A geração 70 iniciou no processo 39648, launcher 12792. O host ficou
CONTROL_READY às 02:54:18 UTC. Os agentes concluíram automaticamente:

| Agente | READY em UTC |
| --- | --- |
| Codex | 02:54:53.813 |
| Claude | 02:55:23.999 |
| Pi | 03:03:20.844 |

A UI Graph confirmou os três presentes após a recuperação. Pi ainda levou
cerca de nove minutos: a primeira passagem verificou o histórico antigo e
persistiu certificados de retirement antes de liberar READY. O avanço foi
observado (3, 18, 55 certificados do Pi), sem novo erro. Essa barreira de
histórico permanece como pendência M4; este resultado não qualifica a latência
de recuperação. Durante o acompanhamento houve uma amostra de CPU total em
100%; não se atribuiu a causa integral ao Nexus nem se usou isso para dispensar
a correção da barreira histórica.

O Meta-harness foi aberto pela UI, mas o controle do Chrome sofreu timeouts e
desconexão ao preencher a mensagem. Nenhum novo envio/resposta real foi
confirmado nesta campanha. Não houve nova chamada ao Codex, cuja quota externa
continua registrada em L5. O teste funcional de resposta pela UI permanece
pendente; não foi substituído por envio direto via API.

Evidências privadas locais: `build/runtime-recovery-diagnostic-live/`,
`build/recovery-diagnostic-before.json`, dumps de stacks e relatórios instalados
em `build/runtime-recovery-diagnostic-installed/`. A aplicação foi deixada em
execução para teste pelo usuário.

## Complemento da validação pela UI

Na continuação da mesma geração 70, sem novo restart, o teste enviado ao Pi
pelo Meta-harness às 00:14 locais respondeu `M3F_PI_OK` às 00:15. O teste
enviado ao Claude às 00:20 respondeu `M3F_CLAUDE_OK` às 00:21. Ambos mostraram
1/1 ACK na interface. Esses horários são a resolução apresentada pela UI,
não medições precisas de latência. Codex não foi chamado novamente por L5.

A aba Agents inicialmente reteve RECOVERING antigo até Refresh Agents;
o backend confirmou READY para os três. A origem dessa observação da UI
permanece em investigação. Também foram identificadas quatro reservas de
aquecimento Pi presas em STARTING após recusas anteriores ao Core; a resposta
real usou capacidade adicional. Detalhes em `m4d2-validation.md`.
