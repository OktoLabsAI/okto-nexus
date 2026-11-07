"""Prepared installed OBS12 measurement; requires the coordinator's explicit GO.

Synthetic SQLite only. Private homes/DB/WAL/SHM are never evidence. Output contains
timings/counts and package provenance, never SQL, capabilities, proofs or frames.
"""
from collections import Counter
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import sys
import time
import traceback
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
WORKSPACE, AGENT = 'obs12-benchmark-workspace', 'obs12-benchmark-agent'
QUOTAS = dict(observation_source_rate_per_minute=6000, observation_source_burst=1024,
    observation_agent_rate_per_minute=60000, observation_agent_burst=4096,
    observation_installation_rate_per_minute=600000, observation_installation_burst=16384,
    observation_max_sources_per_agent=1024, observation_max_sources=4096,
    observation_max_instances=4096, observation_max_correlation_records=4096,
    observation_max_tokens_per_source=64, observation_max_events=20000,
    observation_max_valid_for_seconds=3600)
_ISOLATION_PREFIXES = (
    'PYTHON', 'PYTEST', 'OKTO_', 'NEXUS_', '_NEXUS_', 'CONNECTOR_',
    'OPENAI_', 'ANTHROPIC_', 'CLAUDE_', 'CODEX_', 'AZURE_', 'AWS_',
    'GOOGLE_', 'GEMINI_', 'GOOGLE_CLOUD_', 'CLOUDSDK_', 'OLLAMA_',
    'COHERE_', 'MISTRAL_', 'TOGETHER_', 'OPENROUTER_', 'XAI_',
    'HUGGINGFACE_', 'HF_', 'LANGCHAIN_', 'LANGSMITH_', 'LITELLM_',
)


def isolate_environment(home):
    """Discard inherited application/provider values without reading or saving them.

    This standalone process never restores the inherited profile. The two names
    HOME and CODEX_HOME are deliberately untouched, never read or repurposed.
    No provider/runtime is started, and every bootstrap also receives --home.
    """
    for name in tuple(os.environ):  # Names only; never iterate .items()/values().
        key = name.upper()
        if key in {'HOME', 'CODEX_HOME'}:
            continue
        if (key.startswith(_ISOLATION_PREFIXES)
                or key in {'API_KEY', 'API_TOKEN', 'AUTH_TOKEN', 'BASE_URL', 'MODEL', 'PROVIDER'}
                or key.endswith(('_API_KEY', '_AUTH_TOKEN', '_ACCESS_TOKEN', '_BASE_URL'))):
            del os.environ[name]
    home = home.resolve()
    profile = home / 'isolated-profile'
    paths = dict(USERPROFILE=profile, APPDATA=profile/'AppData'/'Roaming',
                 LOCALAPPDATA=profile/'AppData'/'Local')
    for name, path in paths.items():
        if not path.resolve().is_relative_to(home):
            raise RuntimeError('Disposable profile escaped its benchmark home')
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def insert(conn, table, **values):
    conn.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')', tuple(values.values()))


def forbidden(*args, **kwargs):
    raise RuntimeError('Forbidden runtime, provider, OS proof, or artifact operation during benchmark')


class NoProcess:
    def __class_getitem__(cls, _):
        return cls  # Preserve import-time Popen[bytes] annotations.

    def __init__(self, *args, **kwargs):
        forbidden()


def package_check(proof):
    import okto_nexus
    import nexus_connector_core
    installed = Path(proof['installed_package']).resolve()
    core_installed = installed.parent / 'nexus_connector_core'
    if Path(sys.executable).resolve() != Path(proof['python']).resolve():
        raise RuntimeError('The qualified installed interpreter is required')
    if Path(okto_nexus.__file__).resolve().parent != installed:
        raise RuntimeError('Product import did not resolve to the qualified installed package')
    if Path(nexus_connector_core.__file__).resolve().parent != core_installed:
        raise RuntimeError('Core import did not resolve to the same qualified venv')
    core_distribution = importlib.metadata.distribution('okto-nexus-connector-core')
    if core_distribution.version != '0.0.14' or Path(core_distribution.locate_file('')).resolve() != installed.parent:
        raise RuntimeError('Core distribution is not the pinned installed version')
    if hashlib.sha256(Path(proof['wheel']).read_bytes()).hexdigest() != proof['wheel_sha256']:
        raise RuntimeError('Wheel bytes changed')
    if hashlib.sha256(Path(proof['core_wheel']).read_bytes()).hexdigest() != proof['core_wheel_sha256']:
        raise RuntimeError('Pinned Core wheel bytes changed')
    for relative, expected in proof['files'].items():
        path = (installed / relative).resolve()
        if not path.is_relative_to(installed) or hashlib.sha256(path.read_bytes()).hexdigest() != expected['installed_sha256']:
            raise RuntimeError('Installed package bytes changed')
    loaded_counts = dict(nexus=0, core=0)
    for name, module in tuple(sys.modules.items()):
        if name == 'okto_nexus' or name.startswith('okto_nexus.'):
            expected_root, group = installed, 'nexus'
        elif name == 'nexus_connector_core' or name.startswith('nexus_connector_core.'):
            expected_root, group = core_installed, 'core'
        else:
            continue
        loaded_counts[group] += 1
        path = getattr(module, '__file__', None)
        if path and not Path(path).resolve().is_relative_to(expected_root):
            raise RuntimeError('A product module escaped the qualified installed package')
        if any(not Path(folder).resolve().is_relative_to(expected_root) for folder in getattr(module, '__path__', ())):
            raise RuntimeError('A product package namespace escaped the qualified venv')
    return dict(wheel_sha256=proof['wheel_sha256'], verified_files=len(proof['files']),
        core_wheel_sha256=proof['core_wheel_sha256'], core_version=core_distribution.version,
        product_imports_only_installed=True, loaded_module_counts=loaded_counts, python_version=sys.version.split()[0])


def error_metadata(error):
    code = getattr(error, 'code', None)
    return dict(type=type(error).__name__, code=code if type(code) is str and len(code) <= 100 else None,
        frames=[dict(filename=Path(frame.f_code.co_filename).name, lineno=lineno, function=frame.f_code.co_name)
                for frame, lineno in list(traceback.walk_tb(error.__traceback__))[-12:]])


class Trace:
    def __init__(self, factory):
        self.active = None
        original = factory.unit_of_work
        @contextmanager
        def wrapped(*args, **kwargs):
            with original(*args, **kwargs) as uow:
                active = self.active
                if active is not None:
                    def count(sql):
                        active[sql.lstrip().split(None, 1)[0].upper() if sql.strip() else 'EMPTY'] += 1
                    uow.connection.set_trace_callback(count)
                try:
                    yield uow
                finally:
                    if active is not None:
                        uow.connection.set_trace_callback(None)
        factory.unit_of_work = wrapped

    def measure(self, call):
        if self.active is not None:
            raise RuntimeError('Measurements cannot overlap')
        self.active = Counter()
        start, cpu = time.perf_counter(), time.process_time()
        try:
            value = call()
            result = dict(ok=True, records=(len(value) if isinstance(value, dict) and 'items' not in value
                and 'total_instances' not in value else len(value.get('items', []))),
                total=value.get('total', value.get('total_instances')))
            if 'items' in value:
                views = [item.get('external_observation', item) for item in value['items']]
                result['canonical_items'] = sum(item.get('canonical_session_ref') is not None for item in views)
            elif 'total_instances' in value:
                result['activity'] = value['activity']
                result['freshness'] = value['freshness']
            elif 'total_instances' not in value:
                result['verified_receipts'] = sum(item.get('last_received_receipt', {}).get('status') == 'verified'
                    for item in value.values() if item.get('last_received_receipt') is not None)
        except Exception as error:
            result = dict(ok=False, error=error_metadata(error))
        finally:
            result.update(elapsed_ms=(time.perf_counter()-start)*1000, cpu_ms=(time.process_time()-cpu)*1000,
                select_or_cte=self.active['SELECT']+self.active['WITH'], statement_classes=dict(self.active))
            self.active = None
        return result


def canonical_fingerprint(factory):
    """Keep row digests only in memory; publish equality and table count, no hashes."""
    result = {}
    with factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for name in names:
            if name.startswith(('observation_', 'attention_')) or name == 'events':
                continue
            digest = hashlib.sha256()
            rows = sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM "'+name+'"')), key=repr)
            for row in rows:
                digest.update(repr(row).encode('utf-8'))
                digest.update(b'\n')
            result[name] = digest.digest()
    return result


def seed_native(deps, count):
    from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
    from okto_nexus.adapters.outbound.sqlite.execution_receipts import append_execution_receipt
    from okto_nexus.adapters.outbound.sqlite.execution_tickets import VerifiedExecutionTicket
    from okto_nexus.application.auth import AgentKeyAuthService
    from nexus_connector_core import R4_PREVIEW_REVISION
    installation = ensure_execution_installation(deps.connection_factory)
    server, executor = installation.server_id, installation.embedded_executor_id
    now, sessions = deps.clock.now_iso(), []
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        deps.repos.workspaces.upsert(uow, workspace_id=WORKSPACE)
        deps.repos.agents.upsert(uow, agent_id=AGENT)
        AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id=AGENT)  # Discard bearer.
        deps.repos.agents.set_permissions(uow, agent_id=AGENT, preset_id=None,
            permissions={'observations':{'manage_self':True, 'publish':True}})
        conn.execute("UPDATE execution_executors SET control_state='CONTROL_READY',generation=7,owner_instance_id='bench-owner' WHERE server_id=? AND executor_id=?", (server, executor))
        insert(conn, 'runtime_profiles', profile_id='bench-profile', adapter_id='fixture', config='{}', created_at=now, updated_at=now)
        for number in range(count):
            suffix = str(number)
            scope = dict(server_id=server, executor_id=executor, session_id='bench-session-'+suffix,
                binding_id='bench-binding-'+suffix, workspace_binding_id='bench-workspace-binding-'+suffix,
                session_owner_generation=3, agent_id=AGENT, workspace_id=WORKSPACE, binding_revision=1)
            ns = {key: scope[key] for key in ('server_id','executor_id')}
            insert(conn, 'agent_endpoints', endpoint_id='bench-endpoint-'+suffix, agent_id=AGENT, workspace_id=WORKSPACE,
                adapter_id='fixture', protocol='nxl-r4', profile_id='bench-profile', enabled=1, activation_state='approved', created_at=now, updated_at=now)
            insert(conn, 'execution_workspace_bindings', **ns, workspace_binding_id=scope['workspace_binding_id'],
                workspace_id=WORKSPACE, realization_handle='fixture', revision=1, status='READY')
            insert(conn, 'execution_realizations', **ns, realization_ref='bench-realization-'+suffix,
                local_realization_ref='bench-local-'+suffix, subject_agent_id=AGENT,
                workspace_binding_id=scope['workspace_binding_id'], candidate_ref='fixture', inventory_revision='fixture',
                configuration_digest='sha256:'+'a'*64, local_root_proof_digest='sha256:'+'b'*64, revision=1, status='READY')
            insert(conn, 'execution_bindings', **ns, binding_id=scope['binding_id'], endpoint_id='bench-endpoint-'+suffix,
                workspace_binding_id=scope['workspace_binding_id'], candidate_ref='fixture', inventory_revision='fixture',
                realization_ref='bench-realization-'+suffix, realization_revision=1, binding_revision=1)
            operation_fields = dict(ns, **{key:scope[key] for key in ('binding_id','workspace_id','workspace_binding_id','session_id')},
                subject_agent_id=AGENT, actor_agent_id=AGENT, intent_hash='sha256:'+'c'*64, semantic_payload='{}',
                expected_revisions_json=json.dumps(scope), admission_state='ACCEPTED', created_at=now)
            opening = 'bench-opening-'+suffix
            insert(conn, 'execution_operations', **operation_fields, operation_id=opening, action='runtime.open')
            insert(conn, 'execution_sessions', **ns, session_id=scope['session_id'], binding_id=scope['binding_id'],
                workspace_id=WORKSPACE, workspace_binding_id=scope['workspace_binding_id'], open_operation_id=opening,
                owner_generation=3, lifecycle_state='READY', stream_epoch='bench-stream-'+suffix, lease_state='ACTIVE')
            lease = 'bench-lease-'+suffix
            insert(conn, 'execution_leases', **ns, session_id=scope['session_id'], lease_serial=1, lease_id=lease,
                grant_id='fixture', allowed_actions_json='["turn.submit"]', authorization_revision=1, configuration_revision=1,
                owner_generation=3, connection_generation=7, credential_epoch=1, valid_until_server='2099-01-01T00:00:00Z',
                request_id='fixture', status='ACTIVE', connection_id='bench-owner', scope_json=json.dumps(scope), applied_at=now)
            principal = VerifiedExecutionTicket('fixture', server, executor, scope['binding_id'], AGENT, frozenset({'receipt:publish'}), 1, 1)
            for operation_no in range(4):
                operation = 'bench-turn-'+suffix+'-'+str(operation_no)
                insert(conn, 'execution_operations', **operation_fields, operation_id=operation, action='turn.submit')
                insert(conn, 'execution_dispatch_outbox', **ns, operation_id=operation, dispatch_state='DISPATCHED', lease_id=lease, lease_serial=1)
                for revision, stage in enumerate(('RECEIVED_DURABLE','RUNNING','SUCCEEDED'), 1):
                    frame = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='operation.receipt', **ns,
                        binding_id=scope['binding_id'], agent_id=AGENT, session_id=scope['session_id'], connection_id='bench-owner',
                        connection_generation=7, operation_id=operation, intent_hash='sha256:'+'c'*64, receipt_revision=revision,
                        stage=stage, possible_effect=revision>1, retry_safe=revision==1)
                    append_execution_receipt(deps.connection_factory, principal=principal, uow=uow, frame=frame)
            sessions.append(dict(scope, open_operation_id=opening, stream_epoch='bench-stream-'+suffix))
    return sessions


def grow(deps, service, operator, sessions, instances, sources, target):
    additions = {}
    proof = dict(kind='local_windows_process_v1', external_binding_provenance='operator_attested_external_binding',
        native_birth_provenance='machine_checked_native_birth', host_id='a'*64, pid=1234,
        creation_filetime=133000000000000000, image_path_sha256='sha256:'+'b'*64, binding_hash='sha256:'+'c'*64)
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        for number in range(len(instances), target):
            group = number//100
            if group not in sources:
                sources[group] = deps.repos.observations.create_source(uow, agent_id=AGENT, source_kind='custom',
                    workspace_ids=[WORKSPACE], registration_ref='bench-source-'+str(group), now=now,
                    source_limit=1024, installation_limit=4096)
            source = sources[group]
            instance = deps.repos.observations.create_instance(uow, source_id=source['source_id'],
                expected_revision=source['revision'], workspace_id=WORKSPACE, external_instance_ref='bench-instance-'+str(number),
                now=now, instance_limit=4096)
            instance = dict(instance, fixture_number=number)
            native = sessions[number % len(sessions)]
            selection = {key:native[key] for key in ('server_id','executor_id','session_id','binding_id',
                'workspace_binding_id','session_owner_generation','open_operation_id','stream_epoch')}
            selection.update(source_id=source['source_id'], source_revision=source['revision'],
                observed_instance_id=instance['observed_instance_id'], generation=instance['generation'], expected_correlation_revision=0)
            deps.repos.observation_correlations.replace_selection(uow, selection=selection, proof=proof, verified_at=now,
                now=now, max_records=4096, agent_id=AGENT, workspace_id=WORKSPACE)
            instances.append(instance)
            additions.setdefault(group, []).append(instance)
    for group, items in additions.items():
        source = sources[group]
        token = service.issue_token(context=operator, source_id=source['source_id'], body=dict(expected_revision=source['revision'],
            instance_grants=[{key:item[key] for key in ('observed_instance_id','generation')} for item in items]))['token']
        reports = [dict(schema_version=1, source_id=source['source_id'], observed_instance_id=item['observed_instance_id'],
            generation=item['generation'], sequence=1, state='blocked' if item['fixture_number'] % 2 == 0 else 'working',
            evidence='inferred', observed_at=deps.clock.now_iso(),
            valid_for_seconds=3600) for item in items]
        service.publish(token=token, payload={'reports':reports})


def campaign(home, session_count, args, proof):
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.application.observations import ObservationService
    from okto_nexus.application.attention import AttentionService
    from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
    from okto_nexus.adapters.outbound.sqlite import observation_correlation_projection as batch
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    argv = ['--home',str(home),'--embedding-mode','off','--feature-harness-integrations','false',
        '--feature-observations','true','--feature-attention','true','--metrics-mode','disabled']
    for key,value in QUOTAS.items():
        argv.extend(['--'+key.replace('_','-'),str(value)])
    deps = bootstrap({}, argv)
    try:
        operator = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
        service = ObservationService(deps=deps, access=build_execution_access(deps), correlations=batch)
        attention = AttentionService(factory=deps.connection_factory, access=service.access,
            queries=SqliteAttentionQueries(decision_registry=deps.approvals.attention_decision_actions), clock=deps.clock, config=deps.config)
        trace = Trace(deps.connection_factory)
        native_start = time.perf_counter()
        sessions = seed_native(deps, session_count)
        result = dict(sessions=session_count, receipts_per_session=12,
            external_state_distribution=dict(blocked=0.5, working=0.5),
            native_seed_ms=(time.perf_counter()-native_start)*1000, stages=[])
        sources, instances = {}, []
        for target in (64,512,4096):
            started = time.perf_counter()
            grow(deps, service, operator, sessions, instances, sources, target)
            stage = dict(instances=target, observation_seed_ms=(time.perf_counter()-started)*1000, reads={})
            ids = [item['observed_instance_id'] for item in instances]
            def read_batch():
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    return batch.load(uow, observed_instance_ids=ids)
            reads = dict(batch_all=read_batch,
                observation_page_200=lambda:service.read(context=operator, workspace_id=WORKSPACE, limit=200),
                attention_external_blocked_50=lambda:attention.read(context=operator, filters={'workspace_id':WORKSPACE,'kind':'external_blocked'}, limit=50),
                attention_all_kinds_50=lambda:attention.read(context=operator, filters={'workspace_id':WORKSPACE}, limit=50),
                observation_summary=lambda:service.summary(context=operator, workspace_id=WORKSPACE))
            before = canonical_fingerprint(deps.connection_factory)
            for name, call in reads.items():
                samples = [trace.measure(call) for _ in range(args.samples)]
                for sample in samples:
                    if sample['ok']:
                        if name == 'batch_all':
                            expected = sample['records'] == target and sample['verified_receipts'] == target
                        elif name == 'observation_page_200':
                            expected = sample['records'] == min(target, 200) and sample['canonical_items'] == sample['records']
                        elif name == 'attention_external_blocked_50':
                            expected = sample['total'] == target // 2
                        elif name == 'observation_summary':
                            expected = (sample['total'] == target
                                and sample['activity'] == dict(blocked=target // 2, working=target // 2, idle=0, unknown=0)
                                and sample['freshness'] == dict(current=target, stale=0, unknown=0, unavailable=0))
                        else:
                            expected = sample['total'] >= target // 2
                        if not expected:
                            sample.update(ok=False, error=dict(type='FixtureReadMismatch', code=None))
                times = [sample['elapsed_ms'] for sample in samples if sample['ok']]
                stage['reads'][name] = dict(samples=samples, successful_samples=len(times),
                    median_ms=statistics.median(times) if times else None, first_sample_is_cold_or_less_warm=True)
            after = canonical_fingerprint(deps.connection_factory)
            stage.update(canonical_tables_unchanged=before==after, canonical_table_count=len(before))
            if before != after:
                raise RuntimeError('A measured read changed canonical tables')
            result['stages'].append(stage)
            print(json.dumps(dict(sessions=session_count, instances=target,
                failed_samples=sum(args.samples-value['successful_samples'] for value in stage['reads'].values()))), flush=True)
        result['package_after'] = package_check(proof)
        return result
    finally:
        deps.connection_factory.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--go', action='store_true')
    parser.add_argument('--proof', required=True)
    parser.add_argument('--dependency-path')
    parser.add_argument('--session-count', type=int, default=64)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--output', default='benchmark-installed.json')
    args = parser.parse_args()
    if not args.go:
        parser.error('Prepared only: explicit coordinator authorization and --go required')
    if not 1 <= args.session_count <= 4096 or args.samples != 3:
        parser.error('Use the approved three samples and an explicit bounded session count')
    output = (ROOT / args.output).resolve()
    if output.parent != ROOT or output.exists():
        parser.error('Choose a new output filename in the benchmark directory')
    homes = [ROOT/'private-one-session', ROOT/'private-many-sessions']
    if any(home.exists() for home in homes):
        parser.error('This campaign requires fresh absent private fixture homes')
    # This precedes the first product import in package_check and guard setup.
    isolate_environment(homes[0])
    if args.dependency_path:
        sys.path.append(str(Path(args.dependency_path).resolve()))
    proof = json.loads(Path(args.proof).read_text(encoding='utf-8'))
    result = dict(schema_version=1, started_at=utc(), package=package_check(proof), samples=args.samples,
        quotas=QUOTAS, deadline_seconds=5, layouts=[], notes=[
            'USERPROFILE/APPDATA/LOCALAPPDATA are isolated inside each disposable fixture home before imports/bootstrap.',
            'Inherited application/provider variables are deleted by name without reading or recording their values; HOME/CODEX_HOME are untouched.',
            'Installed wheel only; real SQLite/services; synthetic host correlation fixtures, not real OS proof acceptance.',
            'Same-session and 64-session layouts are distinct. 4096 unique native sessions are NOT qualified by this default campaign.',
            'Twelve receipts per native session were committed through production append_execution_receipt.',
            'Three local samples include trace overhead and do not establish a general SLO.',
            'Alternating 50% blocked / 50% working, all instances correlated; no external completion events.',
            'This is not an identical comparison to OBS11: that baseline included external completions; this measures correlation and 12 receipts/session.',
            'The prior prepared 100%-blocked driver was preserved but never executed or qualified.',
            'Any noncanonical receipt timestamp in selected history produces unknown; no older-valid fallback.',
            'Direct application-service measurements exclude HTTP authentication cold-cache lookup overhead.',
            'First sample is retained separately; no undisclosed warmup. Summary remains exclusively external.',
            'Database files and synthetic credentials/proofs are private fixtures; never collect DB/WAL/SHM or their hashes.',
        ])
    with ExitStack() as guards:
        from okto_nexus.bootstrap import embedded_inventory, runtime_host
        from okto_nexus.adapters.outbound.file.artifacts import LocalArtifactStore
        import subprocess
        guards.enter_context(patch.object(subprocess, 'Popen', NoProcess))
        guards.enter_context(patch.object(embedded_inventory, 'discover_local_candidates', forbidden))
        for name in ('open_journal','create_runtime'):
            guards.enter_context(patch.object(runtime_host, name, forbidden))
        guards.enter_context(patch.object(runtime_host.EmbeddedRuntimeHost, '_compose', forbidden))
        for name in ('describe','read_text','read_bytes'):
            guards.enter_context(patch.object(LocalArtifactStore, name, forbidden))
        try:
            for home, count in zip(homes, (1,args.session_count)):
                isolate_environment(home)
                result['layouts'].append(campaign(home, count, args, proof))
                output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
            result['status'] = 'COMPLETED_MEASUREMENTS'
        except Exception as error:
            result.update(status='ERROR', error=error_metadata(error))
        finally:
            result['finished_at'] = utc()
            output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], output=output.name)), flush=True)
    return int(result['status']=='ERROR')


if __name__ == '__main__':
    try:
        status = main()
    except Exception as error:
        # Cover preflight/import failures too, without str(error), locals or SQL.
        failure = dict(status='ERROR', phase='driver_preflight', error=error_metadata(error), finished_at=utc())
        destination = ROOT / ('driver-preflight-error-'+str(time.time_ns())+'.json')
        try:
            destination.write_text(json.dumps(failure, indent=2)+'\n', encoding='utf-8')
            failure['report'] = destination.name
        except OSError:
            failure['report_persisted'] = False
        print(json.dumps(failure), flush=True)
        status = 1
    raise SystemExit(status)
