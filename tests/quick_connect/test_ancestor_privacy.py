"""Real registered ancestor and observed private-origin logging, provider zero."""
import hashlib
import json
import logging
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_quick_connect_cli as fixtures
from test_git_cli_integration import local_git

from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound import git_project_hint as hints

local_setup = fixtures.local_setup
checking = fixtures.checking
terminal = fixtures.terminal
quick_cli = fixtures.quick_cli
isolated_provider_environment = fixtures.isolated_provider_environment


def protected(c):
    tables = ('agents', 'workspaces', 'execution_bindings', 'agent_endpoints', 'runtime_profiles',
        'runtime_execution_grants', 'connection_setup_commits', 'execution_sessions', 'execution_operations', 'connection_public_ids')
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: [{key: value for key, value in dict(row).items() if key != 'last_seen_at'}
            for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')] for table in tables}


def scripted(c, monkeypatch, expected):
    values, prompts = list(expected), []
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def read(prompt):
        assert len(prompts) < len(values), 'Prompt budget exhausted; refusing another action'
        expected_prompt, response = values[len(prompts)]
        assert prompt == expected_prompt, ('Unexpected prompt', prompt, expected_prompt)
        prompts.append(prompt)
        return response
    monkeypatch.setattr('builtins.input', read)
    return prompts


def test_c13_registered_ancestor_does_not_expand_nested_cwd(quick_cli, tmp_path, monkeypatch, capsys):
    c = quick_cli
    git = local_git(c, tmp_path)
    git('config', '--local', 'remote.origin.url', 'https://fixture.invalid/registered-ancestor.git')
    monkeypatch.setattr(hints, '_trusted_git', c.trusted_git)
    prompts = scripted(c, monkeypatch, [('Confirm this review, including the model connection test? [y/customize/cancel] ', 'y')])
    assert c.run(['connect', 'codex', '--profile', 'ancestor', '--no-chat']) == 0
    capsys.readouterr()
    parent_path = c.home / 'terminal/profiles/ancestor.json'
    parent_bytes = parent_path.read_bytes()
    parent = json.loads(parent_bytes)
    assert parent['state'] == 'done' and len(prompts) == 1
    first_ref = parent['result']['public_connection']['canonical_ref']
    assert parent['result']['public_connection']['state'] == 'bound'
    directory = c.t.call('GET', '/api/v1/runtime-management/connections/workspaces')
    assert first_ref['workspace_id'] in {row['workspace_id'] for row in directory['items']}
    original_current = c.t.flow.current(first_ref['agent_id'], first_ref['binding_id'])
    assert original_current['folders']['workspace_root'] == str(c.project)
    before = protected(c)
    subdir = c.project / 'subdir'
    subdir.mkdir()
    assert subdir.resolve().is_relative_to(c.project.resolve()) and not (subdir / '.git').exists()
    monkeypatch.chdir(subdir)
    prompts = scripted(c, monkeypatch, [('Project: ', 'n'), ('Confirm this review, including the model connection test? [y/customize/cancel] ', 'n')])
    assert c.run(['connect', 'codex', '--profile', 'nested', '--no-chat']) == 0
    output = capsys.readouterr().out
    nested_path = c.home / 'terminal/profiles/nested.json'
    review = json.loads(nested_path.read_bytes())
    assert prompts[0] == 'Project: ' and len(prompts) == 2
    assert 'New project suggestion: registered-ancestor' in output
    assert review['state'] == 'review' and review['request']['workspace_id'] is None
    assert review['selection']['project'] == str(subdir)
    assert review['request']['configuration']['workspace_root'] == str(subdir)
    assert review['selection']['quick_connect']['cwd_resolution']['invocation_cwd'] == str(subdir)
    assert protected(c) == before and parent_path.read_bytes() == parent_bytes
    assert len(c.t.turns) == len(c.t.probes) == 1
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    assert c.run(['connect', '--profile', 'nested', '--approve', review['review_revision'], '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    second_ref = result['quick_connect']['canonical_reference']
    assert second_ref['workspace_id'] != first_ref['workspace_id'] and second_ref['binding_id'] != first_ref['binding_id']
    assert result['quick_connect']['project_root'] == str(subdir) and Path.cwd() == subdir
    current = c.t.flow.current(second_ref['agent_id'], second_ref['binding_id'])
    assert current['folders']['workspace_root'] == str(subdir)
    assert c.t.flow.current(first_ref['agent_id'], first_ref['binding_id']) == original_current
    assert parent_path.read_bytes() == parent_bytes
    after = protected(c)
    assert all(all(row in after[table] for row in rows) for table, rows in before.items())
    assert len(c.t.turns) == 2 and len(c.t.probes) == 1
    print('C13_PROOF ' + json.dumps({'ancestor_registered': True, 'nested_root_preserved': True,
        'parent_reference': first_ref, 'nested_reference': second_ref, 'explicit_project_choice': True}))


def test_d25_private_origin_does_not_enter_observed_logs_json_homes_or_sqlite(quick_cli, local_setup, tmp_path, monkeypatch, capsys):
    c = quick_cli
    origin = 'https://fixture-private-user:PRIVATE@privacy.invalid/owner/privacy-project.git?token=PRIVATE#PRIVATE'
    patterns = ['PRIVATE', origin, 'privacy.invalid', 'fixture-private-user']
    encoded = [value.encode('utf-8') for value in patterns]
    git = local_git(c, tmp_path)
    git('config', '--local', 'remote.origin.url', origin)
    input_config = (c.project / '.git/config').resolve()
    monkeypatch.setattr(hints, '_trusted_git', c.trusted_git)
    traces = [tmp_path / 'git-trace.log', tmp_path / 'git-trace2.jsonl']
    monkeypatch.setenv('GIT_TRACE', str(traces[0]))
    monkeypatch.setenv('GIT_TRACE2_EVENT', str(traces[1]))
    log_path = c.home / 'logs/observed-local.log'
    log_path.parent.mkdir(parents=True)
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(message)s'))
    loggers = [logging.getLogger(), logging.getLogger('okto_nexus'), logging.getLogger('httpx')]
    original_loggers = [(logger, logger.level, logger.propagate) for logger in loggers]
    for logger, _, _ in original_loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        if logger is not loggers[0]:
            logger.propagate = False
    outputs = []
    def no_secret(value):
        assert not any(pattern in value for pattern in patterns)
    def run_json(tokens, expected):
        assert c.run(tokens) == expected
        capture = capsys.readouterr()
        no_secret(capture.out)
        no_secret(capture.err)
        outputs.append(capture.out)
        return json.loads(capture.out)
    try:
        logging.getLogger('okto_nexus.qc34.audit').warning('QC34_SINK_BEFORE')
        review = run_json(['connect', 'codex', '--profile', 'privacy', '--json'], 3)
        assert review['state'] == 'review' and review['selection']['label'] == 'privacy-project'
        assert review['selection']['quick_connect']['project_name_source'] == 'git_origin'
        configured = run_json(['connect', '--profile', 'privacy', '--approve', review['review_revision'], '--json'], 0)
        reference = configured['quick_connect']['canonical_reference']
        before = protected(c)
        def forbidden(*args, **kwargs):
            pytest.fail('Retained privacy profile or ID rediscovered Git')
        monkeypatch.setattr(hints, 'discover_project_name', forbidden)
        for tokens in (['connect', '--profile', 'privacy', '--json'], ['connect', '--id', 'codex', '--json']):
            resumed = run_json(tokens, 0)
            assert resumed['quick_connect']['canonical_reference'] == reference
            assert resumed['quick_connect']['status'] == 'connected'
        scripted(c, monkeypatch, [('Confirm resume? [y/N] ', 'y')])
        assert c.run(['connect', '--profile', 'privacy', '--no-chat']) == 0
        plain = capsys.readouterr()
        no_secret(plain.out)
        no_secret(plain.err)
        assert 'ID do Harness: codex' in plain.out
        assert protected(c) == before and len(c.t.turns) == len(c.t.probes) == 1
        logging.getLogger('okto_nexus.qc34.audit').warning('QC34_SINK_AFTER')
        handler.flush()
    finally:
        for logger, level, propagate in original_loggers:
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.propagate = propagate
        handler.close()
    logs = log_path.read_text(encoding='utf-8')
    assert 'QC34_SINK_BEFORE' in logs and 'QC34_SINK_AFTER' in logs
    http_events = sum('httpx HTTP Request:' in line for line in logs.splitlines())
    assert http_events > 0
    no_secret(logs)
    assert all(not trace.exists() for trace in traces)
    from okto_nexus.adapters.outbound.harness import event_journal
    producer = Path(event_journal.__file__).resolve()
    producer_sha = hashlib.sha256(producer.read_bytes()).hexdigest()
    assert producer_sha == '9262ee2742029bf4826d022fc2bd7fec54c2ff5234f193ef3261f1a306cdf274'
    journal = c.t.deps.harness_supervisor.event_ingress.journal
    expected_lock = (Path(c.t.deps.config.home_dir) / 'runtime-journal-v1/writer.lock').resolve()
    assert expected_lock.is_relative_to(tmp_path.resolve())
    audit = Path(os.environ.get('QC_DERIVATIVE_OUTPUT', str(tmp_path))) / 'file-read-audit.jsonl'
    length_proofs = []
    files, total_bytes, exclusions = [], 0, []
    for path in sorted(tmp_path.rglob('*')):
        if not path.is_file():
            continue
        if path.resolve() == input_config:
            exclusions.append(str(path.relative_to(tmp_path)))
            continue
        def facts(p):
            s = p.lstat()
            return {'size': s.st_size, 'device': s.st_dev, 'inode': s.st_ino,
                'mode': s.st_mode, 'attributes': getattr(s, 'st_file_attributes', 0)}
        prior = facts(path)
        attempt = {'path': str(path.relative_to(tmp_path)), 'before': prior}
        with audit.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'phase': 'before_read', **attempt}) + '\n')
        try:
            data = path.read_bytes()
        except PermissionError:
            later = facts(path)
            assert path.resolve() == expected_lock
            assert stat.S_ISREG(prior['mode']) and not prior['attributes'] & 0x400
            assert prior == later and prior['size'] == 1
            assert prior['size'] < min(map(len, encoded))
            assert type(journal) is event_journal.FileRuntimeEventJournal
            assert journal.root.resolve() / 'writer.lock' == expected_lock
            owner = journal._owner_file
            assert owner is not None and not owner.closed
            owner_stat = os.fstat(owner.fileno())
            assert (owner_stat.st_dev, owner_stat.st_ino, owner_stat.st_size) == (prior['device'], prior['inode'], 1)
            assert hashlib.sha256(producer.read_bytes()).hexdigest() == producer_sha
            proof = {**attempt, 'after': later, 'outcome': 'length_proof',
                'minimum_marker_encoded_bytes': min(map(len, encoded)),
                'producer': str(producer), 'producer_sha256': producer_sha,
                'same_live_owner_identity': True}
            length_proofs.append(proof)
            with audit.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'phase': 'after_read', **proof}) + '\n')
            continue
        with audit.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'phase': 'after_read', **attempt, 'outcome': 'full_read', 'bytes_read': len(data)}) + '\n')
        total_bytes += len(data)
        assert not any(pattern in data for pattern in encoded), str(path.relative_to(tmp_path))
        for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
            no_secret(data.decode(encoding, errors='ignore'))
        files.append({'path': str(path.relative_to(tmp_path)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    assert exclusions == ['workspace\\.git\\config'] or exclusions == ['workspace/.git/config']
    tables, rows, cells = [], 0, 0
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        assert names
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            count = 0
            for row in uow.connection.execute('SELECT * FROM ' + quoted):
                count += 1
                for value in row:
                    if isinstance(value, (str, bytes)):
                        cells += 1

                        if isinstance(value, str):
                            no_secret(value)
                        else:
                            assert not any(pattern in value for pattern in encoded)
                            for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
                                no_secret(value.decode(encoding, errors='ignore'))
            rows += count
            tables.append({'table': name, 'rows': count})
    proof = {'sink': 'logging.FileHandler UTF-8 DEBUG attached to root/okto_nexus/httpx; no redaction/filter added',
        'before_marker': True, 'after_marker': True, 'httpx_request_events': http_events,
        'logging_bytes': log_path.stat().st_size, 'logging_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
        'json_outputs_checked': len(outputs), 'plain_stdout_checked': True,
        'length_proofs': length_proofs, 'producer_sha256': producer_sha, 'files': files, 'file_bytes_checked': total_bytes, 'only_exclusion': exclusions,
        'all_sqlite_tables': tables, 'sqlite_table_count': len(tables), 'sqlite_rows_checked': rows,
        'sqlite_text_cells_checked': cells, 'git_trace_files_absent': True,
        'local_cli_home_scanned': str(c.home), 'server_home_scanned': str(c.t.deps.config.home_dir),
        'outbound_product_telemetry_enabled_by_test': False, 'raw_credentials_or_db_exported': False}
    (tmp_path / 'privacy-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print('D25_PROOF ' + json.dumps({key: proof[key] for key in ('httpx_request_events', 'json_outputs_checked',
        'sqlite_table_count', 'sqlite_rows_checked', 'sqlite_text_cells_checked', 'git_trace_files_absent')}))
