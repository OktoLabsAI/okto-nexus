# SI-036 · Da Home ao terminal de escrita e de volta à mesma sessão

O Connector instalado concluiu `connect --no-interactive` em um projeto descartável. Antes do primeiro envio do navegador, o vínculo estava configurado e o servidor tinha zero sessões, anexações e operações de trabalho. O Edge usou a Home operacional do pacote instalado.

O chat da Home registrou uma mensagem canônica que iniciou um turno no Pi 0.87.1. O navegador abriu a conversa pelo identificador exato devolvido pelo servidor. O editor do CLI anexou à mesma sessão em Windows ConPTY, registrou uma mensagem para o próximo turno e desanexou enquanto a primeira resposta estava em espera. O recibo confirmou a anexação de escrita e o detach. O processo do Pi, sua sessão e a geração do Connector foram preservados.

O Edge recarregou a mesma conversa enquanto a primeira mensagem ainda estava em execução. Após a liberação das respostas simuladas, exibiu o texto da Home, a primeira resposta, a mensagem do terminal e a segunda resposta uma vez cada, nessa ordem. O histórico nativo, os recibos e a base do Nexus confirmaram uma abertura, dois turnos e o fechamento canônico do mesmo processo. [Recibos, artefatos e resultados](si036-pi-browser-writer-roundtrip.json)

A automação passou a fechar a gaveta de envio antes de navegar e a aceitar o aviso de saída ao recarregar a conversa. Os primeiros roteiros também precisaram corrigir a correlação da entrega do chat com a operação do domínio. O ensaio final acompanha os recibos canônicos no banco descartável e verifica a identidade do terminal pelo recibo de anexação e pelo processo do Pi.

Passaram a jornada automatizada com Edge real e 67 testes de regressão do frontend em Node. A jornada usou Connector R4 em loopback e um modelo simulado com rede bloqueada no Pi. SI-T-G09 e SI-T-I07 mantêm as etapas pendentes de campanha. O teste com participante tem seu próprio gate. Este commit de evidências dispensa migração ou reversão de pacote.
