# Navegação, identidade e teclado — evidência recuperada

Cinco checks reais de browser passaram na fixture SQLite/HTTP própria,
somente leitura. O script completo coincide com o transcript privado da
execução e os oito pins da fixture continuam iguais ao checkout. A execução
original foi reportada em `aebdd5`; a recuperação não a reexecutou.

- A06: resposta GET de A retida e liberada após existir formulário de B não
  mistura trabalho, projeto, conteúdo, identidade DOM, foco ou seleção.
- A05: 403 roteado limpa lista/drawer e back/forward não os restaura. Logout
  roteado desmonta Home/formulário e histórico não reabre dados protegidos.
- F06: modal mantém fundo inerte; Keep editing preserva draft e Discard remove
  antes de trocar projeto/alvo. Um composer novo fica vazio.
- H01: Tab/teclas percorrem filtros, card, drawer, composer e ação de modo;
  Escape/Discard devolvem foco ao card ou ao botão New request.

O único POST de logout foi interceptado no browser: zero mutações no backend,
zero credenciais reais e zero inferência. O draft foi descartado explicitamente
antes de Sign out; não é prova de logout com formulário ainda sujo. O percurso
de teclado não certifica cada controle nativo sensível ou fala de leitor de tela.

O CLI interrompia a apresentação do retorno ao observar beforeunload; o script
guardou os resultados em chave localStorage exclusiva de teste. O handler
aceitou o diálogo e nenhuma interação forçada contornou o modal/guard.

Na recuperação de16/11, PID próprio47624 estava ausente, não havia listener
em57008 nem processo com o comando da fixture própria. O código de saída
original não foi retido e permanece desconhecido. Nenhum processo foi
reiniciado/encerrado e nenhum dado foi removido durante esta revisão.

## Suplemento A06 com contadores explícitos

Uma nova fixture e um browser CLI próprios executaram somente a barreira A→B.
A mostrava14 atividades aguardando e1 resultado; B mostrava1 atividade e0
resultados. Depois de abrir o formulário de B, a resposta real retida de A foi
liberada: os quatro contadores de B permaneceram idênticos, assim como projeto,
trabalho visível, identidade DOM, conteúdo, foco e seleção2–8. Zero mutações.
Ver `a06-counters.json` e `browser_final_identity_counters.js`.

A primeira rodada passou nas asserções, mas o init script acessava localStorage
no about:blank de teardown. Um guard de protocolo foi acrescentado somente ao
teste; a rodada final passou sem esse ruído. A fixture final teve exit0 observado
no handle próprio, o comando de fechamento do browser teve exit0 e seu PID
ficou ausente. Isso não altera o limite sobre o exitcode da execução original.
