"""Processless technical peer loaded by Core's trusted production registry."""
import queue
from nexus_connector_core.native.adapter_types import (
    DispatchGuards, HarnessCapabilities, HarnessEvent, HarnessSession, utc_now_iso,
)

ADAPTER = 'fixture.additional.v1'


class RegisteredPeer:
    instances = []
    binding_contract = 1
    context_contract = None

    def __init__(self, *, command, cwd, env):
        self.closed = False
        self.sent = []
        self.contexts = []
        self.queue = queue.Queue()
        self._dispatch_guards = DispatchGuards()
        self.instances.append(self)

    def start(self, *, owning_agent_id):
        self._launch_guard('registered_start')
        self.session = HarnessSession('registered-' + str(len(self.instances)), ADAPTER,
            owning_agent_id, 'RUNNING', HarnessCapabilities(True, None, False, False, True), utc_now_iso())
        return self.session

    def verify_protocol(self):
        return dict(managed_contract=1, transport_binding_contract=self.binding_contract,
                    context_observation_contract=self.context_contract)

    def observe_context(self, session, envelope):
        self._dispatch_guards.check()
        self.contexts.append(envelope)

    def send(self, session, command):
        self._dispatch_guards.check()
        self.sent.append(command)
        if command.verb == 'end':
            self.close()
        elif command.verb == 'send_turn':
            for kind, phase, payload in (
                ('turn_started', 'started', {}),
                ('output_delta', 'progress', {'delta': 'registered adapter response'}),
                ('turn_completed', 'terminal', {})):
                self.queue.put(HarnessEvent(session.session_id, ADAPTER, kind, kind,
                    utc_now_iso(), payload, operation_id=command.operation_id, delivery_phase=phase,
                    output_text='registered adapter response' if kind == 'output_delta' else None,
                    delivery_outcome='success' if phase == 'terminal' else None))

    def events(self):
        while (item := self.queue.get()) is not None:
            yield item

    def close(self):
        self.closed = True
        self.queue.put(None)
        return 'graceful'

    force_stop = close

    def observe_lifecycle(self, session):
        return {'stop_observed': self.closed}
