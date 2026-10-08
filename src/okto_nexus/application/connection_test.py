"""Short-lived draft checks, isolated from canonical bindings and delivery."""
import asyncio
from dataclasses import asdict
import time
import uuid

from nexus_connector_core import (CloseOperation, CoreError, EventCursor, ExecutionContext,
    HarnessSettings, LaunchIntent, LocalRuntimeCore, OpenOperation, OperationKey, ShutdownPolicy, TurnOperation)
from nexus_connector_core.discovery import selected_fingerprint
from nexus_connector_core.environment import child_environment
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.runtime_bridge import CopiedAdapterFactory

from ..adapters.outbound.execution.core_inventory import resolve_local_installation_selection
from ..adapters.outbound.provider_vault import ProviderVault
from ..bootstrap.execution_authority import build_execution_access
from .execution_local_launch import ProviderSecretResolver
from .execution_local_realizations import _digest, directory_identity, _require_binding_method
from .connection_setup import baseline, conflict, require_operator


class ConnectionTests:
    def __init__(self, deps):
        self.deps = deps
        self.tests = {}
        self.closed = False

    def authorize(self, context, agent_id):
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            access = build_execution_access(self.deps)
            require_operator(access, context, uow, require_feature=True)
            if access.agents.get(uow, agent_id) is None:
                raise conflict('The selected agent is no longer available.')

    def start(self, context, owner, request):
        self.authorize(context, request['agent_id'])
        build_execution_access(self.deps).require_admission('open')
        if self.closed or owner is None:
            raise conflict('The local runtime service is unavailable.')
        # Bounded, idempotent requests. A lost HTTP reply never replays a prompt.
        key = (context.actor_agent_id, request['client_intent_id'])
        digest = _digest(request)
        existing = self.tests.get(key)
        if existing:
            if existing['digest'] != digest:
                raise conflict('This test request has different content.')
            return self.public(existing)
        if any(not entry['task'].done() for entry in self.tests.values()):
            raise conflict('Another connection test is running. Wait for it to finish.')
        if len(self.tests) >= 100:
            expired = [k for k,v in self.tests.items() if v['task'].done() and time.monotonic()-v['created'] > 3600]
            for k in expired:
                del self.tests[k]
            if len(self.tests) >= 100:
                raise conflict('The connection test limit was reached. Try again later.')
        c = request['configuration']
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            if baseline(uow, request['agent_id'], request.get('binding_id')) != request['baseline']:
                raise conflict('The active configuration changed. Reopen Connections to review it.')
            _require_binding_method(uow.connection, subject_agent_id=request['agent_id'], adapter_id=c['adapter_id'])
        candidate = resolve_local_installation_selection(owner.candidates, adapter_id=c['adapter_id'],
            candidate_ref=request['candidate_ref'], expected_inventory_revision=request['inventory_revision'])
        if selected_fingerprint(candidate) != candidate.fingerprint:
            raise conflict('The selected installation changed. Refresh installations.')
        if owner.key.executor_id != request['executor_id']:
            raise conflict('The selected host changed.')
        entry = dict(test_id=request['client_intent_id'], digest=digest, actor=context.actor_agent_id,
            agent=request['agent_id'], stage='Preparing test', details=[], status='running', created=time.monotonic(),
            root=directory_identity(c['workspace_root']), home=directory_identity(c['provider_home']) if c['provider_home'] else None,
            candidate=asdict(candidate))
        entry['task'] = asyncio.create_task(self.run(entry, request, candidate))
        self.tests[key] = entry
        return self.public(entry)

    def public(self, entry):
        return {name: entry[name] for name in ('test_id','status','stage','details')}

    def get(self, context, test_id):
        entry = self.tests.get((context.actor_agent_id, test_id))
        if not entry:
            raise conflict('This test is unavailable. Run a new connection test.')
        self.authorize(context, entry['agent'])
        return entry

    def verified(self, context, request, owner):
        entry = self.get(context, request['client_intent_id'])
        if entry['status'] != 'succeeded' or not entry['task'].done() or entry['digest'] != _digest(request) or time.monotonic()-entry['created'] > 3600:
            raise conflict('Run a successful test of the current configuration before finishing.')
        candidate = resolve_local_installation_selection(owner.candidates,
            adapter_id=request['configuration']['adapter_id'], candidate_ref=request['candidate_ref'],
            expected_inventory_revision=request['inventory_revision'])
        if asdict(candidate) != entry['candidate'] or selected_fingerprint(candidate) != candidate.fingerprint:
            raise conflict('The tested installation changed. Run the connection test again.')
        return entry

    async def run(self, entry, request, candidate):
        runtime = journal = None
        def progress(stage):
            entry['stage'] = stage
            entry['details'].append(stage)
        try:
            c = request['configuration']
            directory = self.deps.config.home_dir / 'connection-tests' / uuid.uuid4().hex
            directory.mkdir(parents=True, exist_ok=False)
            journal = SQLiteJournal(directory / 'journal.db')
            resolver = ProviderSecretResolver(ProviderVault(self.deps.config.home_dir, request['agent_id']))
            async def environment(prepared):
                return await child_environment(prepared, resolver, provider_home=c['provider_home'],
                    trusted_home=c['provider_home'] is not None, secret_bindings=c['secret_bindings'])
            runtime = LocalRuntimeCore(journal, CopiedAdapterFactory(environment),
                candidates={c['adapter_id']:candidate}, workspace_roots={'test':c['workspace_root']}, max_lease_seconds=300)
            context = ExecutionContext('connection-test', 'local', 'draft', request['agent_id'], 'test',
                1,1,1,time.monotonic()+300,frozenset({'runtime.open','turn.submit','runtime.close','turn.interrupt'}))
            from .runtime_policy import harness_mcp_settings
            settings = dict(c['harness_settings'])
            if c['adapter_id'] in ('codex_app_server', 'claude_stream'):
                with self.deps.connection_factory.unit_of_work(write=False) as uow:
                    settings = harness_mcp_settings(uow.connection, request['agent_id'], c['adapter_id'], settings)
            model = settings.pop('model', None)
            progress('Preparing installation and login')
            prepared = await runtime.prepare(LaunchIntent(request['agent_id'], 'test', c['adapter_id'],
                model=model, auth_refs=tuple(sorted(set(c['secret_bindings'].values()))),
                harness_settings=HarnessSettings(**settings)), context)
            async with asyncio.timeout(240):
                progress('Connecting to harness')
                opened = await runtime.open(OpenOperation('open','session','epoch',prepared), context)
                # Core open acknowledges a live session as SUBMITTED; terminal
                # SUCCEEDED is required for the subsequent model turn.
                if opened.stage not in ('SUBMITTED', 'SUCCEEDED'):
                    raise CoreError('CONNECTION_FAILED','test')
                progress('Waiting for a model response')
                await runtime.submit(TurnOperation('turn','session','Reply with exactly NEXUS_CONNECTION_OK.'),context)
                output = ''
                async for event in runtime.events(EventCursor('connection-test','local','session','epoch')):
                    if event.operation_id != 'turn':
                        continue
                    text = event.payload.get('output_text')
                    if isinstance(text, str):
                        output = ((output if event.category != 'text_snapshot' else '') + text)[-8192:]
                    if event.operation_id == 'turn' and event.payload.get('delivery_phase') == 'terminal':
                        receipt = await journal.get_receipt(OperationKey('connection-test','local','turn'))
                        if event.payload.get('delivery_outcome') != 'success' or not receipt or receipt.stage != 'SUCCEEDED':
                            raise CoreError('MODEL_RESPONSE_FAILED','test')
                        if 'NEXUS_CONNECTION_OK' not in output:
                            raise CoreError('UNEXPECTED_MODEL_RESPONSE','test')
                        break
                else:
                    raise CoreError('MODEL_RESPONSE_MISSING','test')
            progress('Closing test session')
            await runtime.close(CloseOperation('close','session'),context)
            shutdown = await runtime.shutdown(ShutdownPolicy(5,5))
            # A successful response is insufficient if cleanup is unconfirmed.
            if any(value not in ('graceful','already_closed','forced') for value in shutdown.session_outcomes.values()):
                raise CoreError('TEST_CLEANUP_PENDING','test')
            entry['status'] = 'succeeded'
            progress('Connection verified')
        except asyncio.CancelledError:
            entry['status'] = 'failed'
            progress('Test canceled')
            raise
        except Exception as exc:
            entry['status'] = 'failed'
            # Native diagnostics can contain credentials; only expose stable codes.
            progress('Connection test failed')
            entry['details'].append(getattr(exc,'code',type(exc).__name__))
        finally:
            if runtime:
                while True:
                    shutdown = await runtime.shutdown(ShutdownPolicy(5,5))
                    if all(value in ('graceful','already_closed','forced') for value in shutdown.session_outcomes.values()):
                        break
                    entry['status'] = 'running'
                    entry['stage'] = 'Waiting for test session cleanup'
                    await asyncio.sleep(1)
                if entry['status'] == 'running':
                    entry['status'] = 'failed'
                    entry['stage'] = 'Test session closed. Run a new test.'
            if journal:
                journal.close()

    async def shutdown(self):
        self.closed = True
        tasks = [entry['task'] for entry in self.tests.values() if not entry['task'].done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
