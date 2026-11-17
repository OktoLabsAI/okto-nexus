"""Prepare independent external G02 case, no product files or test execution."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'qc14-extra-scenarios'
old = Path(json.loads((PRIOR / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc14b-autoid-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
shutil.copyfile(PRIOR / 'package-ready.json', HERE / 'package-ready.json')
test = root / 'after/tests/quick_connect/test_quick_connect_autoid_race.py'
test.write_text('''"""Explicit new-intent replan after an auto-ID race; fake Test peers only."""
from test_quick_connect_cli import (  # noqa: F401
    checking, first_connection, invoke, isolated_provider_environment, local_setup,
    quick_cli, terminal,
)
from test_quick_connect_extra_scenarios import canonical_snapshot, public_row


def test_g02_explicit_new_intent_replans_auto_id_and_requires_its_own_review(quick_cli, capsys):
    c = quick_cli
    _, _, first = first_connection(c, capsys)
    def base(profile):
        return ['connect', 'codex', 'Logical App', '--profile', profile, '--new-connection',
                '--workspace-id', first['workspace_id'], '--json']
    loser_review = invoke(c, capsys, [*base('auto-loser'), '--plan'])
    winner_review = invoke(c, capsys, [*base('auto-winner'), '--plan'])
    assert loser_review['quick_connect']['proposed_connect_id'] == 'codex-2'
    assert winner_review['quick_connect']['proposed_connect_id'] == 'codex-2'
    assert loser_review['review_revision'] != winner_review['review_revision']
    winner = invoke(c, capsys, [*base('auto-winner'), '--approve', winner_review['review_revision']])
    assert winner['quick_connect']['connect_id'] == 'codex-2'
    first_public = public_row(c, 'codex', first['workspace_id'])
    winner_public = public_row(c, 'codex-2', first['workspace_id'])
    first_profile = (c.home / 'terminal/profiles/first.json').read_bytes()
    winner_profile = (c.home / 'terminal/profiles/auto-winner.json').read_bytes()
    before = canonical_snapshot(c)
    turns = tuple(c.t.turns)
    calls = len(c.t.calls)
    loser = invoke(c, capsys, [*base('auto-loser'), '--approve', loser_review['review_revision']], expected=3)
    assert (loser['code'], loser['message']) == ('CONFLICT', 'The selected project or directory changed. Review it again.'), loser
    assert canonical_snapshot(c) == before and tuple(c.t.turns) == turns
    assert not any(method == 'POST' and path.endswith(('setup:test', 'setup:finish'))
                   for method, path in c.t.calls[calls:])
    retained = (c.home / 'terminal/profiles/auto-loser.json').read_bytes()
    # This is a new explicitly requested intent, not replay/customization of
    # the uncertain original, and does not alter its checkpoint/reservation.
    fresh = invoke(c, capsys, [*base('explicit-fresh-intent'), '--plan'])
    assert fresh['quick_connect']['proposed_connect_id'] == 'codex-3'
    assert fresh['review_revision'] != loser_review['review_revision']
    assert canonical_snapshot(c) == before and tuple(c.t.turns) == turns
    refused = invoke(c, capsys, [*base('explicit-fresh-intent'), '--approve', loser_review['review_revision']], expected=3)
    assert refused['code'] == 'REVIEW_REQUIRED', refused
    assert canonical_snapshot(c) == before and tuple(c.t.turns) == turns
    third = invoke(c, capsys, [*base('explicit-fresh-intent'), '--approve', fresh['review_revision']])
    assert third['quick_connect']['connect_id'] == 'codex-3'
    assert third['workspace_id'] == first['workspace_id'] == winner['workspace_id']
    assert len({first['binding_id'], winner['binding_id'], third['binding_id']}) == 3
    assert len(c.t.turns) == len(turns) + 1
    assert public_row(c, 'codex', first['workspace_id']) == first_public
    assert public_row(c, 'codex-2', first['workspace_id']) == winner_public
    assert (c.home / 'terminal/profiles/first.json').read_bytes() == first_profile
    assert (c.home / 'terminal/profiles/auto-winner.json').read_bytes() == winner_profile
    assert (c.home / 'terminal/profiles/auto-loser.json').read_bytes() == retained
    after = canonical_snapshot(c)
    for table in ('execution_bindings', 'agent_endpoints', 'runtime_execution_grants'):
        assert all(row in after[table] for row in before[table]), table
''', encoding='utf-8')
src = (PRIOR / 'run.py').read_text()
start = src.index('nodes=[')
end = src.index('\nfor label,node in nodes:', start)
src = src[:start] + 'nodes=' + repr([('g02', 'tests/quick_connect/' + test.name + '::test_g02_explicit_new_intent_replans_auto_id_and_requires_its_own_review')]) + src[end:]
(HERE / 'run.py').write_text(src, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), external_test=str(test),
    sha256=hashlib.sha256(test.read_bytes()).hexdigest(), executed=False), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
