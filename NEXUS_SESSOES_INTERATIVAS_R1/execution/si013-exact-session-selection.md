# SI-T-A12 — Escolha explícita entre sessões da mesma conexão

O Nexus instalado abriu duas sessões reais do Pi 0.87.1 na mesma
conexão. A Home apresentou as duas no seletor do card. No Edge, o
seletor abriu sem opção escolhida e sem campo de envio. Escolher a sessão
mais antiga abriu o campo de mensagem daquela sessão. Enter enviou um
único pedido HTTP e o Nexus registrou o recibo com o ID escolhido.

O Pi recebeu a mensagem apenas na sessão selecionada. A auditoria
SQLite confirmou dois resultados nessa sessão, contando o turno de
preparação, e zero resultados na sessão irmã. Os dois donos nativos
permaneceram os mesmos até o fechamento canônico de ambas as sessões.
[Relatórios e hashes](si013-exact-session-selection.json)

O provedor e a ferramenta eram fixtures. A primeira abertura do
navegador verificava uma URL com destino de sessão, mas este ensaio
começa na raiz da Home. A segunda abertura ajustou esse filtro e
usou as mesmas duas sessões. O teste cobre Edge no Windows.
O marco dispensa migração. Reverter o commit remove o registro.
