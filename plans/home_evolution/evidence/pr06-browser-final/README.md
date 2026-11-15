# Qualificação visual final

Chrome157 em perfil persistente próprio e descartável: Settings200%, DPR2,
viewport físico1440/720 resultando em720/360CSS px; CSS zoom1 e visual scale1.
Composer, descarte de draft, drawer e retorno de foco foram operados por teclado.
O zoom voltou a100% e o browser próprio foi fechado.

Um título permitido com160 caracteres sem espaços causava scroll1590px em
container360px. `min-w-0` no heading flex permite quebra completa: scroll360px,
título241×140px com os160 caracteres. A captura usa GET controlado sintético.

Falha apenas em External reports agora preserva Work/Results atuais e a ação
de visto do resultado. A requisição interceptada corresponde exatamente ao
attention_id/source_revision/preference_revision do DTO. Results parcial
continua desatualizado e com ação bloqueada. Nenhum POST chegou à fixture.

18 testes focais Node e build integrado passaram. O warning existente de bundle
acima de500kB permanece. As fontes estáticas estão pinadas na qualificação;
o servidor sintético antecede correções posteriores da projeção backend.
Essas provas são UI real, sem inferência, daemon nativo, fala de leitor de tela
ou teste humano de compreensão. Probes anteriores que alteravam a raiz do
envelope, em vez de `data`, não são aceites; somente a rodada final é usada.
