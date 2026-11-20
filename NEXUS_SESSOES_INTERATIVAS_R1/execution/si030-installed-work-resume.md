# Recuperação de um envio incerto com o CLI instalado

O ensaio abriu duas sessões Pi do mesmo agente, no mesmo projeto, com processos distintos. O executável instalado enviou uma mensagem para a sessão mais antiga por ID explícito. O servidor admitiu `turn.submit` e devolveu HTTP 202. A fixture interrompeu a resposta antes do corpo, e o CLI registrou o envio como incerto. O checkpoint reteve a intenção, a operação e a sessão sem guardar o texto.

`work resume` no Windows ConPTY recuperou o recibo enquanto o turno ainda executava. A repetição com `--json`, depois do resultado, devolveu a mesma operação em `SUCCEEDED`. Nas duas chamadas, o CLI apenas consultou a API. O Pi recebeu um único `prompt` e o SQLite confirmou um único resultado na sessão original, sem anexações ou operações na sessão irmã além da abertura e do fechamento do próprio ensaio. [Dados e hashes](si030-installed-work-resume.json)

Passaram a integração instalada e oito regressões focais. O Pi 0.87.1 usou uma resposta determinística com rede externa bloqueada. A prova usa o formato 1 do checkpoint no pacote 0.3.8 e cobre a perda da resposta após a admissão. As regressões focais cobrem também a perda da resolução e a ausência de uma intenção durável. Ambas as sessões foram fechadas pelo fluxo canônico.

O marco registra evidências e corrige o SHA de referência da abertura vazia. O rollback consiste em reverter o commit de evidências.
