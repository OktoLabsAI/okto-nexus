"""Cases for the normative NS15.04 migration/restore entry."""
from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
import time

import pytest
from nexus_connector_core import CoreError
from nexus_connector_core.harness_config import harness_http_template
from okto_nexus.bootstrap import local_mcp_home


def template():
    return harness_http_template('codex_app_server', 'http://127.0.0.1:8000/mcp',
        'mcp-cap:restore-fixture', entry_name='nexus', approved_origins={'http://127.0.0.1:8000'},
        harness_is_local=True, loopback_reachable=True, format_qualified=True)


def configuration_case(tmp_path, monkeypatch, request):
    from okto_nexus.adapters.inbound.cli.mcp_config_migration import plan_entry_migration, apply_entry_migration
    from okto_nexus.domain.keys import generate_api_key
    selected = tmp_path / 'selected.json'
    foreign = {'command': 'unrelated', 'args': ['keep'], 'env': {'PRIVATE': 'unchanged'}}
    original = json.dumps({'mcpServers': {'nexus': {'command': 'okto-nexus', 'args': ['stdio']}, 'foreign': foreign}}).encode()
    selected.write_bytes(original)
    plan = plan_entry_migration(selected, entry_name='nexus', url='http://127.0.0.1:8000/mcp', existing_api_key=generate_api_key())
    import os
    def fail_replace(*args):
        raise OSError('injected apply failure')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_replace)
        with pytest.raises(OSError, match='injected'):
            apply_entry_migration(plan)
    assert selected.read_bytes() == original
    saved = apply_entry_migration(plan)
    assert saved.read_bytes() == original
    assert json.loads(selected.read_bytes())['mcpServers']['foreign'] == foreign
    key = json.loads(selected.read_bytes())['mcpServers']['nexus']['headers']['Authorization'].removeprefix('Bearer ')
    assert apply_entry_migration(plan_entry_migration(selected, entry_name='nexus',
        url=plan.url, existing_api_key=key)) is None

    frame = dict(server_id='server', executor_id='executor', binding_id='binding', session_id='session', session_owner_generation=1)
    root = tmp_path / 'session-mcp'
    link = os.link
    def fail_config(source, destination):
        if Path(destination).name == 'config.toml':
            raise OSError('injected config publication failure')
        return link(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'link', fail_config)
        with pytest.raises(OSError, match='injected'):
            local_mcp_home.session_mcp_home(root, frame=frame, configuration_digest='digest', template=template())
    assert not list(root.rglob('config.toml'))
    assert not list(root.rglob('.mcp-*'))
    home = local_mcp_home.session_mcp_home(root, frame=frame, configuration_digest='digest', template=template())
    home.require_current()
    before = home.config.read_bytes()
    assert local_mcp_home.session_mcp_home(root, frame=frame, configuration_digest='digest', template=template()).home == home.home
    owner = home.home / '.owner.json'
    changed = json.loads(owner.read_bytes()); changed['scope']['binding_id'] = 'foreign-binding'
    owner.write_text(json.dumps(changed), encoding='utf-8')
    foreign_marker = owner.read_bytes()
    with pytest.raises(CoreError, match='PROFILE_DRIFT'):
        local_mcp_home.session_mcp_home(root, frame=frame, configuration_digest='digest', template=template())
    assert owner.read_bytes() == foreign_marker and home.config.read_bytes() == before


def restore_case(tmp_path, monkeypatch, request, *, backfilled_policies=False):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / 'tools'))
    import offline_runtime_backup as recovery
    import test_local_realization as local
    from test_embedded_dispatch import connect_local, admit, wait_receipt
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    from fastapi.testclient import TestClient
    tables = ('execution_operations', 'execution_receipts', 'execution_dispatch_outbox',
              'execution_event_ingress', 'execution_event_watermarks', 'execution_sessions')
    if backfilled_policies:
        from okto_nexus.adapters.outbound.sqlite.migration_backup import create_migration_backup
        from okto_nexus.bootstrap.execution_migration import migrate_execution_catalog
        original_app_for = local.app_for

        def seeded(home):
            deps, app = original_app_for(home)
            with deps.connection_factory.unit_of_work() as uow:
                c = uow.connection
                stamp = deps.clock.now_iso()
                c.execute("INSERT INTO agents(agent_id,created_at,permissions) VALUES (?,?,?)",
                          ('policy-owner', stamp, '{"messages":{"send_direct":false}}'))
                c.execute("INSERT INTO policies(policy_id,name,created_at) VALUES (?,?,?)",
                          ('retained-policy', 'Rollback policy', stamp))
                c.execute("INSERT INTO policy_versions(policy_id,version,audience,governance,published_at) "
                          "VALUES (?,1,?,?,?)", ('retained-policy', '["agent:policy-owner"]', '[]', stamp))
                c.execute("INSERT INTO agent_policy_bindings(agent_id,position,source,policy_id,mode,pinned_version,created_at) "
                          "VALUES (?,0,'global',?,'pinned',1,?)", ('policy-owner', 'retained-policy', stamp))
                c.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) "
                          "VALUES ('rollback-legacy','codex','{}',?,?)", (stamp, stamp))
            baseline = tmp_path / 'tn40-before-backfill'
            create_migration_backup(deps.config.db_path, baseline)
            result = migrate_execution_catalog(deps.config.db_path, baseline)
            assert result['status'] == 'CATALOG_BACKFILL_COMPLETE'
            assert result['processed'] > 0 and not result['execution_activated']
            return deps, app

        monkeypatch.setattr(local, 'app_for', seeded)
        tables += ('policies', 'policy_versions', 'agent_policy_bindings', 'execution_migration_map')
    def rows(home):
        with closing(sqlite3.connect(home / 'nexus.db')) as db:
            return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall() for table in tables}
    with contextmanager(local.local_setup.__wrapped__)(tmp_path, monkeypatch, request) as setup:
        _, binding, native = connect_local(setup)
        deps, app, client, headers, *_ = setup
        if backfilled_policies:
            with deps.connection_factory.unit_of_work() as uow:
                policy_key = app.state.auth.issue_key(uow, agent_id='policy-owner')
            policy_headers = {'Authorization': 'Bearer ' + policy_key}
            policy_before = client.get('/v1/connections/me', headers=policy_headers)
            assert policy_before.status_code == 200, policy_before.text
            assert 'messages.send_direct' not in policy_before.json()['permissions']
        opened = admit(setup, binding, 'restore-open', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        session = opened['scope']['session_id']
        config = local_mcp_home.session_mcp_home(deps.config.home_dir / 'session-mcp',
            frame=opened['scope'], configuration_digest='restore-digest', template=template())
        before_config = config.config.read_bytes()
        refused = tmp_path / 'live-backup'
        with pytest.raises((ValueError, OSError)):
            recovery.backup(deps.config.home_dir, refused, stopped=True)
        assert not refused.exists()
        send = native.native.send
        async def lost(*args, **kwargs):
            await send(*args, **kwargs)
            raise CoreError('OUTCOME_UNKNOWN', 'submit', possible_effect=True)
        monkeypatch.setattr(native.native, 'send', lost)
        turn = admit(setup, binding, 'restore-unknown', 'turn.submit', session_id=session, text='one effect')
        deadline = time.monotonic() + 10
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                dispatch = dict(uow.connection.execute('SELECT * FROM execution_dispatch_outbox WHERE operation_id=?',
                    (turn['operation_id'],)).fetchone())
            # Reconciliation projects the durable Core receipt; last_error
            # on the transport outbox need not contain the native failure.
            result = client.get('/v1/runtime/operations/' + turn['operation_id'],
                                headers=headers['subject'])
            assert result.status_code == 200, result.text
            if (result.json().get('possible_effect') is True
                    and app.state.embedded_dispatch_owner.agents.errors.get('subject') is not None):
                assert result.json()['retry_safe'] is False
                break
            assert time.monotonic() < deadline, dispatch
            time.sleep(.02)
        assert len(native.native.sent) == 1
        assert config.config.read_bytes() == before_config and config.home.exists()
    assert native.native.stopped
    home = deps.config.home_dir
    original = rows(home)
    if backfilled_policies:
        assert all(original[table] for table in ('policies', 'policy_versions', 'agent_policy_bindings', 'execution_migration_map'))
    snapshot = tmp_path / 'r4-snapshot'
    report = recovery.backup(home, snapshot, stopped=True)
    assert report['version'] == 2
    assert any(name.startswith('core-runtime/session-') for name in report['files'])
    assert any(name.startswith('session-mcp/') for name in report['files'])
    with pytest.raises(ValueError, match='Confirm'):
        recovery.restore(snapshot, tmp_path / 'unsafe')
    restored = recovery.restore(snapshot, tmp_path / 'restored', stopped=True)
    assert rows(restored) == original
    assert (restored / config.config.relative_to(home)).read_bytes() == before_config
    assert config.config.read_bytes() == before_config
    with pytest.raises(FileExistsError):
        recovery.restore(snapshot, home, stopped=True)
    # An apparently checksummed backup cannot omit a referenced Core journal.
    damaged = tmp_path / 'damaged'
    import shutil
    shutil.copytree(snapshot, damaged)
    next((damaged / 'core-runtime').glob('session-*.db')).unlink()
    manifest = json.loads((damaged / 'backup-manifest.json').read_text())
    manifest['files'] = recovery.inventory(damaged)
    (damaged / 'backup-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Core journal'):
        recovery.restore(damaged, tmp_path / 'incomplete', stopped=True)
    assert not (tmp_path / 'incomplete').exists()
    restored_deps = bootstrap({}, ['--home', str(restored), '--feature-harness-integrations', 'false'])
    with TestClient(build_app(restored_deps)) as restored_client:
        if backfilled_policies:
            policy_after = restored_client.get('/v1/connections/me', headers=policy_headers)
            assert policy_after.status_code == 200, policy_after.text
            for field in ('agent_id', 'permissions', 'revisions'):
                assert policy_after.json()[field] == policy_before.json()[field]
        queried = restored_client.get('/v1/runtime/operations/' + turn['operation_id'], headers=headers['subject'])
        assert queried.status_code == 200, queried.text
        assert queried.json()['possible_effect'] is True
        assert queried.json()['retry_safe'] is False
        assert rows(restored) == original
    assert native.opens == 1 and len(native.native.sent) == 1
