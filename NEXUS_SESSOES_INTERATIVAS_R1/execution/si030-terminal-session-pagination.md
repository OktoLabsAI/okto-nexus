# SI-030 · Catálogo de sessões no terminal

O CLI agora usa a completude do catálogo para decidir se há um único alvo vivo. No pacote anterior, 101 sessões retidas, com uma única sessão elegível, faziam `session attach --json` abrir a pergunta no terminal. Com a correção, o CLI consulta novamente a sessão exata e devolve a exigência de TTY em JSON. Um catálogo ainda incompleto exige `--session-id` antes do attach. [Regressões do CLI](../../tests/session_interaction/test_session_cli.py)

`session list` lê até dez páginas por chamada. Quando há registros adicionais, a saída humana mostra o cursor e o JSON entrega `next_after_session_id`. O comando aceita esse valor em `--after-session-id` para continuar na mesma conexão. O ensaio de 1.001 sessões confirmou que a segunda leitura completou o catálogo sem repetir registros. O cursor é exclusivo da listagem e as leituras continuam filtradas pelo vínculo autorizado.

O caso de 101 registros falhou no wheel anterior e passou com a correção. A primeira rodada no checkout encontrou um Core antigo no ambiente de desenvolvimento. Com os pins atuais em ambientes descartáveis, passaram 93 testes no código-fonte e os mesmos 93 no wheel instalado. O teste de pseudoterminal POSIX foi pulado no Windows. A prova cobre parser, catálogo paginado e respostas da API, sem iniciar harness ou usar provedor. O marco dispensa migração e pode ser revertido pelo commit do Nexus. [Comandos e resultados](si030-terminal-session-pagination.json)

## Revalidação da sessão escolhida

Ao escolher uma sessão da lista, o CLI compara a geração de seu dono e a geração da conexão do executor com a leitura de detalhe. Antes da correção, uma mudança em qualquer um desses valores permitia chegar à revisão do visualizador com o mesmo ID e uma geração diferente. O CLI agora pede que o operador consulte e escolha novamente. A recusa acontece antes da revisão ou emissão de um ticket. A regra vale tanto para a única sessão elegível quanto para a escolha explícita no seletor.

As quatro variações falharam no wheel anterior. Passaram 85 testes no código-fonte e os mesmos 85 no wheel corrigido. O teste POSIX foi pulado no Windows. As mudanças de geração foram simuladas no catálogo. A suíte também exercitou as leituras da API e o broker de anexação. O ajuste dispensa migração e pode ser revertido pelo commit do Nexus. [Comandos e resultados](si030-terminal-session-pagination.json)
