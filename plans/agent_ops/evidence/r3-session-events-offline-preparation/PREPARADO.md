# Helpers preparados, sem execução real

`workflow.json` contém os argv completos do Python W16 pinado e a ordem finita. O argumento de autorização fica pendente: não foi criado recibo nem enviada pergunta. O usuário executará os eventos do Windows pessoalmente; nenhum comando de energia/logout, força ou provedor existe no helper.

Após seleção futura: prepare, install Nexus/Connector uma vez, initial_start de cada um uma vez e ready. Para cada evento selecionado: before grava JSON durável e imprime BEFORE_DURABLE; só então ocorre a ação manual. O mesmo processo foreground observa seus seis handles por até1800s. Não instala terceiro observador. Após retornar, registrar a ação real e executar after (GET/IPC até180s, sem start), aguardar o observador sobrevivente concluir ou registrar sua perda e executar assess. Os quatro eventos têm arquivos próprios.

A publicação usa `.writing` exclusivo, flush/fsync e rename Windows sem sobrescrita. Um arquivo interrompido fica preservado e impede replay; o observador não trata arquivo parcial como after concluído. Nenhum resultado é automaticamente aceite.

No cleanup, cada stop canônico é único e normal. A prova exige parent/launcher/runtime retidos e saídos, tarefa inativa com mesmo digest e ciclo/identidade preservados antes de uninstall. Mudança de phase running→stopped não é confundida com mudança de identidade. Dados Nexus/estado Connector são comparados antes/depois e preservados. Recibo DRAINED da geração antiga, saída física e owner novo são fatos separados. Ausência, erro ou geração divergente nunca vira DRAINED.

Qualificação final: 29 casos sintéticos PASS, contendo os25 antecedentes; sete imports/assinaturas do pacote instalado confirmados sem invocar APIs Windows. Ruff F e sintaxe passaram. Nenhum serviço, tarefa, evento do SO, modelo ou credencial foi usado. Raw stdout/stderr futuros são privados; não devem ser copiados indiscriminadamente para evidência pública.

O PATH A histórico do plano contém um diretório E/venv inexistente; não há dependência dele: todos os comandos e imagens são absolutos no W16 pinado. O plano original foi preservado. Não há alteração global de ambiente.

`AC14.md` e `ac14-audit.json` delimitam por que estes homes vazios não provam estado de operação/grant conhecido atravessando suspensão e oferecem opção de observação de história terminal real, sem nova inferência paga, em uma janela existente devidamente vinculada.
