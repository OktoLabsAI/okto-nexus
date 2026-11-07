## 2026-11-07 — campanha real dos serviços temporários vazios

Executadas as 24 ações únicas aprovadas no Task Scheduler do Windows, 12 por
componente: instalar duas vezes, iniciar e reutilizar, desabilitar, parar,
recusar início desabilitado, habilitar, iniciar, reiniciar, parar e remover.
Prontidão canônica confirmou instância, geração, versão e supervisor; handles
Windows comprovaram reutilização e saída dos processos próprios. As duas
tarefas foram removidas, todos os owners observados encerraram, a porta 52106
foi liberada e os dados temporários preservados. Os 981 arquivos dos três
pacotes permaneceram iguais aos hashes aprovados.

Duas interrupções da instrumentação foram preservadas: comparação de PATH sem
considerar a normalização feita pelo produto e falha transitória de gravação
WinError 5. As retomadas reconciliaram os mesmos recibos/processos e não
repetiram efeitos; são 24 ações totais, não soma de tentativas. A ordenação
exit/birth do restart foi verificada em execução; o valor isolado de exit da
geração anterior não foi retido separadamente, conforme a curadoria.

SVC-T07 passa a VERIFIED para a topologia Windows observada. T14 permanece
parcial: contexto salvo foi conferido, mas não houve variação deliberada de
cwd/PATH entre instalação/início ou amostra independente do contexto do filho.
T17 não incluiu habilitação repetida nem alteração externa; T20 não incluiu
próximo connect; T27 não incluiu foreground após a remoção. Logon, crash,
logout, suspensão, reboot, credenciais e M1 continuam com seus próprios gates.
O mapa inicialmente incorreto de T14 foi corrigido antes do commit, preservando
as ações e a correção auditável. A campanha não encerra AC-13/AC-14.
Evidência: `plans/agent_ops/evidence/r3-native-user-service-execution/campaign/qualification.json`.
