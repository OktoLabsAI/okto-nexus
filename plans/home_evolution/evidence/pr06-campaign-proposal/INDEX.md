# Candidato final, ainda não autorizado

Entrada de revisão: [PROPOSTA.md](PROPOSTA.md).
Comandos finais: [workflow-final-ui.json](workflow-final-ui.json).
Candidato final: `candidate-final-ui.json`, SHA256
`cbb2a45ba9cc99833b5af881abc8415c4c7d355c436d6e05e8cfab4288fdd6af`.
Wheel: `7e1563622f4becb21cc62b6182cb4683c7546861256c355c16bb9aa78efa87ff`.

`candidate.json`, seu workflow e README original ficam como antecedente do
wheel anterior. O rebind muda apenas package/technical_rebind e preserva UUID,
home, porta, IDs, reservas, orçamento e driver. Não cria uma nova campanha.

Revisão final independente de `/root/v11_preparation`: PASS, sem bloqueador.
Foram conferidos hashes reais do candidato, wheel, Python,883 payloads e7
pins de runtime; comparação do delta contra o candidato anterior; ausência
da pasta da campanha e de autorização. A recusa real sem consentimento foi
preservada, não reexecutada pelo revisor. Nenhum acesso de autenticação,
chamada de provedor ou serviço real ocorreu nessa preparação/revisão.

Uma resposta real do usuário deve autorizar a proposta antes do recibo separado.
O recibo não altera o candidato nem reinicia limites. A autorização já concedida
para paradas necessárias do Nexus cobre a limpeza própria; não será pedida
novamente por mudança de PID. Eventos de sessão do Windows ficam excluídos.
