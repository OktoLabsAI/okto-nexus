# Ajuste autorizado: acompanhamento por colunas

Em 2026-11-17, após três percursos de usabilidade, o usuário pediu:

> As tabs Active / Needs you / Results podem ser colunas sempre visiveis com "cards" do que está ocorrendo em cada status

Este ajuste substitui a escolha exclusiva por tabs da implementação R1. Os
arquivos de entrada, SHAs e IDs do plano/ledger original permanecem preservados.
O ledger registra a alteração de escopo em notas, sem reescrever seus cenários.

Há uma única região de acompanhamento com três colunas visíveis. Um trabalho
lógico ocupa um único card, levando consigo conexão, sessões, perguntas,
resultado e arquivos correlacionados. Não há inventários independentes de
harnesses, execuções ou sessões. Conexões/sessões sem operação continuam
alcançáveis como contexto, sem contarem como trabalho RUNNING.

A classificação, contagem e paginação das colunas são responsabilidade do
backend, depois da autorização e correlação do escopo completo. A primeira
leitura deve usar uma UoW e uma revisão do snapshot. Cursors vinculam coluna,
principal, Server, projeto/filtros e revisão; troca de revisão exige revalidar,
sem mesclar páginas incompatíveis. A UI não concatena primeiras páginas de três
fontes para aparentar inventário completo.

Perguntas, aprovações e erros ficam visíveis no básico e no sino global. A
categoria de uma atualização externa não prova execução ou sucesso nativo.
Resultado unseen antigo continua alcançável dentro da retenção; abrir não
marca visto, não aceita entrega e não renova autorização.

Em desktop, as três colunas aparecem lado a lado; em telas estreitas, empilham
sem esconder categorias ou controles. O card de projeto e os resumos familiares
da Home permanecem. Um card abre o registro/sessão exatos em painel contextual,
com rótulo específico, sem selecionar a sessão mais recente por heurística.

O feedback também pede menos ruído e status gráfico claro. Loading acompanha
somente pedidos realmente pendentes. Sucesso aparece apenas após confirmação
canônica; falha conhecida e resultado incerto são distintos. Nenhum indicador
visual autoriza repetir uma execução ou contorna as guardas atuais.

Core, protocolos, Attention, setup e receipts continuam como autoridades. Os
endpoints/URLs anteriores permanecem compatíveis. A preferência de apresentação
e o defaultOFF continuam preservados; este ajuste não é release, deploy ou
ativação padrão. A campanha real continua bloqueada, sem nova chamada paga.

As mudanças se vinculam especialmente a UI-017..UI-028 e UI-029..UI-034. Cenários
anteriores continuam com seus cortes originais; implementação e fixtures não
serão promovidas a qualificação humana/nativa por inferência. A qualificação
do plano permanece em andamento, inclusive o gate obrigatório de múltiplas
conexões local/UI/Connector.
