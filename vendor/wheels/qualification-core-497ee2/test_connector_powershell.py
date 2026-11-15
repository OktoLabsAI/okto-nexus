"""Installed Connector/Core forwarding, synthetic native peer; no process/provider."""
import asyncio
import pytest
from nexus_connector_core import RuntimeEvent
from tests.unit.test_r4_execution import execution, selection, operation, observed

@pytest.mark.parametrize('decision', ['accept', 'decline'])
async def test_installed_connector_powershell_decision(execution, decision):
    owner, connection, factory, receipts, opening = execution
    await connection.emit(opening)
    await observed(receipts, owner)
    request = dict(schema_version=1, request_id='powershell-1', request_hash='a'*64, local_generation=0,
        method='control_request:can_use_tool', params={'subtype':'can_use_tool', 'tool_name':'PowerShell',
        'input':{'command':'Write-Output fixture'}, 'tool_use_id':'tool-fixture'})
    await factory.native.events_queue.put(RuntimeEvent(*factory.scope, 0, 'approval',
        request['method'], {'native_approval':request}))
    await asyncio.wait_for(factory.native.observed.wait(), 3)
    payload=dict(canonical_request_id='request',decision_id='decision',decision_revision=1,
        decision=decision,request=request,response_digest=None)
    await connection.emit(operation(opening,'approval.decide',payload))
    receipt=await observed(receipts,owner)
    assert receipt['stage']=='SUBMITTED'
    expected={k:v for k,v in request.items() if k!='schema_version'}
    assert factory.native.decisions==[(expected,decision,None)]
