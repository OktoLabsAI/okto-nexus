"""Installed Connector consent delta; all IO confined to synthetic local files."""
from copy import deepcopy
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import InstallationCandidate, calculate_inventory_revision
from nexus_connector_core.connection_configuration import materialize_connection_configuration
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.installation import effective_installation_ref
from okto_nexus_connector.cli.commands import connect, identity
from okto_nexus_connector.cli.commands.configure import template
from okto_nexus_connector.cli.main import build_parser
from okto_nexus_connector.cli.output import Output
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.platform import paths
from okto_nexus_connector.services import remote_setup as setup
from okto_nexus_connector.storage.state_store import StateStore

KEY = 'nxs_fixture_remote_key'


@pytest.fixture
def draft(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    exe = tmp_path / 'synthetic-never-executed.exe'
    exe.write_bytes(b'synthetic fixture only')
    candidate = InstallationCandidate('codex_app_server', str(exe), fingerprint(exe), 'path', 'selected')
    store = StateStore(paths.state_file(tmp_path))
    configuration = materialize_connection_configuration(
        template() | {'adapter_id': candidate.adapter_id, 'alias': 'project'},
        execution_location='remote', workspace_root=str(project), workspace_label='Project', provider_home=None)
    record = setup.prepare(store, setup_run_id='setup-test', server='https://nexus.invalid',
        configuration=configuration, candidate=candidate, candidate_ref=effective_installation_ref(candidate),
        inventory_revision=calculate_inventory_revision([candidate]))
    bootstrap = dict(setup_run_id='setup-test', review_revision='a' * 64,
                     server_id='srv_fake', agent_id='agent', workspace_id='workspace', credential_epoch=1)
    handoff = dict(format='okto.remote-setup-handoff', version=1, bootstrap=bootstrap,
                   review_revision=bootstrap['review_revision'], child_requests=deepcopy(record['child_requests']),
                   draft_revision=record['draft_revision'])
    path = tmp_path / 'handoff.json'
    path.write_bytes(setup.document_bytes(handoff))
    args = build_parser().parse_args(['connect', '--setup-receipt', str(path), '--alias', 'worker', '--credential-stdin'])
    monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', '')
    return SimpleNamespace(root=tmp_path, store=store, args=args, output=Output(json_mode=False, stream=io.StringIO()))


@pytest.mark.parametrize('forced', [False, True])
async def test_installed_remote_refuses_without_read_or_vault(draft, monkeypatch, forced):
    monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file' if forced else '')
    monkeypatch.setattr(connect, 'vault_backend_names', lambda: ('synthetic',) if forced else ())
    monkeypatch.setattr(identity, '_vault', lambda *a: pytest.fail('vault opened'))
    stream = io.StringIO(KEY + '\n')
    monkeypatch.setattr('sys.stdin', stream)
    before = draft.store.path.read_bytes()
    with pytest.raises(ConnectorError) as refused:
        await connect.run_connect(draft.args, draft.output, draft.root)
    assert refused.value.code == 'APPROVAL_REQUIRED'
    assert stream.tell() == 0 and draft.store.path.read_bytes() == before


@pytest.mark.parametrize('approved', [False, True])
async def test_installed_storage_ready_reads_exact_one_line(draft, monkeypatch, approved):
    if approved:
        draft.store.update(lambda state: state.preferences.update({'vault.fallback_file.approved': True}))
    monkeypatch.setattr(connect, 'vault_backend_names', lambda: () if approved else ('synthetic',))
    monkeypatch.setattr(identity, '_vault', lambda *a: object())
    stream = io.StringIO(KEY + '\nnext-line\n')
    monkeypatch.setattr('sys.stdin', stream)

    class ReadConfirmed(Exception):
        pass

    class NoNetwork:
        def __init__(self, *a):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def me(self, key):
            assert key == KEY
            raise ReadConfirmed()

    monkeypatch.setattr('okto_nexus_connector.cli.commands.connect_setup.NexusHTTPClient', NoNetwork)
    with pytest.raises(ReadConfirmed):
        await connect.run_connect(draft.args, draft.output, draft.root)
    assert stream.read() == 'next-line\n'
    assert not draft.store.load().identities


@pytest.mark.parametrize('answer,approved', [('yes', True), ('no', False)])
def test_installed_interactive_consent(tmp_path, monkeypatch, answer, approved):
    store = StateStore(tmp_path / 'state.json')
    stream = io.StringIO(answer + '\nnot-a-credential\n')
    monkeypatch.setattr('sys.stdin', stream)
    assert identity._approve_fallback(SimpleNamespace(credential_stdin=False, non_interactive=False),
                                     Output(json_mode=False), store) is approved
    assert bool(store.load().preferences.get('vault.fallback_file.approved')) is approved
    assert stream.read() == 'not-a-credential\n'


async def test_installed_remote_denial_precedes_vault(draft, monkeypatch):
    draft.args.credential_stdin = False
    monkeypatch.setattr(connect, 'vault_backend_names', lambda: ())
    monkeypatch.setattr(identity, '_vault', lambda *a: pytest.fail('vault opened'))
    stream = io.StringIO('no\nnot-a-credential\n')
    monkeypatch.setattr('sys.stdin', stream)
    with pytest.raises(ConnectorError) as refused:
        await connect.run_connect(draft.args, draft.output, draft.root)
    assert refused.value.code == 'APPROVAL_REQUIRED'
    assert stream.read() == 'not-a-credential\n'


@pytest.mark.parametrize('command', ['connect', 'identity'])
async def test_installed_other_entrypoints_preserve_stdin(tmp_path, monkeypatch, command):
    monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file')
    stream = io.StringIO(KEY + '\n')
    monkeypatch.setattr('sys.stdin', stream)
    common = ['--server', 'https://nexus.invalid', '--agent', 'agent', '--credential-stdin']
    argv = ['connect', *common] if command == 'connect' else ['identity', 'add', '--alias', 'worker', *common]
    args = build_parser().parse_args(argv)
    runner = connect.run_connect if command == 'connect' else identity.run_identity
    with pytest.raises(ConnectorError) as refused:
        await runner(args, Output(json_mode=False, stream=io.StringIO()), tmp_path)
    assert refused.value.code == 'APPROVAL_REQUIRED' and stream.tell() == 0
