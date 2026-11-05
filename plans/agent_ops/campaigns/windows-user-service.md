# Campanha Windows de tarefas temporárias — SVC-05/10/11/12

Status inicial: preparada; registro nativo depende da autorização solicitada ao
usuário. Esta campanha usa os candidatos já testados e instalados em venv limpa.
Não substitui os aceites de login/logout, reboot, crash, credenciais ou trabalho
produtivo do plano R3.

O snapshot revisável está em `../evidence/pr02-native-campaign-plan.json` e no
arquivo temporário apontado nele. Ele fixa o executável instalado, diretórios
descartáveis, porta loopback, versões, nomes exatos das duas tarefas e cada argv.
A preparação consultou a ausência desses nomes no Task Scheduler sem criar
tarefas nem dados de aplicação. Somente o diretório da campanha foi reservado.

## Execução autorizada

1. Confirmar o SHA-256 do snapshot aprovado e a ausência das tarefas. Usar o
   Python daquela venv, `-I`, cwd da campanha e somente as variáveis do SO
   explicitadas no snapshot. Nenhuma variável de credencial é herdada.
2. Para cada componente, executar os comandos do snapshot sequencialmente e
   guardar JSON, exit code, timestamps e duração. Uma observação expirada não
   autoriza lançar outro processo nem repetir registro às cegas.
3. Confirmar instalação repetida sobre a mesma identidade/definição; start/reuse
   com um PID/geração; disable preservando a geração ativa; stop com recibo
   `DRAINED`; recusa de novo start enquanto desabilitado; enable seguido de nova
   geração; restart com drain; uninstall de integração ativa com dados retidos.
4. Observar o Task Scheduler separadamente de IPC/HTTP. A tarefa estar running
   não prova prontidão. A saída do CLI não prova logout ou boot.
5. Confirmar ausência das duas tarefas após uninstall e preservar os diretórios
   descartáveis com recibos/logs para auditoria. Verificar que os nomes usados
   são exatamente os selecionados; não enumerar nem alterar outras tarefas.

Em qualquer falha, tentar somente stop canônico e uninstall da instância
selecionada. Se a confirmação nativa/ownership permanecer incerta, guardar os
recibos e informar o recurso residual para revisão; não forçar término ou
excluir uma tarefa sem comprovação. Não apagar dados para fazer o teste passar.

## Limites da autorização solicitada

- Duas tarefas temporárias do usuário, com início no login habilitado durante
  parte da campanha e remoção ao final pelo lifecycle implementado.
- Instâncias vazias e descartáveis; Nexus limitado a loopback, embeddings off,
  sem configuração de provedor, vínculo remoto ou uso de credenciais reais.
- Sem logout, reboot, edição da instalação pessoal existente, inferência paga,
  publicação de pacote ou merge.

A necessidade de autorização decorre do limite da seção 19 do plano fixo:
“sem alterar instalações pessoais, usar credenciais reais, publicar pacotes ou
fazer merge além do autorizado”. A execução nativa não é presumida autorizada
pelos testes isolados. O restante da implementação prossegue enquanto essa
resposta estiver pendente.
