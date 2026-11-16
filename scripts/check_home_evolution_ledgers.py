"""Check HOME-R1 bookkeeping integrity, never certify implementation behavior."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'plans/home_evolution'


def main():
    execution = json.loads((DIRECTORY/'execution-ledger.json').read_bytes())
    tests = json.loads((DIRECTORY/'test-ledger.json').read_bytes())
    source = (ROOT/execution['plan']).read_bytes()
    assert hashlib.sha256(source).hexdigest() == execution['plan_sha256'] == tests['plan_sha256']
    text = source.decode('utf-8-sig')
    titles = dict(re.findall(r'^#### (HOME-\d{3}) — (.+)$', text, re.M))
    scenarios = dict(re.findall(r'^- \*\*(HOME-T-[A-I]\d{2}) — NOT_RUN:\*\* (.+)$', text, re.M))
    assert len(titles) == 36 and len(scenarios) == 73
    assert set(execution['tasks']) == set(titles)
    assert set(tests['scenarios']) == set(scenarios)
    for key, item in execution['tasks'].items():
        assert item['title'].strip() == titles[key].strip()
        assert item['status'] in {'TODO','IN_PROGRESS','IMPLEMENTED','VERIFIED','BLOCKED'}
        if item['status'] == 'VERIFIED':
            assert item['evidence'] and item['tests'], key
            assert all((ROOT/path).is_file() for path in item['evidence']), key
    for key, item in tests['scenarios'].items():
        assert item['requirement'].strip() == scenarios[key].strip()
        assert item['status'] in {'NOT_RUN','PASS','FAIL','BLOCKED'}
        if item['status'] == 'PASS':
            assert item['evidence'] and item['environment'], key
            assert all((ROOT/path).is_file() for path in item['evidence']), key
    assert len(execution['invariants']) == 10
    print('HOME-R1:36 tasks,73 scenarios,10 invariants; literal IDs/titles and references valid.')
    print('Bookkeeping check only; not campaign, browser or product acceptance.')


if __name__ == '__main__':
    main()
