# Eventos de sessão Windows — proposta offline

Nenhum evento ou serviço foi executado. Esta proposta fica para revisão do root
e autorização futura de uma janela pelo usuário; nenhuma pergunta foi enviada.
O arquivo `plan.json` contém paths, nomes completos, argv e ambiente exatos.

Usar o pacote W16 existente, sem rebuild ou alteração de venv, com duas instâncias
descartáveis nesta pasta: `nexus` e `connector`, projeto `project`, porta loopback
**59231**. São tarefas de login do próprio usuário, com supervisor foreground
único, sem RestartOnFailure nativo, sem força. Não são Windows Services de boot.
Antes de qualquer efeito futuro, conferir ausência desses alvos e porta livre;
conflito recusa a seleção, sem escolher outra porta/home silenciosamente.

As tarefas selecionadas são:

- Nexus: `OktoNexus-server-5f463f273e6178366e9050a7e6c2ef4eedd2b148078d620ee81610c7deb7a8b5`
- Connector: `OktoNexus-connector-20cc2017b0e19b944cba1818131b0ef1276af0d7a30ae1a0629a7c70163d834b`

Depois da autorização futura: criar apenas diretórios próprios, instalar e
iniciar cada serviço uma vez e observar READY/armazenamento ou IPC. O Nexus tem
harness integrations desativadas; Connector não recebe identidade. Não haverá
setup, modelo, trabalho, sessão produtiva ou acesso a credencial real. Prontidão
local do Connector não será chamada de vínculo remoto autenticado.

## Sequência proposta

| Evento separado | Ação manual do usuário | Prova posterior mínima |
|---|---|---|
| Suspensão/retorno | Suspender pelo menu do Windows, aguardar aproximadamente 60 segundos e acordar manualmente. | Estado e identidade antes/depois; mesma geração ou mudança explicitada, sem novo trabalho. Não confundir wake com login/reboot. |
| Logout/login | Sair da conta e entrar novamente como o mesmo usuário. | Antes de start/connect manual: observar tarefa, novo logon e owner iniciado pelo gatilho. Registrar separadamente destino/incerteza da geração anterior. Cobre fatos de T18, T21 e T29, sem um login artificial adicional. |
| Shutdown/retorno | Desligar normalmente, ligar manualmente e fazer login. | Persistência da geração encerrada ou ausência/incompletude honesta; nova disponibilidade não prova drain antigo. Registrar comportamento real de shutdown/Fast Startup sem mudar política do Windows. |
| Reboot/login | Reiniciar pelo menu e fazer login. | Fronteira de reboot, nova geração e leitura dos mesmos dados próprios; resultado próprio, sem transferir aceite para logout ou suspensão. |

Nenhum comando automático de logout, shutdown, reinício ou suspensão foi
incluído. Essas ações podem fechar aplicativos e a sessão desta ferramenta;
documentos pessoais devem estar salvos antes da janela. O usuário pode escolher
somente alguns eventos e os demais permanecem pendentes.

## Observador persistente e retomada

A persistência é dos **registros**, não uma promessa de que um processo de usuário
sobreviva ao evento. O root usa os helpers de observação já qualificados e grava
um `before.json` exclusivo com flush/fsync antes de cada evento. Após retornar,
o usuário reabre a conversa com o caminho desta proposta; o root lê o registro
antes de qualquer ação. `after.json` inclui seu hash e `assessment.json` preserva
o resultado separado de cada evento. Não se instala uma terceira tarefa ou
serviço de observação e não há retomada produtiva automática.

As leituras ficam nos dois alvos: status canônico HTTP/IPC, tarefa e digest exatos,
sessão de logon própria, PID+nascimento+imagem de parent/launcher/runtime, geração,
ciclo e campos permitidos dos recibos. Não exportar logs globais, configuração
pessoal, tokens de instalação, nonce de handshake ou conteúdo de credenciais.
As observações pós-evento têm janela técnica de 180 segundos, a cada 2 segundos,
sem novo start para obter resultado positivo. Não há promessa de preempção de
I/O do SO.

Um HANDLE não pode ser persistido em JSON: depois da perda do observador não
afirmar saída física por handle retido. Novo owner, reconciliação da identidade
antiga e ausência de recibo são fatos distintos. Recibo ausente/incompleto ou
ligado à geração errada permanece UNKNOWN; nunca vira DRAINED por inferência.

## Alcance e limpeza

O plano verifica lifecycle real de sessão e a honestidade sobre interrupção. Não
reivindica sobrevivência de provedor ou reconciliação de trabalho produtivo ativo,
pois não seleciona trabalho. Não acrescenta inferência paga como novo requisito
dos cenários literais. Drain/timeout do CLI já qualificados não serão repetidos
como se comprovassem logout/shutdown externos.

Ao fim, ou na primeira divergência, o root observa a coorte atual, solicita apenas
stop canônico normal e confirma saídas físicas e tarefa inativa antes de
uninstall. Todos os dados/evidências ficam preservados. Se a confirmação faltar,
reter a incerteza e informar o recurso residual; sem force, End Task, kill ou
exclusão de tarefa ativa. Enquanto não houver cleanup, as duas tarefas próprias
continuam habilitadas para os logins selecionados — efeito explícito da janela.

## Autorização futura a apresentar

Apresentar ao usuário os quatro eventos, os dois nomes acima, a janela e a forma
de retorno. Solicitar autorização para instalar/iniciar essas tarefas temporárias,
deixá-las habilitadas durante os eventos escolhidos, observar somente seus dados e
pará-las/removê-las normalmente ao final. O usuário executa pessoalmente as ações
do Windows. Não inclui força, tarefas pessoais, alteração de política de energia,
boot sem login, credenciais ou modelo. A pergunta exata sugerida está no JSON e
**não foi enviada**.

Preparação: leitura de fontes e resolução pura das identidades com consulta ao
token do próprio processo. Nenhuma consulta/mutação do Scheduler, socket, serviço,
modelo ou evento de energia foi feita. Nenhuma nova suíte ou build foi criado.
