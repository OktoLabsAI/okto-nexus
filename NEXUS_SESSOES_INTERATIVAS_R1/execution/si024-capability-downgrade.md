# Perda de capacidade no terminal e versões anteriores

Se a conexão com a apresentação cair, o terminal informa que perdeu o acesso à sessão e orienta a conferir o estado no Nexus antes de enviar novamente. Uma confirmação cujo recibo ficou indisponível continua aparecendo como incerta. A revisão de uma apresentação agora consulta o servidor antes de procurar o executável local.

Quando o servidor não oferece a revisão de apresentação ou o catálogo de comandos de sessão, o cliente informa qual recurso está indisponível. A recusa acontece antes da seleção do executável, do pedido de confirmação e do envio de texto. A listagem de sessões continua acessível no servidor anterior testado.

O ensaio com frontend Codex 0.170.0 e app-server 0.157.0 suspendeu a disponibilidade da fila durante a revisão de uma interrupção. O terminal perdeu a permissão de escrita. A confirmação não enviou controle nativo, não pausou a fila e não alterou a entrada já enfileirada. Outro visualizador abriu em leitura durante a indisponibilidade e acompanhou a mesma thread no app-server original. Após o retorno da capacidade, a entrada seguiu pela fila existente. As respostas do modelo foram simuladas em loopback.

Os ensaios de pacote usaram um servidor Nexus 0.3.7 construído a partir do commit `2a0f30fb`, com Core 0.0.14. O Connector 0.0.13 com seu Core 0.0.14 negociou e registrou um executor. O Connector 0.0.14 com Core 0.0.15 diagnosticou `VERSION_INCOMPATIBLE`. A sessão no servidor anterior abriu, enviou e encerrou pelo fluxo que já operava, com um adaptador sintético. Ao consultar o protocolo do Nexus 0.3.8 com Core 0.0.16, ambos os Connectors anteriores sinalizaram a incompatibilidade antes de usar credenciais ou registrar um executor. As 50 regressões passaram no código-fonte e no wheel instalado. [Pacotes e escopo dos ensaios](si024-capability-downgrade.json)

A alteração dispensa migração. Reverter o commit restaura as mensagens anteriores do terminal e preserva filas e recibos. A campanha de compatibilidade continua em aberto. A próxima etapa de integração é provar que o renderer nativo do Pi e o Nexus compartilham o mesmo `AgentSession`.
