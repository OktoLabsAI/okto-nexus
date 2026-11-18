# Matriz de capacidades — sessões interativas R1

**Estado deste documento:** referência de inspeção e roteiro de qualificação. Nenhuma combinação foi testada nesta preparação. `observed_in_code` não é `qualified`. O arquivo JSON associado é um template para registrar campanhas por instalação, versão, sistema operacional e modo de sessão.

## 1. O que foi observado no Core consultado

| Capacidade | Codex `codex_app_server` | Pi `pi_rpc` | Claude `claude_stream` |
|---|---|---|---|
| Transporte implementado | JSON-RPC app-server stdio | JSONL RPC stdio, um processo por sessão | stream-json, um processo com vários turnos |
| Entrada nativa de usuário | Caminho de envio já representado | Caminho prompt representado | Linha user estruturada |
| Steer declarado | Imediato, target nativo obrigatório | Fronteira do run atual; sem ID nativo de alvo no contrato | Imediato composto por interrupt + reenvio |
| Restrição importante | Validar expectedTurnId no efeito | Esperar estabilização qualificada, não apenas agent_end | Recusar janela pré-geração; fechamento do stdin encerra processo |
| Interrupt | Controle nativo com targeting | Abort com sinal de estabilização | Control request, com guard de janela segura |
| Fila durável deste plano | A implementar/qualificar pelo Server | A implementar/qualificar pelo Server | A implementar/qualificar pelo Server |
| TUI anexável no baseline | Não comprovada nesta inspeção | Não comprovada nesta inspeção | Não comprovada nesta inspeção |
| Detach de TUI com trabalho contínuo | Não qualificado neste pacote | Não qualificado neste pacote | Não qualificado neste pacote |

Fontes fixadas S09–S12 constam no plano e no ledger. Números de versões de binários mencionados em comentários de adaptador são evidência histórica do projeto, não identificação da instalação presente.

## 2. Caminhos candidatos — não promessas de suporte

**Codex:** a documentação oficial atual descreve frontend remoto e app-server com transports específicos, alguns experimentais. Verificar se a instalação e o schema suportam a seleção do mesmo thread. O gateway deve restringir métodos e sessão; não expor a engine inteira nem permitir um thread novo silencioso. Baseline stdio não ganha attach só por trocar um flag.

**Pi:** conferir SDK, RPC e extension APIs da versão instalada. Uma bridge com um único AgentSession e renderer nativo pode ser necessária. Resume de arquivo é diferente de anexar à sessão viva. Não presumir export específico do SDK sem conferir; não usar scraping/teclas como admissão. dispose/EOF do worker não são detach.

**Claude:** versões atuais documentam background e attach, mas isso não comprova attach ao stream-json `-p` atual. Validar modo de criação/ownership e se a transição mantém ferramentas, aprovações e sessão. Transferir foreground para background não é automaticamente seguro: abortar/recomeçar uma ferramenta para simular continuidade é proibido.

Para cada harness, testar primeiro em ambiente isolado. Se houver incompatibilidade, documentar método/transporte ausente e plano de bridge, em vez de habilitar UI enganosa. Não marcar a meta nativa como cumprida apenas retornando unsupported.

## 3. Registro mínimo de cada campanha

Registrar: adapter ID; versão do harness; hash/fingerprint da instalação; OS/arquitetura; versão/hash Core; versão Server/Connector; local/remoto; modo nativo; estratégia de attach; scope da sessão; native session/thread ID sem segredo; driver/owner epoch; capabilities declaradas/observadas; schema usado; comandos e saídas redigidas; cenário de teste; resultado e limitações.

Não anexar tokens, diretórios de credencial, transcript privado ou banco real. O hash do artefato e a captura redigida precisam ser suficientes para reproduzir o teste sem expor a conta.

## 4. Checklist por combinação

1. Envio ocioso recebe user na sessão correta, sem mensagem de coordenação.
2. Envio ocupado fica em uma única fila e só começa depois da fronteira completa elegível.
3. Steer preserva target e semântica; Claude informa a interrupção composta; Pi distingue ACK de consumo.
4. Interrupt atua no turno selecionado e mantém fila pausada; sessão irmã intacta.
5. Pergunta/aprovação mantém formato, destinatário e autoridade corretos.
6. TUI real abre o mesmo contexto; nenhum fork, --last ou worker duplicado.
7. Fechar janela/cliente/transporte não encerra engine, tool ou fila por causa da apresentação.
8. Reattach mostra continuidade e recupera history/cursor sem replay.
9. UI e TUI não escrevem concorrencialmente fora do árbitro; takeover usa epoch.
10. Comandos suportados têm handlers/efeitos comprovados; native-only/unsupported explicitados.
11. Tentativa de abrir outra sessão/projeto pelo túnel é recusada.
12. Remote mantém processo e credenciais no host; autenticação humana não usa chave de agente.
13. Logs e transporte não vazam tokens/argv de segredo; backpressure não trava a engine.
14. Perda de resposta e restart preservam unknown e não repetem ferramentas.
15. Políticas one-shot/expiry/close continuam explícitas; não adulterar lifecycle para manter a janela.

## 5. Estados e habilitação

`designed`, `observed_in_code`, `implemented`, `qualified`, `unsupported`, `blocked` são estados de capacidade e evidência. Os testes usam NOT_RUN/PASS/FAIL/BLOCKED. A UI só habilita um efeito quando o suporte da instalação, o estado atual e a autorização permitem; falta de permissão não é sinônimo de unsupported.

Campanha Codex Windows não qualifica Pi, Claude, macOS, Linux ou Connector remoto. Atualizar a matriz por combinação. Capacidade que falha em nova versão deve ser recusada com motivo, sem apagar evidências do corte anterior.
