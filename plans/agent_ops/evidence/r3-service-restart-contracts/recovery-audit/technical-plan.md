# Caso seguro SVC-T22: restart pending com filho pertencente vivo

Plano aprovado pelo coordenador antes da implementação. Arquivo exclusivo proposto: `tests/execution_r4/test_service_surviving_child.py`. Não alterar produto nem o helper de T23/T24.

1. Reutilizar `RestartServer` de `test_service_restart_contracts.py`, após freeze, e `RemoteProject` de `remote_renewal_helpers.py`: Server real separado, HTTP/WebSocket e Core/DaemonApp reais, homes e identidades de teste descartáveis.
2. Trocar apenas o peer nativo por um Python local com vida finita, iniciado por `process_launch.produce` e `spawn_owned_process(container_id=process_launch.identity.container_id)`, conforme o padrão existente em `capacity_connector_process.py:202–214`. Não modificar policy, Job Object, geração, lease ou ledger para obter sobrevivência.
3. Registrar/observar birth journal, container, operação, claim e slot reais. O filho pertence ao Core no Connector; **não** ao Server. A associação não será inferida apenas de um PID estrangeiro.
4. Admitir uma operação e mantê-la sem terminal. Invocar o CLI real `service restart` com prazo curto. Comprovar retorno pending, mesmo Server PID/generation, child vivo, um open/send e claim/slot ainda retidos. Não chamar isso troca de processo concluída.
5. Publicar terminal e close explicitamente autorizado; confirmar saída física do processo e release pelo Core antes de encerrar os recursos. O pedido de restart que já retornou pending não deve iniciar outra geração sozinho.
6. Cleanup somente dos processos/handles criados pelo teste. Falhas iniciais ficam retidas. Fonte focal primeiro, instalado somente após os dois helpers/testes congelarem sob coordenação do root.

É viável com contratos existentes, sem mudança de produto identificada. Teste não usa provider, serviço pessoal, tarefas do sistema ou credenciais existentes. Não afirma sobrevivência de filho à morte do dono.
