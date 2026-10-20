# M6k — upgrade e rollback do Connector local

Data: 2026-10-20 UTC. Experimento descartável com Nexus 0.3.1/Core 0.0.12 instalado em `127.0.0.1:8204` e o mesmo estado copiado do Connector Pi M6e/M6f. O Nexus global permaneceu parado. O teste usou pacotes locais instalados em ambientes separados: Connector 0.0.9/Core 0.0.11 para rollback e Connector 0.0.10/Core 0.0.12 para a versão corrente. O estado original não foi modificado; o teste operou em `build/runtime-m6d-ui/m6k-state`.

1. O Connector 0.0.9 recusou abrir a cópia em cerca de 3,5 s, com `VERSION_INCOMPATIBLE (state_load): state schema 15 is newer than supported 13; upgrade the connector first`. Não abriu daemon ou sessão. Os 16 arquivos copiados continuaram com os mesmos hashes do estado de origem.
2. O Connector 0.0.10 abriu o mesmo estado em processo separado, alcançou `CONNECTED` para `m6e-pi` e `CONTROL_READY` no servidor na primeira tentativa. Foi encerrado pela CLI `daemon stop` com saída 0.
3. Com oito arquivos de estado e bases de dados registrados por SHA-256, o rollback para 0.0.9 repetiu a mesma recusa explícita. Todos os oito hashes permaneceram idênticos. A nova execução de 0.0.10 voltou a `CONNECTED`/`CONTROL_READY` na primeira tentativa e encerrou normalmente pela CLI.

O corte comprova upgrade com preservação da configuração, recusa segura de rollback incompatível pelo schema persistido e recuperação subsequente do host corrente. Não mede negociação de protocolo entre versões nem compatibilidade retroativa, que não é requisito desta versão. Todos os processos descartáveis foram encerrados; as portas 8202, 8204 e 49841 ficaram sem listener. Resta comparar disponibilidade e custo para a decisão de adoção M6.
