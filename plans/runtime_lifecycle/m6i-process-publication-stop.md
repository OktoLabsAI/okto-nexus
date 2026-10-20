# M6i — parada do Connector durante publicação

Data: 2026-10-20 UTC. Segundo corte de parada do item 5 do ADR M6, no mesmo fixture de Nexus HTTP e Connector instalado em processo Windows separado.

O fixture reteve a resposta de um commit durável de `R4PublicationStore.bind`, depois de admitir trabalho e iniciar o consumo pelo Core. Enquanto a publicação estava retida, o shutdown permaneceu pendente. Ao liberar o commit, o processo encerrou com código zero e não houve uma segunda tentativa de dispatch. O teste controla a resolução da obrigação original; não força o encerramento do processo enquanto o armazenamento está bloqueado.

O novo corte passou isolado em 50,55 s. Em seguida, os cinco cenários do fixture passaram juntos em 248,22 s: reinício gracioso, abrupto, perda de receipt, parada durante abertura e parada durante publicação. O peer nativo é determinístico; Nexus, Connector, Core, controle, ledger, publicação e shutdown são os artefatos instalados. Não houve mudança de código de produção neste checkpoint.

Os três cortes de parada do item 5 estão agora cobertos localmente: abertura (M6h), publicação (este checkpoint) e autenticação pendente no named pipe (M6c). Ainda faltam a combinação de revogação/expiração de lease com geração e restart do host, upgrade/rollback e a comparação de disponibilidade/custo para a decisão de adoção.
