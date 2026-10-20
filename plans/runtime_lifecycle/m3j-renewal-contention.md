# M3j — contenção transitória de escrita não derruba o host

## Incidente da geração 71

Em 17/10/2026, às 04:38:22 UTC (01:38:22 local), o host embedded entrou em
contenção após `DB_ERROR: SQLite writer admission timed out`. O traceback
terminava em `EmbeddedAgentRecovery.fail → _state → SqliteUnitOfWork.__enter__`.
As linhas individuais de Pi, Claude e Codex ainda estavam READY, mas o executor
compartilhado estava RECOVERING. A interface confirmou os três nesse estado
após atualizar Agents. O heartbeat continuava avançando: HTTP vivo não provava
que o dispatcher nativo ainda estava disponível.

O registro do primeiro erro dependia da mesma escrita que expirou. Portanto,
não há evidência suficiente para atribuir o primeiro erro exclusivamente à
renovação, nem para identificar o detentor original da fila de escrita. A
renovação transitória reproduziu um caminho que chegava a `agents.fail`; a
propagação da falha secundária de `_state` para contenção global está comprovada
pelo log. As últimas autorizações do Pi ainda eram válidas até 04:39 UTC.

Foram preservados logs, stacks sem variáveis locais e cópias de 271 bancos em
`build/runtime-m3j-live`. O processo 40832, launcher 25092, encerrou normalmente
às 05:05:08 UTC, depois de registrar DRAINED. Não houve término forçado nem
alteração manual de estados/locks. Outra cópia foi feita com o servidor parado
em `build/runtime-m3j-offline`.

## Correção

- Falha transitória ao emitir ou confirmar renovação verifica a propriedade do
  host por leitura e agenda nova tentativa somente dentro da validade existente.
  Depois da expiração, a recuperação se restringe à sessão.
- Se o Core já instalou uma autorização, sua confirmação exata fica retida para
  persistência posterior; não se emite outra autorização por causa do ACK pendente.
- Falha transitória ao gravar estado/diagnóstico de recuperação mantém o agente
  bloqueado no owner e conserva sua obrigação de recuperação. O bloqueio também
  é verificado antes do despacho e da associação durável da operação. Outros
  agentes continuam disponíveis. READY continua exigindo a gravação após as
  provas de contenção e reconciliação.
- A classificação sanitizada do erro original é registrada antes da tentativa
  de gravar seu estado. Falhas permanentes e perda de propriedade continuam
  seguindo a contenção existente.

## Validação

Quatro casos reproduziram a escalada antes da alteração. Os 13 casos específicos
passaram com source. A campanha contra o wheel instalado passou em **43 casos**,
815,17 segundos, `changed_inputs=[]`; `pip check` passou. Inclui timeouts reais
do WriteGate na emissão e confirmação para Codex, Claude e Pi; expiração sem
extensão de prazo; isolamento de publicação, controles e recuperação; novas
conexões locais/remotas; saída normal e término abrupto antes/depois do bind.

Limite da evidência: o subprocesso auxiliar dos três testes de término ainda
inclui `repo/src` em seu PYTHONPATH. O processo principal usa o pacote instalado
e os arquivos permaneceram inalterados. Esses três casos não constituem prova
de instalação isolada do subprocesso; essa limpeza pertence à qualificação M8.

Wheel Nexus 0.3.1:
`9dae54d0f28b55fc3576754a83a129aba26b102126aa1d2137ee90d17f48b571`.
Core instalado: M3h 0.0.12, SHA
`e95a306637c784dedd8e07215e957cfc7f343116bf4517400c5d46bfde605917`.
Connector permanece 0.0.10, SHA
`64f0bb0567dec34d73500981f0bbab43b2a9f78ecda695bd63518127bc4dc25a`.
Os 541/156/98 arquivos instalados foram comparados com os wheels, e as
dependências dos três pacotes foram verificadas. O contrato M3i ainda em
desenvolvimento não foi instalado.

## Instância real

Geração 72, PID 29220, launcher 44848, porta 8202. Codex ficou READY às
05:16:33.456 UTC, Claude às 05:16:33.963 e Pi às 05:16:42.310. Agents mostrou
os três Online. As chamadas abaixo foram enviadas pelo Meta-harness no
workspace Techridy, sem ferramentas nem alterações de arquivos:

| Chamada Pi | Até RUNNING | Até conclusão | Resposta na UI |
| --- | ---: | ---: | --- |
| Durante prontidão inicial | 127,439 s | 137,667 s | M3J_PI_OK |
| Com pool aquecido | 0,569 s | 7,060 s | M3J_PI_WARM_OK |

A primeira chamada aguardou automaticamente a prontidão; seu atraso não é
considerado resolvido. O pool recompôs quatro instâncias e autorizações de
sessões aquecidas chegaram à terceira revisão, sem nova contenção do host.
Não houve nova chamada real ao Codex devido à quota externa já registrada em L5.
Claude também respondeu `M3J_CLAUDE_OK` pelo Meta-harness. A interface mostrou
1/1 ACK nas três mensagens. O retorno do Claude confirma o funcionamento real
independente do Pi; não é uma medição de desempenho do startup frio.

## Pendências mantidas

L10: substituir automaticamente um owner já contido exige join e prova de
liberação; a recuperação inicial atual não faz essa supervisão. L14/M3i:
prontidão e observação independentes por harness, incluindo o atraso inicial
observado neste rollout. A origem da disputa de escrita da geração 71 permanece
sem atribuição conclusiva. O plano completo e os gates UI permanecem abertos.
