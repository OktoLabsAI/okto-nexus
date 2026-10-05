# M02/M03 — Binding público aprovado diretamente pelo operador

Data: 30 de setembro de 2026. Incremento parcial, sem fechamento de milestone
ou gate. Core permanece `0.2.28.dev0`, com o mesmo wheel nos três repos.

## Implementação

`POST /v1/connections/bindings:prepare` aceita o `agent_id_hint` já previsto
quando o principal autenticado é o operador canônico. A autoridade é
revalidada dentro da transação pelo `RuntimeAccessService`, sem compor
registry nativo ou descobrir binários no Server. Agente comum continua
impedido de representar outro sujeito.

A proposta reserva um profile ID para managed, inclui a habilitação no diff
e exige confirmação do operador. Prepare não cria perfil, endpoint, binding,
grant ou processo. Apply pelo mesmo ator compara diff/revisões, identidade do
operador, política do sujeito, realização/configuration digest e inventário.
Cria perfil e endpoint habilitados junto do binding e da auditoria em uma
transação. O perfil canônico usa configuração vazia, sem herança de ambiente;
a configuração técnica aprovada permanece na realização do executor.

Negações explícitas de método não são removidas por prepare/apply. A intenção
de apply é idempotente: replay retorna a visão persistida, sem duplicar
perfil, endpoint ou auditoria. A identidade do sujeito vem da proposta
persistida; não muda para a identidade do operador. Rotação da chave do
operador exige nova proposta para uma aplicação ainda não concluída.

O grant continua explícito pela API existente `/api/v1/harness/grants`, com
ator, endpoint, ações, expiry e budget. O teste demonstra sua emissão após
o binding público, sem semear perfil, endpoint, binding ou grant por SQL.
Não há concessão implícita no apply nem anúncio de runtime pronto.

## Evidência

- Nexus R4: **77 passes**, um aviso de depreciação do TestClient.
- Wheel Nexus instalado, fora dos clones e com `python -I`: **11 passes**
  (oito casos novos e três NS05), mesmo aviso. Há sobreposição com R4.
- Asserções: ator/sujeito, schema público, prepare sem mutação de recursos,
  replay, prova forjada, negação explícita, chave/política/configuração/expiry
  alteradas, rollback por falha de storage, grant separado e autoaprovação
  sem autoridade produtiva.
- Core: campanha instalada **99 passes**, publicada em `9d244cf`; runtime e
  wheel não mudaram. O relatório está no repo Core em
  `plans/implementation/R4_INSTALLED_CAMPAIGN.md`.

Comandos, hashes, resultados e tentativas anteriores estão em
[test_runs_20260930_operator_binding.json](test_runs_20260930_operator_binding.json).
Os arquivos dos pacotes instalados foram comparados byte a byte com os wheels;
o Nexus também foi comparado com a fonte. O primeiro wheel foi recusado por
conter asset obsoleto do cache de build. A reconstrução em diretório novo
passou a comparação. Assets prévios do usuário foram empacotados sem alteração;
isso não constitui aceite do frontend.

## Trabalho restante

Prova delegada de operador (`operator_proof_ref`), reuso de autorização no
self-bind e onboarding UI/CLI continuam pendentes. Abertura inicial com lease,
loop de outbox, owners embedded/daemon e providers reais ainda não foram
exercitados por esta campanha. Attach não foi qualificado. NS03.02 e M03
continuam parciais; a entrada alternativa de teste foi registrada no inventário.

A API legada de grants exige timestamp UTC de largura fixa; a tentativa com
offset ISO retornou `INTERNAL_ERROR`. O teste passou a usar o formato canônico,
e a conversão desse erro de entrada em resposta de validação permanece como
defeito conhecido. Não foi contado como comportamento corrigido.
