"""Hash the already reviewed inputs only; no application imports or tests."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
names=[
    'tests/execution_r4/test_canonical_admission_shutdown.py',
    'tests/execution_r4/test_canonical_delivery.py','tests/execution_r4/test_local_realization.py',
    'tests/execution_r4/test_embedded_inventory.py','src/okto_nexus/application/settings.py',
    'src/okto_nexus/config.py','src/okto_nexus/adapters/inbound/http/app.py',
    'src/okto_nexus/adapters/inbound/http/routes.py','tools/ci_installed.py',
    'tests/execution_r4/test_canonical_structured_work.py',
    'tests/execution_r4/test_canonical_native_protocol_regressions.py',
    'tests/execution_r4/test_canonical_handoff_recovery.py',
    'tests/execution_r4/test_canonical_capture_admission.py',
    'src/okto_nexus/bootstrap/embedded_events.py',
    'tests/execution_r4/test_agent_recovery_isolation.py',
    'tests/test_runtime_relay_process_restart.py','tests/runtime_serve_shutdown_fixture.py',
    'tests/execution_r4/test_service_restart_contracts.py','tests/conftest.py',
]
pins={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in names}
prefix=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-0s9w2_3_/venv/Lib/site-packages/nexus_connector_core')
core={str(prefix/name):hashlib.sha256((prefix/name).read_bytes()).hexdigest() for name in ('runtime.py','journal.py')}
report=dict(scope='Read-only source review; proposed tests/fixtures changes are not applied or executed.',
    repository=pins,installed_core=core,proposal_sha256=hashlib.sha256((HERE/'proposal.md').read_bytes()).hexdigest(),
    classification=dict(settings='Confirmed fixture/oracle precondition mismatch; product pin refusal follows its declared contract.',
        late_structured='Concrete duplicate-factory/handshake drift; exact first failure awaits bounded focal trace. No TypeError inference from optional kwargs alone.',
        quota='Separate ACK-durability precondition gap; hypothesis until actual traceback/state.',
        recovery_unavailable='Awaiting exact first failed assertion; no classification without it.'),
    mutations=dict(product=False,tests=False,ci_runner=False,ledger=False,prefix=False),
    test_or_app_processes_started=0,provider_calls=0)
(HERE/'source-pins.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(proposal_sha256=report['proposal_sha256'],source_files=len(pins),core_files=len(core))))
