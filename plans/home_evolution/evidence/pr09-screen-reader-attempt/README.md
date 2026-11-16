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
