# Eventos manuais do Windows com o histórico real do M1

Preparação somente. Este suplemento usa os homes efetivos da campanha B: `campaign/nexus-home` e `campaign/connector-state`, com o pacote instalado em R. Substitui a limitação dos homes vazios de E sem alterar E, seus testes ou seus recibos. O runner contém apenas observação; não implementa start, stop, upgrade, suspensão, logout, reboot, setup, connect ou inferência.

## Situação de preparação

Nexus parado segundo o fechamento retido pelo root. Connector PID39640/generation `fbc0042be355e83da5bb695a64de4910` ainda estava `DRAINING_PENDING` quando esta proposta foi criada. Não se infere saída pelo timeout do observador. O root só prepara os serviços depois da prova física real dessa coorte. Autorização e seleção de eventual força pertencem à proposta específica existente; este suplemento não as amplia.

`history-current.json` é uma projeção SQL somente leitura, realizada agora em 11 bancos próprios. Não prova prontidão, fechamento ou ocorrência de evento Windows. Ela registra operações e recibos reais, sessões/leases, grants, claims, slots e watermarks. Não lê payloads, chaves, vault, operator-auth.db, configurações pessoais nem conteúdo do provedor. Cada banco é lido em transação separada: não há atomicidade global presumida.

## Preparação dos serviços pelo root

Depois do fechamento real pendente, manter os mesmos homes, identidade, grants e histórico. O pacote atual e a definição de cada tarefa estão identificados no `plan.json`; não há reinstalação ou upgrade implícito. Se for escolhido outro pacote/definição antes da campanha, revisar somente essas referências concretas. Não reutilizar start, seleção ou watcher já consumidos. O root seleciona uma nova inicialização canônica dos serviços existentes, sem trabalho, e confirma READY nas duas coortes. O `before` faz sua própria captura dos seis handles e exige os mesmos homes/tarefas/imagens.

Nenhuma nova aprovação artificial é exigida pelo script. A janela manual precisa ser combinada com o usuário, porque logout/reboot encerra aplicativos e pode interromper esta conversa. Salvar documentos abertos antes da janela. O observador pode morrer no logout: os arquivos anteriores são duráveis, mas isso nunca vira prova de saída física.

## Sequência concreta

Python de todos os comandos: `C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t/package/venv/Scripts/python.exe`.
Script: `C:/Users/jpamb/AppData/Local/Temp/r3-session-current-history-w6d7vl5_/observe.py`.

1. Após preparo explícito dos serviços e janela combinada, o root executa `rtk proxy <Python> -I -B -X utf8 <script> before --event 01-suspend-resume`. Aguardar `BEFORE_DURABLE_READY_FOR_MANUAL_EVENT`; o mesmo processo fica observando os handles por até 1800s.
2. O usuário escolhe **Iniciar → Energia → Suspender**, depois acorda o computador. Nenhum comando automático de energia será enviado. Não executar `connect`, `start` ou trabalho entre as duas observações.
3. Registrar apenas fatos efetivamente ocorridos em `actual-suspend.json`: formato abaixo. Então `rtk proxy <Python> -I -B -X utf8 <script> after --event 01-suspend-resume --actual-marker <arquivo-real>` e `... assess --event 01-suspend-resume`.
4. Em janela combinada, repetir `before` com `02-sign-out-logon`. O usuário usa **Iniciar → sua conta → Sair**, e entra novamente na mesma conta Windows. Não iniciar manualmente serviços nem abrir `connect` para disfarçar uma falha do gatilho de login. Depois de retomar a conversa, executar `after`/`assess` com esse ID e marcador real separado.
5. **Shutdown/power-on** (`03-shutdown-power-on-logon`) e **Restart** (`04-restart-logon`) são campanhas distintas. Se selecionadas para a janela, repetir o mesmo before/manual/after/assess; usuário escolhe Desligar e liga novamente, ou Reiniciar, respectivamente. Não apresentar suspensão ou logout como prova de reboot. Fast Startup pode preservar o boot marker no shutdown; registrar o fato e não inferir cold boot.
6. Ao final, o root seleciona cleanup canônico normal das coortes atuais e prova suas saídas antes de remover a integração temporária, preservando dados. Nenhuma decisão de cleanup é implementada neste observer.

Exemplo estrutural do marcador, que **não é recibo real**:

```json
{
  "event_id": "01-suspend-resume",
  "action": "sleep-wake",
  "performed_by_user": true,
  "no_manual_start_or_connect": true,
  "source_reference": "referência ao relato real do usuário e observação do root",
  "started_utc": "<instante real com timezone>",
  "completed_utc": "<instante real com timezone>"
}
```

Para os demais IDs, `action` é `sign-out-sign-in`, `shutdown-power-on-sign-in` ou `restart-sign-in`. Não criar marcadores antes das ações reais.

## Leitura do resultado

O before/after usa as funções E já qualificadas para PID/birth/imagem, geração/ciclo, Scheduler exato, identidade da sessão Windows, horário de login e boot marker. Os dados reais novos são avaliados separadamente: mesma história não significa todos os trabalhos settled, e novo owner READY não significa que o antigo terminou em DRAINED.

`HISTORY_UNCHANGED` exige igualdade dos metadados allowlisted em todas as tabelas/bancos: sem novo operation/action, reset/extensão de grant, alteração de claim/slot ou avanço inesperado de stream. Qualquer mudança é retida como `CHANGES_REQUIRE_CANONICAL_RECONCILIATION`; o helper não repara, reseta, repete ou admite trabalho. Recebimento tardio legítimo pode mudar metadados e deve ser explicado pelo fato canônico, sem promover automaticamente aceite.

SVC18 ganha evidência de login real apenas se houver correlação do novo logon, gatilho/tarefa e nova coorte, sem start manual. SVC21 retém a incerteza de logout/shutdown; ausência de recibo DRAINED permanece UNKNOWN. SVC29 mantém as quatro campanhas distintas. AC13/AC14 continuam sujeitos aos predicados fixos e evidências combinadas: esta campanha observa **histórico real sem nova admissão**, não sobrevivência de trabalho ativo. Os testes T22/T23/T24 retidos cobrem os cortes próprios de autoridade/claim/filho ativo; não são reexecutados nem confundidos com eventos manuais.
