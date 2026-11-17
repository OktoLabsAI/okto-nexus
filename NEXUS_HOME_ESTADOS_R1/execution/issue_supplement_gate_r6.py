"""Root-reviewed exact additional test closure for the immutable R6 wheel."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
relative = 'tests/home_states/test_results_boundary_completion.py'
pin = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
assert pin == '17e0e923b80e068d6cda05621b76bd4a3e96d3e35e4cf3d36a1c731fe14d7df1'
ready = json.loads((HERE / 'package-hst-r6/READY.json').read_text())
path = HERE / 'installed-supplement-r6/TESTS_READY.json'
assert not path.exists()
report = dict(runtime_source_commit=ready['source_commit'], runtime_wheel_sha256=ready['wheel_sha256'],
    additions={relative: pin}, selections=[relative,
        'tests/execution_r4/test_native_decisions.py::test_question_listing_and_decision_belong_to_originating_interlocutor',
        'tests/execution_r4/test_meta_harness_sessions.py::test_operator_message_and_handoff_sessions_are_scoped[message-private]',
        'tests/execution_r4/test_meta_harness_sessions.py::test_operator_message_and_handoff_sessions_are_scoped[handoff-private]'],
    scope='Six new Results boundaries plus original-recipient denial and canonical private operator message/handoff cases.',
    qualification='NOT_RUN; post-build supplementary test closure, not inherited R5 execution',
    limits=['No source/prefix/helper/TTL changes; only the exact new test file is added.',
            'Historical synthetic read fixtures are not native execution; no provider or human.',
            'Existing private-message/handoff tests use inert native fixtures; broadcast is outside this supplement.'])
path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(status='TESTS_READY_NOT_EXECUTED', path=str(path), new_file_sha256=pin)))
