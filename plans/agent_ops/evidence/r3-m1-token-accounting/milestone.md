## 2026-11-07 — contabilidade operacional M1

Coletor determinístico preparado e verificado em 40 casos finais: contagem
cumulativa por thread sem duplicação no replay, escopos/epochs/cursors/gaps,
reservas seriais antes de runtime.start, vínculo posterior aos mesmos IDs,
seis reservas globais, recusa em stream aposentado e preventiva de 100 mil.
A rodada anterior de 39 casos e seus inputs foi preservada; não são 79 casos.
As transições são puras; persistência/dispatch pertencem ao controlador.
Não houve HTTP, provider, processo nativo ou acesso a credenciais.

A proposta v6 esclarece o limite operacional aceito: depois de turno terminal,
ao menos uma observação de uso correlacionada e replay atualizado sem gaps,
o valor continua sendo mínimo observado, não contador final/faturado. A
monitoração de threads anteriores continua para atualizações tardias. Ausência
de uso, regressão, gap ou fonte desconhecida impede nova admissão. O schema
nativo não oferece marcador de uso final nem corte atômico, e não se inventa
essa garantia. Mantêm-se 700 mil de tolerância total e preventiva de 100 mil.

O journal privado do setup é uma fonte distinta, sem os campos do scope da
API pública de trabalho. Sua observação e a integração global com reserva,
driver de perda e abort canônico ainda estão em preparação. Este marco não
qualifica M1 nem autoriza conta, inferência ou serviço; nenhum aceite promovido.
Evidência: `plans/agent_ops/evidence/r3-m1-token-accounting/preparation/README.md`.
