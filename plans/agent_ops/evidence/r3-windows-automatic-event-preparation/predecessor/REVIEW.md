# Automação Windows — preparação não selecionada

Estado: **UNSELECTED**. Não há janela real selecionada, tarefa registrada, evento executado, serviço iniciado/parado ou chamada de provedor. O plano manual T permanece byte a byte intacto. Esta preparação não promove nenhum critério de aceitação.

São no máximo três eventos separados, um de cada vez: suspensão/retorno, saída/login e reinício/login. Não há evento extra de shutdown/power-on nem encadeamento automático após entrar no Windows. O login após logout/reboot é manual; não se lê senha, não se configura autologin e não se força fechamento de aplicativos.

## Comandos e efeitos propostos

* Saída: `rtk proxy C:\Windows\System32\shutdown.exe /l`.
* Reinício: `rtk proxy C:\Windows\System32\shutdown.exe /r /t 0`.
* Suspensão: chamada exata `powrprof.SetSuspendState(FALSE, FALSE, FALSE)`, sem hibernação/fallback. Requer `SeShutdownPrivilege` no token próprio. Habilitar somente o privilégio já atribuído ao próprio token; se ausente/negado, recusar, sem elevação. O segundo argumento é obsoleto e não tem efeito; não o descrevemos como garantia de fechamento gracioso. O terceiro FALSE conserva eventos de despertar habilitados.

Não usar `/f`, `/g`, `/sg` nem timeout positivo/default de shutdown: a Microsoft documenta que `/t > 0` implica `/f`. Aplicativos podem bloquear/cancelar uma saída ou reinício sem força. A tentativa fica registrada; não há retry automático. Uma contagem regressiva opcional deve acontecer **antes** do comando, fora de shutdown, e terminar sem efeito se a janela expirar.

O retorno de um comando/API não prova que o evento ocorreu. Logout exige mesmo principal/novo logon/mesmo boot; reboot exige mesmo principal/novo logon/novo boot. Suspensão não é inferida de tempo decorrido, API de sucesso ou ausência do processo: o coletor a deixa `EVENT_UNCONFIRMED` até observação independente do evento, registrada aditivamente. Fast Startup e alteração de relógio não são descartados por suposição.

## Recuperação e evidência

`collect.py` reutiliza os módulos pinados `event_native.py`, `event_observer.py` e `history.py`, com as casas reais e Q atualizado. O before exige READY atual dos dois serviços, seis handles reais, task digests novos e revalidação de identidade após leitura de history. Nenhum before antigo é substituto. O after consulta status e o histórico real, compara metadados allowlisted e não interpreta SUCCEEDED como settlement. Não há acesso a vault/operator-auth/payload pessoal.

Uma tarefa temporária de observação pode ser registrada **somente depois da revisão da janela concreta**: LogonTrigger do SID próprio, InteractiveToken, LeastPrivilege, sem senha, sem start de serviços e sem evento OS. Sua única ação é Q/pythonw + `collect.py --plan <selected-plan> --sha256 <pin>` (after é default). `WakeToRun=false`; ela não é um mecanismo de autologin/despertar. Se o usuário não entrar, não há execução dessa tarefa. Após suspensão, o controlador que continuar vivo chama o mesmo after diretamente, pois não se presume novo logon.

O observer before mantém os seis handles por até 1800s; logout/reboot pode encerrar esse observer. Sem recibo final real dos handles, saída física permanece UNKNOWN. O after tem laço de consulta de 180s e herda os limites SQLite de history; não promete interromper chamadas de SO bloqueadas. Nenhum retorno falso DRAINED é fabricado. Uma coleta after reservada e interrompida não é repetida automaticamente.

## Sequência concreta futura — não executada

1. Root conclui a preparação de serviços separada e confirma ambas as coortes reais READY. Nenhuma ação de lifecycle está neste suplemento.
2. Selecionar um evento e janela UTC de até 30 minutos, após revisão. Rodar Q com `-I -B -X utf8 select_event.py --proposal-sha256 <SHA plan-template.json> --event <01-suspend-resume|02-sign-out-logon|04-restart-logon> --not-before <UTC> --expires <UTC> --reviewed-event-window`. O seletor cria apenas arquivos novos e XML; não registra tarefa nem executa evento. A pasta por evento é exclusiva, impedindo seleção repetida por acidente.
3. Ler `selections/<event>/commands.json`. Registrar somente `task_name` exato de observação, recusando colisão: `Get-ScheduledTask -TaskName <name> -ErrorAction SilentlyContinue` deve estar ausente; então `Register-ScheduledTask -TaskName <name> -Xml (Get-Content -LiteralPath <recovery-task.xml> -Raw)`. Não passar Force, Password, RunLevel elevado ou credenciais. Verificar definição/principal/ação/trigger reais antes de prosseguir. O XML contém SID próprio e fica local; não copiá-lo para relatório público sem necessidade.
4. Executar o argv `before` e esperar a prova `BEFORE_RETAINED`; manter esse processo/handles. Registrar tentativa exclusiva com plan SHA, before SHA, evento e horário imediatamente antes do único comando acima. Validar novamente janela/principal e ausência de tentativa anterior. Esta etapa de execução é seleção do root; não está automaticamente habilitada pela existência do template.
5. Executar um único evento. Em logout/reboot, usuário entra manualmente. Em suspensão, manter disponível despertar manual. Aplicativo bloqueando ou resultado incerto: preservar, sem `/f` ou repetição.
6. A tarefa logon (ou after explícito pós-suspensão) grava coleta real. Confrontar history, boot/logon, shutdown receipts e handles existentes; não criar marcador `performed_by_user=True` para um comando automatizado. O helper original manual não é alterado.
7. Remover somente a tarefa temporária com nome/definição/principal ainda iguais, após seu processo observador terminar. Se estiver rodando, não encerrá-lo para limpar. Não modificar as duas tarefas dos serviços. Revisar o resultado antes de selecionar outro evento.

## Capacidade observada e limites

`powercfg /a` confirma S0 Low Power Idle (Network Connected), hibernação e Fast Startup; S1/S2/S3 e Hybrid Sleep indisponíveis. A política Wake Timers está AC=1, DC=0. GetSystemPowerStatus e metadados de logon/boot próprios estão em `capabilities.json`. Isso **não** prova que um timer de desktop desperte esta máquina em Modern Standby. Não haverá mudança de powercfg/política; wake timer automático não foi selecionado. Despertar manual é a alternativa real, não um sucesso automático presumido.

A materialização RO terminou exit0 (tool 3d5237), com dois avisos COM `Win32 exception occurred releasing IUnknown` na liberação de wrappers WMI herdados. Os campos de boot/logon coletados são preservados com sua condição real; não houve comando de serviço ou evento. Os avisos não são silenciosamente convertidos em prova de aceitação.

## Documentação primária

* [shutdown](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/shutdown): `/l`, `/r`, `/t` e força implícita.
* [SetSuspendState](https://learn.microsoft.com/en-us/windows/win32/api/powrprof/nf-powrprof-setsuspendstate): argumentos, privilégio e valor de retorno.
* [Powercfg](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/powercfg-command-line-options): consultas de capacidades/política.
* [Task Scheduler LogonType](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-logontype-principaltype-element): InteractiveToken exige usuário já conectado.
* [WakeToRun](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-itasksettings-put_waketorun) e [system wake-up events](https://learn.microsoft.com/en-us/windows/win32/power/system-wake-up-events): intenção de wake não é garantia nesta configuração S0.
* [Modern Standby wake sources](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby-wake-sources) e [desktop apps/Modern Standby](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/integrating-apps-with-modern-standby): diferenças AC/DC e suspensão de aplicações desktop.

Os 8 testes são offline e usam fixtures para o coletor: não são teste real de logon, suspensão, reboot, registro de tarefa ou continuidade produtiva. Seleção/registro/comando ainda dependem da janela concreta; nenhuma nova preparação fora deste escopo é necessária aqui.
