from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
sources = ['src/okto_nexus/application/execution_native_decisions.py',
    'src/okto_nexus/application/attention_authority.py',
    'tests/execution_r4/test_native_decision_provenance.py']
def pin(path):
    data = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))

xml = ET.parse(root/'final.xml')
cases = xml.findall('.//testcase')
bad = [c for c in cases if c.find('failure') is not None or c.find('error') is not None]
assert not bad and cases
record = dict(
    classification='OFFLINE_SOURCE_REGRESSION_PASS_NO_LIVE_ACCEPTANCE',
    sources={p:pin(repo/p) for p in sources},
    evidence={p:pin(root/p) for p in ['final.xml','initial-10pass-1fixture-fail.xml','run_tests.py']},
    tests=dict(passed=len(cases), failures=0, errors=0,
        suites=['test_native_decision_provenance.py','test_native_decisions.py','test_managed_native_decisions.py'],
        initial='10 passed; one fixture SQL referenced nonexistent session_owner_generation; corrected to owner_generation.',
        final_test_import_delta='After collection, fixture imports changed to module aliases for Ruff F811; behavior unchanged; production bytes unchanged.'),
    checks=dict(ruff='PASS tool 7e33de', diff_check='PASS tool 154593',
        peer='finish_reader_cache reviewed both production sources and tests, no remaining blocker',
        root='reviewed production diff and test design; commit authorized conditional on tests'),
    limitations=['No live service, provider, model, credentials or installed wheel mutation.',
        'Legacy plain native decision guards refuse deferred dispatch; no retrospective authority promotion.',
        'No M1 or acceptance promotion; source fix only.'],
)
(root/'qualification.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(dict(tests=len(cases),qualification=pin(root/'qualification.json'))))
