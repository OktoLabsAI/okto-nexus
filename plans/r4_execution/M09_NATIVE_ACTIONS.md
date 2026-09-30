# M09 — ações nativas no domínio canônico

## Entrega deste incremento

A rota `POST /v1/runtime/native-actions` executa `context`, `claim` e
`complete` pelos mesmos casos de uso de handoff usados no MCP. A audiência
`nexus-native-session` exige ações `handoff.get`, `handoff.claim` e
`handoff.complete`, respectivamente. Chaves canônicas e capabilities MCP
não autenticam essa rota; `tools/call` não é requisito da audiência nativa.

A migration 082 adiciona `execution_native_actions`. O pedido, seu digest,
o resultado e o efeito de domínio são confirmados na mesma transação. O
factory específico da invocação permite que os casos de uso existentes
participem do UOW externo, sem commit interno e sem compartilhar transações
entre threads/requisições. A autoridade é verificada depois de adquirir a
transação e nos acessos ao domínio.

Repetir o mesmo ID/conteúdo devolve o recibo original após revalidar
autoridade, visibilidade, permissões e geração do claim. Conteúdo conflitante
ou reutilização da chave de claim com outro ID retorna conflito. O ledger
não guarda o segredo da capability. Resposta perdida não emite outro ID
nem autoriza retry automático; o caller recupera o pedido original.

## Paridade de claim e limites

- MCP e ações nativas competem pelo mesmo handoff/epoch. Só um claim vence.
- Uma sessão pode concluir pelo canal nativo o trabalho adquirido via MCP,
  ou concluir por MCP o trabalho adquirido nativamente.
- Um epoch explícito no claim nativo somente reutiliza claim ativo da mesma
  sessão/escopo, sem novo evento de claim ou execução de runtime.
- Payloads fechados impedem substituição de agente, workspace ou credenciais.
  O escopo deve coincidir byte a byte em JSON canônico, incluindo tipos.
- Request e resposta nativos são limitados a 16 KiB. Uma resposta de claim
  excedente desfaz o claim; conteúdo grande exige referência de artefato.
- Replay que contém payload exige propriedade atual do claim e lease não
  expirada, mesmo antes de a expiração oportunista atualizar o banco.
- Falha ao gravar o receipt desfaz claim/conclusão, eventos e notificações.
- Falhas não classificadas conservam resultado incerto e o ID original,
  sem expor a exceção ou credencial na resposta.

Os contratos HTTP, schema e documento consolidado foram atualizados juntos.
O Core não recebe uma segunda implementação do domínio e seu wheel permanece
`0.2.28.dev0`, com SHA-256
`27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c`.

## Evidência e correções

O [manifesto](test_runs_20260930_native_actions.json) registra comandos,
artefatos, hashes, campanhas e tentativas anteriores. Os grupos de testes
se sobrepõem e não devem ser somados como requisitos distintos.

A primeira campanha interrompeu após uma fixture tentar emitir duas
audiências com o mesmo request ID. A segunda expôs um erro do handler:
o código de limite excedido não pertencia ao enum legado. A fixture passou
a usar IDs distintos e o handler passou a usar o código contratual correto.

A revisão após as campanhas amplas encontrou uma lacuna de divulgação no
replay de contexto: visibilidade pública do handoff não autoriza recuperar o
payload de um claim expirado. O teste vermelho reproduziu a lacuna. A
correção verifica a propriedade atual e a validade do claim antes de retornar
um recibo com payload; os casos finais cobrem expiração já materializada e
expiração ainda não materializada. O wheel foi reconstruído após a correção.
As campanhas amplas anteriores e as campanhas finais afetadas são
identificadas separadamente no manifesto.

Nos bytes finais, passaram 51 casos dirigidos de ações nativas/MCP e 77
casos instalados, com sobreposição. As campanhas amplas anteriores à última
correção registraram 186 casos R4, 311 regressões e 191 casos instalados.
Elas permanecem identificadas como anteriores à correção de replay; não são
apresentadas como reexecuções completas da fonte final. A conferência do
pacote final verificou 480 arquivos instalados, incluindo 389 arquivos dos
consumidores comparados com o workspace.

A campanha cobre HTTP nativo real no aplicativo, MCP HTTP, disputa de
claim, modo strict, isolamento, replay/conflito, perda da resposta após
commit, revogação entre autenticação e efeito, JSON inválido e rollback.
Recriar a aplicação e o connection factory recupera o receipt do banco.

## Limites e próximo trabalho

A qualificação do executor e o estado READY são precondições sintéticas;
handoffs existentes são preparados como dados de domínio. Isso não comprova
onboarding completo, runtime nativo de provider nem daemon/embedded pronto.
O teste de recriação da aplicação não equivale a reboot do SO ou kill de
processo durante commit.

O pacote instalado inclui os três assets UI previamente modificados no
workspace; esta campanha não aceita UI nem representa build de release limpo.
Esses assets permanecem fora do commit.

A próxima integração deve implementar o backend dos hosts para a bridge
pública Core, adotar configuração e referências protegidas, compor o caller
no daemon e no owner embedded, e renovar a autoridade corretamente. Também
faltam inbox limitado ao workspace, ferramentas restantes, causalidade
completa, consumo exclusivo das demais superfícies e matriz real de
providers/hosts. Nenhum gate G0–G3, flag de prontidão ou milestone integral
é encerrado por este incremento.
