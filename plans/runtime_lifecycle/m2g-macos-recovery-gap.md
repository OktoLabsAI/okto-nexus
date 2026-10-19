# M2g — auditoria da recuperação física no macOS

Data: 2026-10-19. Achado técnico, sem implementação ou qualificação nativa.

O Core já planeja uma identidade `darwin-launchd:*` antes da admissão e cria o
processo por um guardian em um job `launchd`. O guardian valida a coalition,
contém a árvore e emite `proof=D` após uma drenagem comprovada. Essa prova é
enviada apenas pela conexão AF_UNIX ao processo observador. Em
`native/process/recovery.py`, tanto a recuperação por birth record quanto
`recover_launch_container` retornam `UNKNOWN` para `darwin`, mesmo após a
árvore ter sido contida. Logo, um crash do owner após o spawn não tem prova
durável consultável pelo novo owner e a reserva deve continuar incerta. Isso é
seguro, mas não satisfaz a convergência automática pretendida em M2.

O fechamento de M2 no macOS requer persistir uma prova de parada ligada à
identidade planejada, somente após o guardian confirmar a drenagem completa;
o novo owner deve ler essa prova sob o producer fence. Ausência, arquivo
inválido ou falha de gravação permanecem `UNKNOWN`, sem liberar capacidade.
Qualificar as fronteiras de crash antes do guardian, após spawn e após birth
em um host macOS com sessão `gui/<uid>` suportada. Os testes portáteis atuais
do Core não substituem essa execução nativa. Não alterar o comportamento
global do Nexus com base apenas nesta auditoria.
