"""Finite source-first operational focal qualification; no provider campaign."""
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'operational-focals'
OUT.mkdir(exist_ok=True)
FILES = (
    'src/okto_nexus/domain/home_entries.py',
    'src/okto_nexus/domain/home_entry_pages.py',
    'src/okto_nexus/domain/home_harness_blocking.py',
    'src/okto_nexus/domain/home_harness_board.py',
    'src/okto_nexus/domain/home_operational_status.py',
    'src/okto_nexus/adapters/outbound/sqlite/home_entries.py',
    'src/okto_nexus/adapters/outbound/sqlite/home_operational_facts.py',
    'tests/home_states/test_operational_status.py',
    'tests/home_states/test_operational_board.py',
    'tests/home_states/test_operational_sqlite.py',
)


def pins():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


before = pins()
command = [sys.executable, '-B', '-m', 'pytest',
    'tests/home_states/test_operational_status.py',
    'tests/home_states/test_operational_board.py',
    'tests/home_states/test_operational_sqlite.py',
    'tests/ui_simplification/test_harness_blocking.py',
    'tests/ui_simplification/test_entry_relations.py::test_sender_filter_keeps_receiver_question_and_results',
    'tests/ui_simplification/test_entry_relations.py::test_historical_session_never_uses_new_binding_context',
    'tests/ui_simplification/test_harness_board.py::test_real_native_input_metadata_and_snooze_preserve_waiting_harness',
    '-q', '--tb=short', '--junitxml=' + str(OUT / 'junit.xml')]
started = datetime.now(timezone.utc).isoformat()
run = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                     encoding='utf-8', errors='replace', timeout=180)
(OUT / 'pytest.txt').write_text(run.stdout + '\n' + run.stderr, encoding='utf-8', newline='\n')
after = pins()
sys.path.insert(0, str(ROOT / 'src'))
okto_nexus = importlib.import_module('okto_nexus')
nexus_connector_core = importlib.import_module('nexus_connector_core')
report = dict(version=1, layer='source-first domain + real SQLite/ASGI HTTP + inert Core native peer',
    command=command, cwd=str(ROOT), python=sys.executable, start=started,
    end=datetime.now(timezone.utc).isoformat(), exit_code=run.returncode,
    imports=dict(nexus=okto_nexus.__file__, core=nexus_connector_core.__file__),
    input_before=before, input_after=after, drift=[p for p in FILES if before[p] != after[p]],
    artifacts={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()},
    limits=['No real native binary/provider/account exercised.', 'No installed-package qualification.',
        'No browser, speech/AT, latency p95, multi-host or paid campaign proof.',
        'Native same-execution causal application/resumption remains unqualified without a producer guarantee.',
        'Confirmed current terminal/independent work is not labelled application of a response.'],
    antecedents=[
        dict(tool='27b3a1', result='1 FAIL', cause='Incorrect oracle: synthetic applied lease can establish control metadata; it cannot establish process presence.'),
        dict(tool='0f10be', result='1 FAIL / 6 PASS', cause='TestClient context tried to start an already-running fixture lifespan on another loop; changed test to existing non-context TestClient pattern.'),
        dict(tool='ddf4c1', result='1 FAIL / 25 PASS', cause='Oracle required runtime-ready from a decision fixture that has no opening receipt; retained as negative case.'),
        dict(tool='b680f4', result='1 FAIL', cause='Same unsupported positive opening oracle; producer source inspection confirmed no wire stream_epoch in open receipt.'),
        dict(tool='8597ff', result='1 FAIL', cause='Diagnostic confirmed opening_stage/native_id absent in that fixture; separate real canonical open with inert peer supplies the positive case.')])
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
print(run.stdout)
print(json.dumps(dict(exit_code=run.returncode, drift=report['drift'], evidence=str(OUT))))
raise SystemExit(run.returncode)
