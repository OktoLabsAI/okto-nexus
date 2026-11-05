"""Explicit terminal responses conform to the same Core native input grammar."""
import pytest
from nexus_connector_core import native_input_response

from okto_nexus.adapters.inbound.cli.native_input import answer, display_text


def proposal(method, params, *, kind='native_input'):
    return dict(approval_key=dict(canonical_request_id='request', agent_id='agent', session_id='session', kind=kind),
                expires_at='2099-01-01T00:00:00Z', display=dict(method=method, params=params))


@pytest.mark.parametrize('method,params,inputs,expected', [
    ('item/tool/requestUserInput', {'isBlocking': True, 'questions': [dict(id='q', header='Pick', question='Which?', isOther=True,
        options=[dict(label='Blue', description='blue option'), dict(label='Red', description='red option')])]},
        ['yes', '1,0', 'Custom'], {'answers': {'q': {'answers': ['Blue', 'Custom']}}}),
    ('control_request:can_use_tool', {'tool_name': 'AskUserQuestion', 'input': {'questions': [
        dict(question='Which?', header='Pick', options=[dict(label='Blue', description='blue option'),
            dict(label='Red', description='red option')])]}},
        ['yes', '1'], {'answers': {'Which?': 'Blue'}}),
    ('mcpServer/elicitation/request', {'mode': 'form', 'serverName': 'fixture', 'requestedSchema': {'type': 'object',
        'properties': {'count': {'type': 'integer'}, 'enabled': {'type': 'boolean'}, 'text': {'type': 'string'}},
        'required': ['count', 'enabled', 'text']}},
        ['yes', '3', 'false', ''], {'content': {'count': 3, 'enabled': False, 'text': ''}}),
    ('extension_ui_request', {'method': 'confirm', 'title': 'Continue?', 'message': 'Continue this work?'}, ['yes', 'no'], {'confirmed': False}),
    ('extension_ui_request', {'method': 'select', 'title': 'Pick', 'options': ['a', 'b']}, ['yes', '2'], {'value': 'b'}),
])
def test_terminal_input_preserves_explicit_values_and_validates_with_core(monkeypatch, method, params, inputs, expected):
    iterator = iter(inputs)
    monkeypatch.setattr('builtins.input', lambda prompt: next(iterator))
    choice, response = answer(proposal(method, params))
    assert choice == 'approve' and response == expected
    # The same response is consumed by the canonical native contract, not a
    # CLI-specific answer format or a model-text command channel.
    native_input_response({'request_id': 'fixture', 'method': method, 'params': params}, response, approved=True)


@pytest.mark.parametrize('choice,expected', [('yes', ('approve', None)), ('no', ('deny', None)), ('', None), ('cancel', None)])
def test_permission_has_no_default_approval(monkeypatch, choice, expected):
    monkeypatch.setattr('builtins.input', lambda prompt: choice)
    assert answer(proposal('item/commandExecution/requestApproval', {}, kind='native_approval')) == expected


def test_control_sequences_are_presented_as_literal_text():
    rendered = display_text('Result\x1b[2J\rcontinued\x07\nnext')
    assert rendered == 'Result\\u001b[2J\\u000dcontinued\\u0007\nnext'
