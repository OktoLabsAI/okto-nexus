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
