# Tentativa de leitor de tela real

O Narrador está instalado no Windows. Não havia processo Narrator/NVDA em
execução na observação inicial. A ponte nativa falhou antes de qualquer ação:
`@oai/sky.list_apps`, sua repetição e `cua.listApps` retornaram native pipe
unavailable/erro2. Nenhum aplicativo ou helper personalizado foi iniciado.

H02 permanece NOT_RUN no nível de fala real. Os anúncios ARIA no DOM continuam
comprovados nas evidências anteriores, sem serem apresentados como consumo por
um leitor de tela real.

O [guia oficial do Narrador](https://support.microsoft.com/en-us/accessibility/windows/narrator/chapter-2-narrator-basics)
documenta **Narrator key+Alt+X** para abrir Speech Recap. Essa é a observação
pretendida depois de restaurar a ponte suportada: duas rajadas de dados
sintéticos na Home devem produzir avisos úteis agrupados, preservando os
rótulos de estado em texto. Não foi capturado áudio, histórico de fala ou
conteúdo de aplicativos pessoais nesta tentativa.

## Sonda manual finita, sem ponte de automação nativa

O runner `manual_probe.py` torna a observação reproduzível sem que o agente
controle janelas ou inicie o Narrador. Ele cria uma Home temporária própria
`nexus-home-r1-at-*`, usa o seed padrão e serve somente HTTP de leitura, com
lifespan/runtime desativado. Duas tarefas/handoffs válidas e respectivos eventos
`handoff.created` são inseridos pelo relógio do próprio runner; não são POSTs da
interface, inferência ou uma alteração de dados reais.

### Procedimento para a pessoa que observará o leitor de tela

1. Leia os passos e prepare/ative o Narrador manualmente **antes** de iniciar o
   runner. O runner não abre, configura ou captura o leitor de tela.
2. No diretório do Nexus, execute:

   ```powershell
   rtk proxy .venv\Scripts\python.exe plans\home_evolution\evidence\pr09-screen-reader-attempt\manual_probe.py
   ```

3. Copie somente a URL loopback impressa no registro `READY` para uma nova aba
   privada. Escolha **Use operational Home**, depois **Orion workspace**. Deixe
   Work state em All states, sem filtros aplicados, sem drawer e sem Pause display.
   Pode deixar o foco no campo de filtro de agente, sem aplicar uma seleção.
4. Mantenha o Chrome **ativo e visível**. Nos padrões atuais, os pulsos ocorrem
   aproximadamente45 e65segundos após `READY`. Aguarde até depois do segundo
   pulso e do agrupamento do aviso — cerca de70segundos — antes de abrir Recap.
   Não minimize a Home nem abra Speech Recap antes: background pode agrupar
   legitimamente os dois fatos em um único aviso na volta.
5. Só então use **tecla Narrador+Alt+X**, conforme o
   [guia oficial](https://support.microsoft.com/en-us/accessibility/windows/narrator/chapter-2-narrator-basics),
   e observe Speech Recap. Informe apenas o texto dos avisos **da Home** e a
   quantidade realmente ouvida/registrada. Se não ouviu, ouviu um só ou ficou
   incerto, esse é o resultado a registrar. Não copie o histórico inteiro,
   clipboard, conteúdo ou nomes de outras janelas/aplicativos.
6. A sonda pede parada em85segundos e reserva até5segundos de drenagem, dentro
   do limite configurado de90. As conexões SSE observam o encerramento; não é
   necessário fechar o Chrome para o servidor sair. Para parar antes, crie um
   arquivo vazio no caminho `stop_file` impresso no `READY`. Os dados sintéticos
   ficam preservados no Temp; não há tarefa de login, serviço Windows ou deploy.

Tempos podem ser alterados com `--first-delay`, `--pulse-gap` e `--duration`.
O segundo pulso é `first-delay + pulse-gap`. O limite nunca aceita duração
maior que90segundos e reserva5segundos finais para drenagem. Os padrões45/65/90
substituem15/30/90: o ensaio mostrou que a preparação do browser podia perder
o primeiro pulso cedo. Essa é uma mudança do protocolo de teste, não do produto.

### Qualificação automática dessa sonda

`manual-dom-result.json` comprova **DOM e HTTP apenas**, com dois IDs de trabalho
novos provenientes dos commits SQLite, dois avisos Home agrupados, foco/seleção
preservados, cinco GETs Home reais e zero POST/provedor. O runner encerrou por
timer com SSE/browser ainda abertos em75,274segundos no ensaio30/50/80; depois
o browser próprio foi fechado. Nenhum Narrador foi iniciado ou ouvido.

`manual_probe-tested-source.txt` preserva o código executado. Depois do ensaio,
somente os defaults dos argumentos foram ampliados para45/65/90, com equivalência
AST do restante do código verificada. A fala real **H02 continua NOT_RUN** até
uma pessoa ou a ponte nativa suportada observar o leitor de tela de verdade.
