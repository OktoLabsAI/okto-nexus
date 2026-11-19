# SI-026 Vincular a reorientação ao turno revisado

O Core registra qual operação iniciou a geração no processo Claude. Um controle revisado leva esse identificador até o adaptador, que compara o alvo com o primeiro turno pendente imediatamente antes da escrita. A associação usada para recuperar o recibo também inclui o alvo. Trocar de alvo invalida a associação sem precisar gravar o texto da mensagem nela.

O reenvio revisado exige a confirmação da interrupção. O adaptador espera a resposta do processo com o identificador do controle e o resultado interrompido do turno original. Quando o turno termina naturalmente, a execução original fica concluída e o reenvio é retido. Uma resposta atrasada, ausente ou incompatível mantém a operação sem reenvio. O Core registra a possibilidade de efeito da primeira escrita e preserva o recibo para consulta.

Os ensaios cobriram a troca de turno depois da verificação do runtime e antes da escrita, a conclusão natural enquanto o pedido de interrupção estava em trânsito, o caminho normal e as falhas já exercitadas no marco anterior. A validação usou um processo real com protocolo Claude simulado, um diário SQLite descartável e zero chamadas a provedores.

O pacote é pré-release de desenvolvimento. A mudança dispensa migração e mantém os esquemas R4. O rollback restaura o pacote anterior no Nexus e no Connector e reverte a alteração do Core. A revisão no painel e a publicação dos dois estágios para o operador continuam em implementação. O terminal nativo e o fluxo remoto permanecem em qualificação. [Dados dos ensaios](si026-claude-reviewed-target.json)
