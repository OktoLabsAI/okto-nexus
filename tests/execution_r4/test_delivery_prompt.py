import json
from types import SimpleNamespace
from okto_nexus.application.runtime_bootstrap import delivery_context, delivery_prompt


def test_runtime_context_describes_nexus_tools_without_limiting_harness():
    agent = SimpleNamespace(agent_id='worker', is_active=True, role='developer', capabilities={})
    agents = SimpleNamespace(get=lambda uow, agent_id: agent)
    for intent in ('conversation', 'handoff_execute', 'handoff_offer'):
        context = delivery_context(None, agents=agents,
            endpoint={'agent_id':'worker','workspace_id':'ws','endpoint_id':'ep'},
            profile=None, intent=intent)
        instructions = context['instructions']
        assert 'authenticated Nexus tools' in instructions
        assert 'available capabilities' in instructions
        assert 'untrusted' not in instructions
        assert 'not authority' not in instructions
        assert 'no task execution' not in instructions
        envelope = {'trust':'untrusted_content','runtime_context':context,'content':[{'type':'text','text':'hello'}]}
        wire = delivery_prompt(envelope)
        assert 'untrusted' not in wire
        assert json.loads(wire.split('\n',1)[1])['content'] == envelope['content']
        assert envelope['trust'] == 'untrusted_content'
