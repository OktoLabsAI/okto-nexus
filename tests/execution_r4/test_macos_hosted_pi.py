"""Qualify the proposed Intel macOS Pi renderer over installed Nexus and R4."""

import asyncio
from dataclasses import replace
import errno
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

import test_pr34_remediation as server_fixture
from nexus_connector_core import pi_extension_resource
from nexus_connector_core.discovery import candidate_pi_node_cli, fingerprint
from nexus_connector_core.native.adapters import compatibility, pi
from okto_nexus.adapters.outbound.local_presenter_client import open_local_presentation, review_local_presentation
from okto_nexus.application.terminal_connection import PREFIX
from okto_nexus.application.terminal_work import read_binding_session
from okto_nexus_connector.services.core_host import CoreRuntimeHost
from remote_renewal_helpers import RemoteProject
from tools.probe_macos_pi import ANSWER, PI_ARGS, PROMPT, SANDBOX, prepare_fixture, verify_history, verify_network_denied


MACOS_BUILD = 'sha256:8f4451e71c3200fd1dcada6dbfae32963f43aa378ede063f30feec33ed94b721'
MACOS_NODE = 'sha256:2a249a6a7015b0555c3448a77d226c1f3c8f62bd133d89044a2e1518cd16c4b3'
pytestmark = pytest.mark.skipif(sys.platform != 'darwin' or not os.getenv('NEXUS_PI_HOSTED_REPORT'),
                                reason='requires the pinned Pi distribution on the Intel macOS runner')


READER = '''
import fcntl, json, os, signal, sys, termios
from okto_nexus.adapters.inbound.cli.session import attach_session
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP

fcntl.ioctl(0, termios.TIOCSCTTY, 0)
assert os.tcgetpgrp(0) == os.getpgrp()
signal.signal(signal.SIGHUP, signal.SIG_DFL)
with os.fdopen(int(sys.argv[1])) as secret:
    config = json.load(secret)
api = RemoteOperatorHTTP(config['origin'], token=config['token'], server_id=config['binding']['server_id'])
attach_session(api, config['binding'], session_id=config['session_id'], interactive=True)
'''


def close_controlling_terminal(project, binding, session_id):
    import pty
    import select

    master, slave = pty.openpty()
    secret, writer = os.pipe()
    process = None
    try:
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', READER, str(secret)],
                                   stdin=slave, stdout=slave, stderr=slave, pass_fds=(secret,),
                                   start_new_session=True, cwd=project.project)
        os.close(slave)
        slave = None
        os.close(secret)
        secret = None
        output_pipe = os.fdopen(writer, 'w', encoding='utf-8')
        writer = None
        with output_pipe:
            json.dump(dict(origin=project.origin, token=project.http.token, binding=binding,
                           session_id=session_id), output_pipe)
        captured = bytearray()
        deadline = time.monotonic() + 35
        while PROMPT.encode() not in captured and time.monotonic() < deadline:
            if not select.select([master], [], [], 0.2)[0]:
                continue
            try:
                data = os.read(master, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                break
            if not data:
                break
            captured.extend(data)
            assert len(captured) < 256 * 1024, 'Unexpected Pi terminal output'
        active, = project.rows('session_attachments')
        assert active['state'] == 'ACTIVE' and active['session_id'] == session_id
        assert PROMPT.encode() in captured, 'The exact live prompt did not reach the terminal'
        assert project.http.token.encode() not in captured
        os.close(master)
        master = None
        assert process.wait(timeout=10) == -signal.SIGHUP
        return active['attachment_id']
    finally:
        for descriptor in (master, slave, secret, writer):
            if descriptor is not None:
                os.close(descriptor)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def stage_candidate(monkeypatch, directory, candidate):
    assert sys.platform == 'darwin' and platform.machine() == 'x86_64'
    assert (candidate.version, candidate.architecture, candidate.build_identity) == ('0.87.1', 'x86_64', MACOS_BUILD)
    assert fingerprint(Path(candidate.executable)) == MACOS_NODE
    # Exercise the proposed exact entry in the installed package. The copied
    # JavaScript changes only the platform clause. All file digests and the
    # canonical Python Node, installation and lease checks remain in effect.
    packaged = pi_extension_resource.pi_hosted_rpc_path()
    source_assets = directory / 'pi-hosted'
    shutil.copytree(packaged.parent, source_assets)
    hosted = source_assets / packaged.name
    code = hosted.read_text(encoding='utf-8')
    before = '["win32", "linux"].includes(process.platform)'
    assert code.count(before) == 1
    hosted.write_text(code.replace(before, '["win32", "linux", "darwin"].includes(process.platform)'), encoding='utf-8')
    monkeypatch.setitem(pi_extension_resource._REVIEWED_HOSTS, 'darwin', (MACOS_BUILD, MACOS_NODE))
    monkeypatch.setattr(pi_extension_resource, 'pi_hosted_rpc_path', lambda: hosted)
    reviewed = ('pi', candidate.version, sys.platform, candidate.architecture, candidate.build_identity)
    monkeypatch.setattr(compatibility, 'QUALIFIED_BUILD_IDENTITIES', compatibility.QUALIFIED_BUILD_IDENTITIES | {reviewed})

    spawn = pi.spawn_owned_process

    def isolated_spawn(argv, **kwargs):
        assert argv[0] == candidate.executable and argv[1] == str(hosted)
        return spawn((*SANDBOX, *argv, *PI_ARGS), **kwargs)

    monkeypatch.setattr(pi, 'spawn_owned_process', isolated_spawn)


def test_installed_macos_pi_reader_hangup_preserves_work(tmp_path_factory, monkeypatch):
    directory = tmp_path_factory.mktemp('pi')
    release = Path(os.environ['NEXUS_PI_RELEASE']).resolve(strict=True)
    node = Path(os.environ['NEXUS_PI_NODE']).resolve(strict=True)
    candidate = candidate_pi_node_cli(node, release / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js',
                                      explicit=True)
    stage_candidate(monkeypatch, directory, candidate)
    home, entered, release_turn, environment = prepare_fixture(directory, release)
    bootstrap, build = server_fixture.bootstrap, server_fixture.build_app
    monkeypatch.setattr(server_fixture, 'bootstrap', lambda env, args: bootstrap(env, [*args, '--embedding-mode', 'off']))

    def build_app(deps, **kwargs):
        deps.config.runtime_session_interaction_enabled = True
        return build(deps, **kwargs)

    monkeypatch.setattr(server_fixture, 'build_app', build_app)
    server = server_fixture._runtime(directory, SimpleNamespace(param='production'), monkeypatch)
    try:
        project = RemoteProject(next(server), directory, monkeypatch, actions=4, candidate=candidate, provider_home=str(home))
        verify_network_denied(node, environment, project.project)
        approved_launch = CoreRuntimeHost.approved_launch

        async def approved(host, store, **kwargs):
            setup = await approved_launch(host, store, **kwargs)
            assert host is project.daemon.host

            async def isolated(prepared):
                assert Path(prepared.cwd) == project.project
                assert all(ref.startswith('native-cap:') for ref in prepared.secret_refs)
                return dict(environment)

            return replace(setup, environment=isolated)

        monkeypatch.setattr(CoreRuntimeHost, 'approved_launch', approved)

        async def exercise():
            try:
                await project.start()
                operation = await asyncio.to_thread(project.work().submit, PROMPT, new_session=True,
                                                    client_intent_id='macos-hosted-pi')
                session_id = operation['scope']['session_id']
                await project.eventually(entered.is_file, timeout=70)
                owner, = [entry for runtime in project.daemon.host._runtimes.values()
                          for key, entry in runtime._sessions.items() if key.session_id == session_id]
                transport = owner.native._connector._transport
                native = transport._proc
                assert type(native).__name__ == 'OwnedDarwinPopen' and transport._hosted_rpc_ready
                binding = await asyncio.to_thread(project.call, 'GET', PREFIX + '/connections/bindings/' + project.binding['binding_id'])
                context = await asyncio.to_thread(read_binding_session, project.http, binding, session_id)
                generation = context['scope']['session_owner_generation']
                scope = {name: context['scope'][name] for name in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                                                  'workspace_binding_id', 'agent_id', 'session_id')}
                attachment = await asyncio.to_thread(close_controlling_terminal, project, binding, session_id)
                await project.eventually(lambda: any(row['attachment_id'] == attachment and row['state'] == 'DETACHED'
                                                      for row in project.rows('session_attachments')))
                assert native.poll() is None and not project.rows('execution_results')
                release_turn.touch()
                await project.operation(operation['submission_turn_operation_id'], timeout=180)
                await project.eventually(lambda: len(project.rows('execution_results')) == 1)
                result, = project.rows('execution_results')
                assert result['session_id'] == session_id and result['output_text'] == ANSWER
                verify_history(home)

                def reread():
                    revision = review_local_presentation(project.http, scope=scope,
                        expected_session_generation=generation, presentation='pi_remote')
                    with open_local_presentation(project.http, scope=scope, expected_session_generation=generation,
                            capability_revision=revision, client_intent_id='macos-hosted-pi-result',
                            pi_viewport=(100, 36), remote=True) as reader:
                        captured = bytearray()
                        deadline = time.monotonic() + 15
                        while ANSWER.encode() not in captured and time.monotonic() < deadline:
                            if data := reader.poll_pi_output(1):
                                captured.extend(data)
                            assert len(captured) < 256 * 1024
                        assert ANSWER.encode() in captured and project.http.token.encode() not in captured

                await asyncio.to_thread(reread)
                assert transport._proc is native and native.poll() is None
                closed = await asyncio.to_thread(project.work().submit, action='close', session_id=session_id,
                                                  client_intent_id='macos-hosted-pi-close')
                await project.operation(closed['operation_id'], timeout=180)
                assert native.poll() is not None
            finally:
                release_turn.touch()
                await project.close()

        asyncio.run(exercise())
    finally:
        server.close()
    report = dict(build_identity=MACOS_BUILD, node_digest=MACOS_NODE, macos=platform.mac_ver()[0],
                  proposed_renderer=True, operator_attach_http_ws=True, pty_close_received_sighup=True,
                  detached_reader_before_result=True, same_process_and_session=True, terminal_result_reopened=True,
                  canonical_close=True, exact_history=True, inference_provider='synthetic')
    Path(os.environ['NEXUS_PI_HOSTED_REPORT']).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
