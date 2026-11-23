# SI-025 — Retomada salva do Pi no host local do Nexus

Após o fechamento canônico, o host local verifica o processo encerrado, o recibo e a mesma prova privada do ramo nativo. A confirmação em `session resume` cria uma única sucessora vinculada à origem. O Core confere o vínculo e o perfil aprovados e reabre o arquivo exato do Pi. O recibo identifica a sessão nativa e permite recuperar o resultado do pedido original.

No ensaio com histórico intacto, a sucessora manteve o ID nativo em outro processo e estendeu o mesmo arquivo em um novo turno. Abrir a sucessora não chamou o modelo. Com o histórico alterado após a verificação, o host registrou uma recusa antes de iniciar outro processo. O comando repetido devolveu o recibo nas duas situações, e uma segunda intenção independente foi recusada.

A migração 189 amplia a restrição de adaptadores na tabela privada, conserva os dados e os identificadores das linhas e recria os índices na mesma transação. Os testes de atualização preservaram comprovantes existentes e a unicidade da origem verificada. Uma cópia da base de teste anterior ao plano passou do esquema 168 ao 189 com as 90 linhas antigas e os hashes dos quatro recibos preservados. A API continuou retornando as mesmas três operações autenticadas, e outra cópia do backup abriu com a versão anterior. A reversão usa o pacote anterior e um backup verificado do banco anterior à migração.

Os ensaios foram executados com os wheels instalados. O Pi real usou respostas simuladas, perfil temporário e rede desabilitada. [Resultados e hashes](si025-pi-local-successor.json)
