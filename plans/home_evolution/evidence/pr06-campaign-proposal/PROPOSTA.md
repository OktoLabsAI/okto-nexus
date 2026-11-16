# HOME-033 — proposta de validação local

**Preparação inerte A08 concluída; execução ainda não autorizada.** Candidato
final `6181fd0029f1eb023d226f168f6d00b60baad2cfe92e12b3850592a36fecc189`, wheel
`c1c45e2a3dc8b9f0bed348ddc2d09ab4d0afccbaae2b8c19253fdcaf4980b759`, fonte
`3d95aad8c1b5d2e6354cd872512586fd7a02aec9` e interface `Dcu4bArB`.
O pacote passou Twine e12 testes instalados; os883 payloads do prefixo foram
conferidos no rebind. A tentativa real do driver sem consentimento retornou
`NEW_PAID_CONSENT_REQUIRED` antes de importar produto ou iniciar efeitos.
A pasta da campanha e o recibo de autorização continuam ausentes; há0 reservas.

Este é um rebind técnico da mesma campanha inerte: a cadeia5a8c72→cbb2a45→6181fd
preserva UUID, pasta, porta, IDs, driver, referências à configuração nativa e limites. Apenas
`package` e `technical_rebind` mudaram. Os candidatos e manifests anteriores
ficam preservados como antecedentes; nenhum orçamento ou reserva foi reiniciado.

Proponho validar a Home com o Codex CLI na conta já usada pelo próprio CLI, em uma campanha temporária própria. Serão **no máximo duas chamadas produtivas**: o teste obrigatório de conexão e um pedido pequeno para ler um CSV sintético, calcular quantidade/soma decimal e escrever um relatório com hash verificável. Não haverá terceira chamada de continuação: após encerrar a sessão, verificaremos a recusa de continuar aquele contexto exato.

O limite proposto é **200 mil tokens observados**, com parada preventiva em 150 mil e reserva de 50 mil antes da segunda chamada. A medição pode chegar com atraso; portanto esse limite não é uma trava atômica de cobrança e pode haver ultrapassagem. Uso desconhecido ou incompleto impede nova chamada. Nenhum orçamento ou consentimento de campanhas anteriores será reutilizado.

A campanha usa a pasta `Temp/home-r1-local-codex-bc1d3f18e856`, porta local 62817 e IDs fixos. Criará dados sintéticos, um serviço de usuário temporário e sua tarefa de login, removida no encerramento. O login/configuração nativa existente pode influenciar modelo, MCPs e instruções; não prometemos isolamento dessas configurações nem leremos/coparemos arquivos de autenticação. A conta nativa pode manter seus próprios registros de sessão/cache.

Durante o pedido, observaremos a atividade e o resultado na Home. Se surgir uma pergunta ou permissão nativa real, será revisada pelo operador no alvo exato; não fabricaremos uma pergunta. Também alternaremos a apresentação nova/clássica enquanto o mesmo trabalho permanece ativo. Ramos que não ocorrerem serão registrados como não executados.

A limpeza contempla interrupção canônica do pedido exato quando necessária, parada normal, observação das identidades dos processos e, se indispensável, a força canônica do serviço próprio dentro da autorização já existente para paradas necessárias do Nexus. Dados e evidências ficam preservados. Não encerraremos a sessão do Windows, reiniciaremos o computador ou alteraremos serviços pessoais.

A preparação passou 27 testes offline e revisão independente. Isso não comprova execução real ou sucesso do modelo. A autorização futura será um recibo separado vinculado ao hash do candidato final, sem trocar pasta, IDs ou reiniciar reservas.

O artefato instalado A08 tem qualificação em
`plans/home_evolution/evidence/pr10-package-server-final/qualification.json`.
Os27 testes offline e a revisão anterior continuam evidência do driver
imutável, não uma execução nova do modelo. Comandos atuais estão em
`workflow-server-final.json`; o recibo futuro deve vincular exatamente o candidato
acima. Nenhuma autorização foi criada por esta atualização técnica.
