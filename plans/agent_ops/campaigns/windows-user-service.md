# Campanha Windows de tarefas temporárias — SVC-05/10/11/12

Status em 2026-11-07: campanha autorizada e encerrada, com **24/24 ações únicas
concluídas**, tarefas removidas e dados temporários preservados. Não substitui
os aceites de login/logout, reboot, crash, credenciais ou trabalho produtivo
do plano R3.

O snapshot executado é a revisão 4 de
[`native-service-campaign-proposal.json`](../evidence/r3-campaign-proposals/native-service-campaign-proposal.json),
SHA-256 `862f986247ec9c0c4071f4b57ff422e2384128fe1f8c8b1b3b4ea2f9c3d19e0a`.
A [autorização](../evidence/r3-campaign-execution-authorization/authorization.json)
e a [qualificação real](../evidence/r3-native-user-service-execution/campaign/qualification.json)
registram os efeitos e a limpeza. Os snapshots anteriores permanecem históricos;
os pacotes executados também não são substituídos retroativamente pelos candidatos
corrigidos depois da campanha.

O snapshot executado fixa o executável instalado, diretórios
descartáveis, porta loopback, versões, nomes exatos das duas tarefas e cada argv.
O preflight confirmou a ausência dos nomes no Task Scheduler, homes vazios e
porta livre antes dos efeitos. Ao final, as duas tarefas estavam ausentes,
os processos tinham saído e a porta 52106 estava livre. Os 981 arquivos dos
pacotes permaneceram iguais aos hashes aprovados.

## Procedimento executado

Esta lista documenta a campanha encerrada; não é uma instrução para repetir
ações já consumidas. Recibos e interrupções de instrumentação foram preservados.

1. Confirmar o SHA-256 do snapshot aprovado e a ausência das tarefas. Usar o
   Python daquela venv, `-I`, cwd da campanha e somente as variáveis do SO
   explicitadas no snapshot. Nenhuma variável de credencial é herdada.
2. Para cada componente, executar os comandos do snapshot sequencialmente e
   guardar JSON, exit code, timestamps e duração. Uma observação expirada não
   autoriza lançar outro processo nem repetir registro às cegas.
3. Confirmar instalação repetida sobre a mesma identidade/definição; start/reuse
   com um PID/geração; disable preservando a geração ativa; stop com recibo
   `DRAINED`; recusa de novo start enquanto desabilitado; enable seguido de nova
   geração; restart com drain; stop e uninstall com dados retidos.
4. Observar o Task Scheduler separadamente de IPC/HTTP. A tarefa estar running
   não prova prontidão. A saída do CLI não prova logout ou boot.
5. Confirmar ausência das duas tarefas após uninstall e preservar os diretórios
   descartáveis com recibos/logs para auditoria. Verificar que os nomes usados
   são exatamente os selecionados; não enumerar nem alterar outras tarefas.

Em qualquer falha, tentar somente stop canônico e uninstall da instância
selecionada. Se a confirmação nativa/ownership permanecer incerta, guardar os
recibos e informar o recurso residual para revisão; não forçar término ou
excluir uma tarefa sem comprovação. Não apagar dados para fazer o teste passar.

## Limites da campanha executada

- Duas tarefas temporárias do usuário, com início no login habilitado durante
  parte da campanha e remoção ao final pelo lifecycle implementado.
- Instâncias vazias e descartáveis; Nexus limitado a loopback, embeddings off,
  sem configuração de provedor, vínculo remoto ou uso de credenciais reais.
- Sem logout, reboot, edição da instalação pessoal existente, inferência paga,
  publicação de pacote ou merge.

SVC-T07 foi verificado. T14 permanece parcial, pois não houve variação deliberada
de cwd/PATH nem amostra independente do contexto do filho. T17 não incluiu enable
repetido ou alteração externa; T20 não incluiu próximo connect; T27 não incluiu
foreground após uninstall. AC-13 e AC-14 continuam pendentes.

A campanha M1 usou outros alvos e teve encerramento separado: houve duas
admissões e trabalho cancelado, seguido da
[contenção autorizada](../evidence/r3-m1-authorized-containment/closure/summary.json).
Essa parada forçada não qualifica drain cooperativo nem o ciclo completo M1.
