# Uma parada forçada canônica do Connector

Proposta preparada, não executada e ainda sem autorização específica. A autorização anterior da recuperação excluía força; o novo recibo `force-authorization.json` não foi criado.

O stop normal retornou código 4, estado `stopping`. O serviço permanece em drenagem pendente. A ação proposta é **uma única** chamada ao CLI instalado, para o mesmo estado, PID 36068, geração `8b35799e3ae1c6c3feec7cce45ee5162` e ciclo `16bedd50e8807474af5366e08fe39346`:

```text
<R/package/venv/Scripts/python.exe> -I -B -X utf8 -m okto_nexus_connector.cli.main --non-interactive --json --state-dir <B/campaign/connector-state> daemon stop --timeout 45 --force --expected-generation 8b35799e3ae1c6c3feec7cce45ee5162
```

`force-proposal.json` contém os caminhos absolutos e hashes exatos. O helper retém handles somente de consulta/sincronização para parent 41808, launcher 42508 e runtime 36068, verificando nascimento e imagem. Também valida o observador original PID 18564, retido pela sessão root 64647. Task e ciclo precisam permanecer idênticos, o status canônico precisa declarar `force_available=true`, e nenhuma força anterior pode estar marcada.

O efeito autorizado seria solicitar contenção forçada **pelo produto**, uma vez. Não haverá chamada direta a TerminateProcess, encerramento de tarefa pelo SO, remoção de dados, desinstalação, rotação de chave ou inferência. Uma resposta perdida/inconclusiva não permite replay. A conclusão da chamada não prova encerramento: o restart continua condicionado às três saídas físicas e ausência nativa/canônica. Não se afirma settlement de trabalho.

O recibo específico deve conter `status=SPECIFIC_CONNECTOR_FORCE_AUTHORIZED`, o SHA desta proposta, `target` exatamente igual ao da proposta, `max_canonical_force_calls=1`, `force_authorized=true` e a referência à mensagem explícita do usuário. Root revisará o código e solicitará essa autorização; o helper não a cria.

Os recibos antigos permanecem intactos. O campo `force_used=false` do observador original significa apenas que **o observador** não encerrou processos. O novo recibo da ação registrará `force_used=true`; não se reinterpretará a observação antiga como ausência de força na campanha.

Execução futura, somente depois do recibo e revisão:

```text
rtk proxy <R/package/venv/Scripts/python.exe> -I -B -X utf8 <R/connector-consent-restart/force_once.py> --expected-proposal-sha256 c35871e2af447c3532cb51dbc223bdb07a31807242c2abbe7187a88a7bea5a7e --authorization-sha256 <SHA do recibo específico>
```

O wrapper mantém a chamada pendente sem kill/retry; o prazo canônico selecionado é 45 segundos. Root mantém o wrapper e o observador existentes. Nenhuma garantia de encerramento é inferida do prazo.
