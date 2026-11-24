# Recuperação de um envio incerto com o CLI instalado

O ensaio abriu duas sessões Pi do mesmo agente, no mesmo projeto, com processos distintos. O executável instalado enviou uma mensagem para a sessão mais antiga por ID explícito. O servidor admitiu `turn.submit` e devolveu HTTP 202. A fixture interrompeu a resposta antes do corpo, e o CLI registrou o envio como incerto. O checkpoint reteve a intenção, a operação e a sessão sem guardar o texto.

`work resume` no Windows ConPTY recuperou o recibo enquanto o turno ainda executava. A repetição com `--json`, depois do resultado, devolveu a mesma operação em `SUCCEEDED`. Nas duas chamadas, o CLI apenas consultou a API. O Pi recebeu um único `prompt` e o SQLite confirmou um único resultado na sessão original, sem anexações ou operações na sessão irmã além da abertura e do fechamento do próprio ensaio. [Dados e hashes](si030-installed-work-resume.json)

Passaram a integração instalada e oito regressões focais. O Pi 0.87.1 usou uma resposta determinística com rede externa bloqueada. A prova usa o formato 1 do checkpoint no pacote 0.3.8 e cobre a perda da resposta após a admissão. As regressões focais cobrem também a perda da resolução e a ausência de uma intenção durável. Ambas as sessões foram fechadas pelo fluxo canônico.

O marco registra evidências e corrige o SHA de referência da abertura vazia. O rollback consiste em reverter o commit de evidências.

## Validação do recibo selecionado

A resolução precisa identificar a mesma sessão registrada na solicitação e manter o recibo já confirmado. O envio, a observação e a recuperação verificam esses dados antes de usar a resolução. Se o recibo retornar outra operação ou outro hash, o checkpoint fica intacto para a recuperação seguinte.

O ensaio isolado de API e SQLite abriu duas sessões do mesmo vínculo com peers sintéticos. A fixture alterou apenas a resposta recebida pelo CLI. As três variantes de troca de sessão foram recusadas antes de qualquer nova admissão. Duas variantes de troca do recibo confirmado preservaram o checkpoint e não dispararam outra requisição de escrita. O ajuste dispensa migração e o rollback reverte o commit do Nexus. [Comandos e resultados](si030-installed-work-resume.json)

Os cinco casos reproduziram a falha no wheel anterior e passaram no código e no wheel corrigidos. Na primeira rodada ampla, 125 casos passaram por ambiente. Três casos pararam enquanto a fixture preparava o segundo resultado sintético. A rodada focada usou duas sessões vazias e completou a verificação. Somando as rodadas por caso, passaram 128 testes em cada ambiente. O teste de pseudoterminal POSIX foi pulado no Windows.

## Admissão ao reutilizar uma sessão

Na recuperação de um pedido que reutiliza uma sessão, a API consulta a admissão gravada para a intenção atual antes de incluir o recibo da abertura existente. Enquanto falta essa admissão, `work status` informa que o envio está sem confirmação. `work resume` pode então admitir a intenção original, que já contém a referência do primeiro turno planejado. Se a admissão já aconteceu, o CLI recupera o recibo por leitura.

O ensaio isolado descarta a resposta da resolução, interrompe a requisição de admissão antes de chegar à API ou descarta sua resposta após a gravação. Cada caso conserva a sessão, o processo e a referência do turno original. A mudança usa as tabelas atuais e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si030-installed-work-resume.json)

Os dois casos anteriores à admissão falharam no wheel original. Com a correção, a recuperação fez uma única admissão em cada um desses casos. Quando a resposta se perdeu após a gravação, a recuperação fez só leituras. Passaram sete testes no código-fonte e os mesmos sete no wheel instalado, com um único envio ao peer sintético por caso de recuperação.

## Correlação do primeiro turno após a admissão

Quando a abertura ou reutilização já foi admitida, o CLI mantém o checkpoint pendente até confirmar o primeiro turno. Se essa consulta falhar, `work resume` reconcilia a admissão por leitura. Uma consulta que deixe de devolver a admissão confirmada mantém o checkpoint para nova leitura. A confirmação guarda o ID do turno e impede que a observação use a resposta de outro pedido da mesma sessão.

O checkpoint mantém o formato 1 e grava apenas IDs e estados adicionais de recuperação. A proteção usa a confirmação da operação ou do turno. Um checkpoint antigo que marcou a reutilização como admitida com base na abertura existente ainda pode recuperar a admissão pendente. A mudança dispensa migração e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si030-installed-work-resume.json)

Os dois casos principais falharam no wheel de referência. Na rodada final, passaram 12 testes no código-fonte e os mesmos 12 no wheel instalado. A suíte manteve uma única execução quando a consulta se perdeu após a admissão e recusou a troca para outro turno real da mesma sessão.

## Verificação de IDs passados ao CLI

`work resume` compara `--request-id` com o pedido salvo e `--session-id` com a sessão confirmada pelo recibo original. Uma divergência devolve `WORK_REQUEST_CONFLICT` antes de alterar o checkpoint ou admitir o pedido. Sem essas opções, a recuperação continua usando o checkpoint do perfil.

Nos dois casos novos, a resposta da resolução se perdeu antes da admissão. O wheel anterior admitiu o pedido mesmo com o ID errado. Com a correção, a recusa preservou o checkpoint byte a byte e deixou o executor sem abrir processo ou receber turno. Com os dois IDs corretos, o CLI admitiu a operação original uma vez. A API e o SQLite trabalharam com um peer sintético no Windows. O formato do checkpoint permanece na versão 1. O marco dispensa migração, e o rollback reverte o commit e restaura o wheel anterior. [Comandos e resultados](si030-installed-work-resume.json)

Passaram sete testes focados no código-fonte e 12 no wheel instalado, incluindo retomada sem seletores, recuperação durante a drenagem e perda da resposta antes e depois da admissão. O wheel e a distribuição de código-fonte passaram no `twine check --strict`. A comparação dos 817 arquivos do pacote identificou apenas os dois módulos da correção depois de normalizar as terminações de linha. [Resultados e hashes](si030-installed-work-resume.json)
