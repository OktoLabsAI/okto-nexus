"""Embedded host's bounded, durable, nonexecuting observation lane.

This uses Core's optional context port, never the R4 execution outbox. A remote
executor cannot claim this capability merely by publishing adapter metadata.
"""
import asyncio
import json

from nexus_connector_core import SessionKey
from nexus_connector_core.models import EffectNotSent

from ..domain.runtime_commands import RuntimeCommandNotSent
from ..errors import OktoNexusError


class EmbeddedContextObserver:
    def __init__(self, owner):
        self.owner = owner
        self.loop = asyncio.get_running_loop()

    async def publish_support(self, runtime, session_id):
        channel = self.owner.channel
        key = SessionKey(channel.server_id, channel.executor_id, session_id)
        supported = runtime.context_observation_supported(key)
        def persist():
            with self.owner.factory.unit_of_work() as uow:
                self.owner.verify(uow=uow)
                uow.connection.execute(
                    'INSERT OR REPLACE INTO execution_context_observers '
                    'SELECT s.server_id,s.executor_id,s.session_id,?,?,?,p.revision,? '
                    'FROM execution_sessions s JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
                    'JOIN agent_endpoints e USING(endpoint_id) JOIN runtime_profiles p USING(profile_id) '
                    'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?',
                    (channel.connection_id, channel.connection_generation,
                     self.owner.inventory.dispatcher.epoch, int(supported),
                     channel.server_id, channel.executor_id, session_id))
        await asyncio.to_thread(persist)

    def execute(self, operation, guard):
        # The synchronous observation worker remains occupied until the actual
        # native call returns, even after its durable timeout becomes unknown.
        future = asyncio.run_coroutine_threadsafe(self._execute(operation, guard), self.loop)
        try:
            return future.result()
        except EffectNotSent as error:
            raise RuntimeCommandNotSent(str(error)) from error

    async def _execute(self, operation, guard):
        owner = self.owner
        key = SessionKey(operation['canonical_server_id'], operation['canonical_executor_id'],
                         operation['runtime_session_id'])
        session = owner.sessions.get(key.session_id)
        if (key.server_id != owner.channel.server_id or key.executor_id != owner.channel.executor_id
                or session is None or session['executor'] is None or owner._stopping.is_set()):
            raise EffectNotSent('Observer session owner changed')
        runtime = await session['executor']._runtime()
        def checked():
            try:
                owner.verify()
                guard()
            except OktoNexusError as error:
                raise EffectNotSent('Observation authority changed') from error
        await runtime.observe_context(key, json.loads(operation['envelope']), guard=checked)
