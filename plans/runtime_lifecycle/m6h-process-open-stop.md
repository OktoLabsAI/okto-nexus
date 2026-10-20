# M6h — parada do Connector durante abertura nativa

Data: 2026-10-20 UTC. Corte do item 5 do ADR M6, com Connector em processo Windows separado e peer nativo determinístico.

O fixture de capacidade já inicia um Nexus HTTP descartável e um Connector `python -I` com Core/Connector instalados. Acrescentei um gate na abertura nativa, após a admissão e reserva reais. O teste inicia o shutdown enquanto a abertura está pendente, observa que a parada permanece aguardando o dono original e que nenhuma instância nativa foi reportada como aberta, libera a abertura e exige a conclusão do shutdown. O processo sai com código zero; o dispatch não ganha uma segunda tentativa. Os três cenários preexistentes de reinício gracioso, reinício abrupto e perda do receipt continuam separados.

Uma primeira versão do teste exigia conclusão em 15 s sem liberar o gate sintético. Ela expirou porque a abertura não podia produzir um resultado; não era prova de falha do produto. O fixture agora oferece `begin_stop` e `finish_stop`, permitindo verificar a espera segura e liberar o gate sem matar o processo. Os quatro cenários passaram juntos com Nexus 0.3.1, Core 0.0.12 e Connector 0.0.10 instalados: **4 passed em 168,20 s**.

Este corte prova a parada durante uma abertura em processo separado, com conclusão após o produtor resolver sua pendência. Não prova o caso de um provider que nunca devolve controle nem substitui os cortes de parada durante publicação, autenticação e upgrade/rollback. A autenticação pendente do named pipe já foi validada em M6c.
