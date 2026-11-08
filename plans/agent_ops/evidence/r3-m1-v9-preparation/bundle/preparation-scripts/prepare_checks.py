"""Write finite pure preparation tests; does not execute them or the campaign."""
from pathlib import Path

ROOT = Path(__file__).parent
DRAFT = ROOT / 'draft'
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-controller-v8-bfx9ol3t/revision-2/public')
test = (OLD / 'test_v8.py').read_text()
test = test.replace("'proposal_revision': 8", "'proposal_revision': 9")
test = test.replace("['reserved_requests'] == 2", "['reserved_requests'] == 3")
test = test.replace("['reserved_requests'] == 8", "['reserved_requests'] == 9")
test = test.replace('V8_APPROVAL_REQUIRED', 'V9_APPROVAL_REQUIRED')
test = test.replace('are_eight_cumulative', 'are_nine_cumulative')
test = test.replace("state['format'] = 1", "state['format'] = 8")
test = test.replace("assert control.data['ancestry']['predecessor_faults'] == ['CAMPAIGN_RUNNER_EXCEPTION']",
                    "assert control.data['ancestry']['predecessor_faults'] == ['SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE']\n"
                    "        assert control.data['ancestry']['prior_ancestry']['predecessor_faults'] == ['CAMPAIGN_RUNNER_EXCEPTION']")
test += '''

def test_previous_v8_receipt_never_authorizes_v9_reservation(tmp_path):
    auth = approval(tmp_path, proposal_revision=8)
    control = Controller(tmp_path / 'controller.json', tmp_path, create=True, **auth)
    try:
        before = control.path.read_bytes()
        with pytest.raises(Refused, match='V9_APPROVAL_REQUIRED'):
            control.work('new', 'local', 'no dispatch')
        assert control.path.read_bytes() == before
        assert control.summary()['reserved_requests'] == 3
        assert control.data['requests'] == {}
    finally:
        control.close()
'''
(DRAFT / 'controller/test_v9.py').write_text(test, encoding='utf-8')
(DRAFT / 'controller/canonical_fixture.py').write_bytes((OLD / 'canonical_fixture.py').read_bytes())
old_install = Path('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/test_timed_install.py')
install_test = old_install.read_text().replace("'revision': 8", "'revision': 9").replace("'proposal_revision': 8", "'proposal_revision': 9").replace('exact_v8_receipt', 'exact_v9_receipt')
# Explicitly hypothetical enabled installer; Popen/run remain forbidden by the
# reused autouse fixture and all outputs are below pytest's synthetic tmp_path.
install_test = install_test.replace("def never_spawn(monkeypatch):\n", "def never_spawn(monkeypatch):\n    monkeypatch.setattr(module, 'FINAL_PINS_BOUND', True)\n")
(DRAFT / 'installation/test_timed_install.py').write_text(install_test, encoding='utf-8')
entry = DRAFT / 'test_entry_guards.py'
text = entry.read_text()
text = text.replace("[('m1_v9_remote_setup.py',['transfer'])]", "[('m1_v9_lifecycle.py',['initialize']),('m1_v9_setup.py',['local']),('m1_v9_work.py',['local','useful']),('m1_v9_remote_setup.py',['transfer'])]")
entry.write_text(text, encoding='utf-8')
print('Pure preparation tests written; no execution.')
