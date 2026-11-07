# Auditoria finita das nove tarefas IMPLEMENTED

Base: Nexus `412f47056308782e2a5a1f748be9f59c6fd0bf7a`. Somente leitura; nenhum teste, serviço, provedor ou credencial acessado. Requisitos literais, fontes, casos PASS exatos e hashes estão em `matrix.json` e `input-manifest.json`.

| ID | Recomendação | Evidência ainda necessária / limite |
|---|---|---|
| BASE-06 | IMPLEMENTED | Medir as etapas de primeiro uso útil no harness suportado e contexto escolhidos; preservar os tempos e pré-requisitos reais. Nenhuma nova infraestrutura de lifecycle é pedida. |
| SVC-07 | IMPLEMENTED | Qualificar a cláusula de encerramento externo da linha327 no contexto de gerenciador escolhido, com persistência/estado incerto e reconciliação honestos. O alcance real SVC-T21 permanece aberto. |
| DX-04 | IMPLEMENTED | Exercitar o launcher suportado com perfil isolado, chave sintética existente e mecanismo protegido; observar autenticação do processo real e o negativo sem referência. Cofre pode conter apenas credencial sintética. Um turno pago não é requisito dessa prova. |
| DX-15 | VERIFIED | Nenhuma falta concreta no contrato literal. Retirar M1 inteiro como gate deste contrato de encaminhamento. DX17/18/20 e DX-T39/T40/T43 continuam abertos nos seus próprios alcances; não declarar provider ou serviço registrado qualificado. |
| DX-16 | VERIFIED | Nenhuma falta concreta no contrato literal. Não herdar prontidão de provedor/instalação nova M1 como gate da descoberta/revisão. Manter candidatos sintéticos e ausência de login confirmado declarados. |
| DX-17 | IMPLEMENTED | Percurso real de primeira solicitação/estado/decisão/resultado no harness selecionado, local e via Connector aplicável, reutilizando os controles existentes. Nenhum novo histórico ou protocolo é necessário. |
| DX-08 | IMPLEMENTED | Concluir a campanha já em preparação de handoff com consentimento separado, cliente real, claim e resultado canônicos exatos observados pela fachada. Não presumir PASS enquanto em implementação. |
| DX-18 | IMPLEMENTED | Comprovar instruções/modelo/ferramentas/limites efetivos no processo real lançado pelo serviço e utilidade do preset no trabalho autorizado, sem ampliar permissões ou substituir instruções. |
| DX-20 | IMPLEMENTED | Qualificar DX-T39/T40 e configuração efetiva DX-T43: trabalho, pergunta/permissão representativa, resultado correlacionado e reencontro no terminal sem dashboard/configuração manual. |

DX-15 e DX-16 podem ser reconciliados como contratos VERIFIED sem fechar M1. Os outros sete conservam pendências específicas; nenhum novo defeito de produto foi demonstrado.

412f4705 acrescenta participação/troca dirigida/reconnect de Inspector e FastMCP reais. Não junta ParticipantLaunch/vault nem executa o handoff opcional. Root reportou2/2 fonte em nova campanha, mas a instalação ainda estava rodando na sessão39625; esse resultado não foi promovido nesta matriz.

SVC-T22 prova a parada pendente com filho real; não substitui logout/shutdown externo. DX-T45/T46/T47/T50 e renovação remota já têm contratos próprios qualificados; sua menção genérica como ausência deve ser removida, mantendo T39/T40/T43.

A pendência DX04 não pressupõe inferência paga: exige demonstrar o consumo da credencial pelo cliente suportado real. O launcher atual só aceita Claude/Codex e rejeita generic; os helpers Inspector/FastMCP não podem ser renomeados como esses clientes. As versões nativas previamente documentadas são Claude2.1.317/Codex0.166.0, em modo de protocolo isolado; nenhuma versão nova foi executada.
