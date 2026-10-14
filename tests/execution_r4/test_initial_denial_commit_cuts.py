"""Initial denial persistence failures must not strand an entire agent."""
from copy import deepcopy
import json

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_revocation_boundaries import test_revocation_cannot_cross_acquisition_boundary as check_boundary
from test_one_shot_runtime import query


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('failures', [1, 2])
def test_initial_denial_commit_failure_recovers_original_session_without_native_work(runtime, monkeypatch, boundary, failures):
    owner = runtime[0][1].state.embedded_dispatch_owner
    containment = owner.access.session_containment
    fired = []
    requests = []
    issued = []
    original_issue = owner.leases.issue

    def issue(request, **kwargs):
        issued.append(deepcopy(request))
        return original_issue(request, **kwargs)

    monkeypatch.setattr(owner.leases, 'issue', issue)
    target = containment.repository if boundary == 'rollback' else containment
    name = 'record' if boundary == 'rollback' else 'denied'
    original = getattr(target, name)

    def fail_once(*args, **kwargs):
        requests.append(deepcopy(args[1] if boundary == 'rollback' else args[0]))
        result = original(*args, **kwargs)
        if len(fired) < failures:
            fired.append(boundary)
            raise OSError('Initial denial persistence cut: ' + boundary)
        return result

    monkeypatch.setattr(target, name, fail_once)
    try:
        check_boundary(runtime, 'grant', 'before_initial_lease')
        assert fired == [boundary] * failures
        assert len(requests) >= failures + 1
        assert len(issued) == 1
        assert all(request == issued[0] for request in requests)
        recorded = query(runtime[0], 'SELECT request_json FROM execution_session_containment')
        assert len(recorded) == 1 and json.loads(recorded[0][0]) == issued[0]
    except BaseException:
        # A failing fixture keeps all journal evidence but must not retry
        # shutdown publication forever and conceal the actual assertion.
        async def preserve_failed_history():
            pass
        owner._publish_shutdown_history = preserve_failed_history
        raise
