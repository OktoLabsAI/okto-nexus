# PreparaÃ§Ã£o finita do controller M1 v8

**PREPARATION_ONLY_NOT_AUTHORIZED.** Nenhuma aprovaÃ§Ã£o real, serviÃ§o, chamada HTTP,
credencial, processo nativo ou inferÃªncia foi criada/executada por esta preparaÃ§Ã£o.
O predecessor e suas evidÃªncias continuam imutÃ¡veis; seu fault nÃ£o foi removido.

O controller separado comeÃ§a com carry-in fixo de **2 admissÃµes / 45.843 tokens
observados mÃ­nimos**. Permite no mÃ¡ximo **6 novas admissÃµes, 8 cumulativas**.
O limite preventivo **proposto** Ã© 200.000 tokens cumulativos; tolerÃ¢ncia 700.000
e deadline 120 segundos permanecem operacionais, sem garantia atÃ´mica ou de billing.
A soma Ã© sempre carry-in + setup observado + high-water de work observado.
O collector v8 separado mantÃ©m max_requests=6 e stop_at=200000; o controller aplica
o guard cumulativo mais restritivo, inclusive antes de reservar novo trabalho.

## Interface futura, sem execuÃ§Ã£o nesta preparaÃ§Ã£o

```python
Controller(state_path, fresh_campaign_root, create=True,
           approval_path=authorized_receipt_path,
           approval_sha256=authorized_receipt_sha256,
           expected_proposal_sha256=final_approved_proposal_sha256)
```

Sem os trÃªs seletores de aprovaÃ§Ã£o vÃ¡lidos, summary indica V8_APPROVAL_REQUIRED
e setup/work recusam antes de binding/dispatch. O receipt futuro deve conter:

- status: USER_APPROVED; proposal_revision: 8;
- proposal_sha256: exatamente expected_proposal_sha256 (64 hex minÃºsculos);
- policy e ancestry: exatamente os objetos POLICY e ANCESTRY exportados;
- campaign_root: raiz fresh absoluta resolvida; user_quote: consentimento real.

O receipt e o digest esperado sÃ£o entradas de uma orquestraÃ§Ã£o confiÃ¡vel: o mÃ³dulo
nÃ£o autentica uma pessoa por conta prÃ³pria. Os receipts criados pelos testes sÃ£o
explicitamente sintÃ©ticos e nÃ£o autorizam uma campanha. O hash final da proposta
nÃ£o fica embutido no cÃ³digo para evitar dependÃªncia circular.

Retomada usa create=False, mesmo arquivo/raiz e mesmos seletores. O estado formato8
fixa policy, ancestry, autorizaÃ§Ã£o e proposal SHA. AlteraÃ§Ã£o dos limites, carry-in,
raiz ou ancestry Ã© recusada. A escrita mantÃ©m CAS, selo de integridade, reservas,
faults e high-water monotÃ´nicos; create nÃ£o sobrescreve estado existente. NÃ£o hÃ¡
fallback para zero. O selo detecta corrupÃ§Ã£o acidental, nÃ£o Ã© autenticaÃ§Ã£o contra
alguÃ©m que controla e reescreve os arquivos e os hashes.

ANCESTRY referencia closure summary pÃºblica SHA8193dc80... e checkpoint predecessor
SHA78026c0b... informado pelo root. NÃ£o lemos o checkpoint privado. O fault histÃ³rico
CAMPAIGN_RUNNER_EXCEPTION permanece metadata; nÃ£o contamina falsamente o estado
fresh, cuja admissÃ£o depende de uma nova aprovaÃ§Ã£o exata.

## ValidaÃ§Ã£o e limites

15 testes iniciais passaram; apÃ³s review do root, 19 finais passaram em 5,60 s no
Python instalado do freshenv m1-drain-hosts-n7pm3omg. SÃ£o os mesmos 15 mais 4 casos de
snapshot da proposta, sem somar execuÃ§Ãµes como casos distintos. Inputs finais
inalterados. Guards negam socket, subprocess e Windows Credential Manager.

Testes usam transportes fake e a traduÃ§Ã£o pura de eventos do Core instalado.
NÃ£o requalificam setup real, HTTP, polls sob provider ou duraÃ§Ã£o de parada. A rodada
anterior de controller histÃ³rico continua sendo prova separada. A inspeÃ§Ã£o final
de 981 payloads instalados confirma os pins informados pelo root; nÃ£o Ã© uma nova
instalaÃ§Ã£o nem um hash individual coletado antes desta rodada.

Para repetir apenas testes sintÃ©ticos em outro diretÃ³rio de saÃ­da novo:

```powershell
rtk proxy python C:/Users/jpamb/AppData/Local/Temp/m1-controller-v8-bfx9ol3t/run_tests.py another-synthetic-run
```

O diff modifica apenas as cÃ³pias Temp de controller.py e token_collector.py.
setup_journal.py Ã© byte a byte o histÃ³rico. Nenhum checkout foi alterado.
