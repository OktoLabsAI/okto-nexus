"""Windows permission requests use the existing explicit native decision path."""
from copy import deepcopy

import pytest

from nexus_connector_core import CoreError
from nexus_connector_core.decision_bridge_r4 import native_request_action
from nexus_connector_core.native.adapter_types import RuntimeCommandNotSent
from nexus_connector_core.native.native_inputs import claude_permission_tool_supported
from test_claude_mcp_permissions import connector, _bridge_categories


def params():
    # Claude Code 2.1.323 envelope, synthetic command and IDs; no command runs.
    return {'subtype': 'can_use_tool', 'tool_name': 'PowerShell', 'tool_use_id': 'tool-ps',
            'display_name': 'PowerShell', 'decision_reason_type': 'subcommandResults',
            'description': 'Synthetic reviewed command',
            'input': {'command': "& 'approved.exe' -c 'synthetic'", 'description': 'Synthetic'},
            'permission_suggestions': [{'type': 'addRules', 'behavior': 'allow',
                'destination': 'localSettings',
                'rules': [{'toolName': 'PowerShell', 'ruleContent': 'synthetic'}]}]}


@pytest.mark.parametrize('decision,behavior', [('accept', 'allow'), ('decline', 'deny')])
def test_powershell_waits_for_exact_once_operator_decision(decision, behavior):
    native = connector()
    writes = []
    native._write_json = writes.append
    original = params()
    native._handle_permission_request({'request_id': 'request-ps', 'request': original})
    assert writes == []
    request = native._approval_requests['request-ps']['request']
    assert native_request_action(request) == 'approval.decide'
    # A journal projection is not an instruction to replace the original input.
    projected = deepcopy(request)
    projected['params']['input'] = {'command': '[NATIVE_TEXT_REDACTED]'}
    native.reply_native_approval('session', projected, decision)
    assert len(writes) == 1
    response = writes[0]['response']
    assert response['request_id'] == 'request-ps' and response['subtype'] == 'success'
    answer = response['response']
    assert answer['behavior'] == behavior
    if decision == 'accept':
        assert answer == {'behavior': 'allow', 'updatedInput': original['input']}
    else:
        assert 'updatedInput' not in answer
    assert 'updatedPermissions' not in answer and 'permission_suggestions' not in answer
    with pytest.raises(RuntimeCommandNotSent):
        native.reply_native_approval('session', request, decision)
    assert len(writes) == 1


def test_powershell_is_published_by_real_bridge_as_operator_approval():
    assert _bridge_categories(connector(), [('request-ps', params())]) == [
        ('approval_request', 'turn-operation', True, True)]


@pytest.mark.parametrize('input_value', [None, [], 'command', {}, {'command': None},
    {'command': 1}, {'command': ''}, {'command': '   '}, {'command': 'x' * 17000}])
def test_invalid_or_oversized_powershell_input_is_not_actionable(input_value):
    native = connector()
    writes = []
    native._write_json = writes.append
    value = params()
    value['input'] = input_value
    native._handle_permission_request({'request_id': 'invalid', 'request': value})
    assert not native._approval_requests
    assert writes[0]['response']['subtype'] == 'error'


@pytest.mark.parametrize('change', ['generation', 'turn_ended', 'tool', 'hash', 'session'])
def test_stale_or_forged_powershell_decision_never_reaches_wire(change):
    native = connector()
    writes = []
    native._write_json = writes.append
    native._handle_permission_request({'request_id': 'request-ps', 'request': params()})
    request = deepcopy(native._approval_requests['request-ps']['request'])
    session = 'session'
    if change == 'generation':
        request['local_generation'] += 1
    elif change == 'turn_ended':
        native._approval_turn_active = False
    elif change == 'tool':
        request['params']['tool_name'] = 'Bash'
    elif change == 'hash':
        request['request_hash'] = 'different'
    else:
        session = 'other-session'
    with pytest.raises(RuntimeCommandNotSent):
        native.reply_native_approval(session, request, 'accept')
    assert writes == []


@pytest.mark.parametrize('name', ['powershell', 'PowerShell.exe', 'PowerShell;Bash', True])
def test_only_exact_powershell_tool_name_is_supported(name):
    assert not claude_permission_tool_supported(name)
    value = params()
    value['tool_name'] = name
    with pytest.raises(CoreError):
        native_request_action({'method': 'control_request:can_use_tool',
                               'params': value, 'local_generation': 3})


def test_disabled_native_approvals_do_not_silently_allow_powershell():
    native = connector()
    native.native_approvals_enabled = False
    writes = []
    native._write_json = writes.append
    native._handle_permission_request({'request_id': 'request-ps', 'request': params()})
    assert not native._approval_requests and writes[0]['response']['subtype'] == 'error'
