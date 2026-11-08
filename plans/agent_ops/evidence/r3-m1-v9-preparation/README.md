# M1 v9 — proposta pronta para aprovação

A correção da resposta perdida da checagem de versão está no commit Nexus
`44c3825445144fa48b5c5ccf6b0d2bd48b21c3b7`, com 59 testes instalados aprovados.
A campanha v8 terminou antes do teste de modelo; o Nexus parou normalmente,
a tarefa foi removida e os dados foram preservados. O controlador e sua reserva
permanecem encerrados, sem reset ou replay.

Esta é uma **nova campanha**, com a conta já autenticada no Codex CLI e os
seguintes limites:

- Até 6 novas reservas produtivas. O histórico conserva 3 reservas: 2 com
  inferência confirmada e 1 da v8 sem inferência confirmada. Máximo de 9 reservas
  cumulativas, com até 8 inferências confirmadas se todas as novas ocorrerem.
- 45.843 tokens observados carregados; preventiva cumulativa de 200 mil tokens
  e tolerância operacional de 700 mil, sem promessa de bloqueio atômico.
- Uma instalação offline, duas tarefas temporárias próprias do Windows e
  8 ações explícitas de instalar/iniciar/parar/desinstalar; no máximo um início
  implícito adicional da mesma tarefa Connector durante a conexão.
- Sem parada forçada de serviço, logout, reboot, repetição de intenção incerta
  ou novos ciclos além dos comandos propostos. Dados e evidências preservados.

A proposta executável é [bundle/m1-codex-campaign-proposal-v9.json](bundle/m1-codex-campaign-proposal-v9.json),
SHA256 `9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279`.
Os comandos exatos estão em [bundle/proposed-commands.json](bundle/proposed-commands.json)
e [bundle/planning-commands.json](bundle/planning-commands.json). Os scripts
executáveis permanecem nos caminhos temporários pinados da proposta; esta cópia
do repositório conserva os mesmos bytes para revisão.

Passaram 24 testes puros do controlador, 27 do instalador, uma regressão da
pinagem do Python e 12 recusas de entrada. O candidato anterior, que omitia o
pin do Python na verificação de cada comando, foi rejeitado e preservado.
A raiz conferiu os 27 módulos executáveis, os três wheels e o binário nativo por
hash, sem executá-lo. As duas tarefas estavam ausentes, a porta 54913 disponível
e o diretório da campanha inexistente. Esses estados serão conferidos novamente
imediatamente antes dos efeitos. O novo alvo contém apenas dependências; os três
produtos ainda não foram instalados nele.

**A v9 ainda não está autorizada nem executada.** A proposta v8 autorizada
excluía “Additional service cycles or task restart”; por isso estes novos ciclos
exigem uma aprovação específica. A autorização cobre apenas esta campanha
concreta e não transforma os testes de preparação em aceite M1.
