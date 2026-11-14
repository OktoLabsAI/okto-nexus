Work readiness preflight — qualificação de fonte

Commit46ba5c31: --readiness-timeout explícito em (0,30] permite observar novamente apenas falhas transitórias locais classificadas, com identidade constante e prazo antes do handler. Sem a flag permanece uma inspeção canônica com timeout HTTP original de2s. Não inicia serviço nem repete dispatch.

Os122 testes antecedentes passaram sobre a versão intermediária de default2s total, rejeitada na revisão. Os76 testes finais passaram sobre defaultNone e retry opt-in. As suítes se sobrepõem e não equivalem a198 casos distintos. Fontes e relatórios intermediários estão preservados.

Sem novo wheel instalado, campanha real ou aceite M1. A contagem permanece124/132; limites de inferência e monitor da campanha não mudaram.
