"""Exercise the installed Pi renderer and RPC owner in an isolated process."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from unittest.mock import patch

PROMPT = 'Owner prompt held by a deterministic local provider'
RESULT = 'Native Pi rendered the answer from the same session'
STAGES = ('first-view', 'between-views', 'second-view')


def read_rpc(stream, trace_path, frames):
    try:
        with trace_path.open('w', encoding='utf-8') as trace:
            for line in stream:
                trace.write(line)
                frames.put(json.loads(line))
    finally:
        frames.put(None)


def request(owner, frames, observed, intent, command, **options):
    owner.stdin.write(json.dumps({'type': command, 'id': intent, **options}) + '\n')
    owner.stdin.flush()
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            frame = frames.get(timeout=max(.1, deadline - time.monotonic()))
        except Empty:
            break
        assert frame is not None, 'Pi RPC closed unexpectedly'
        observed.append(frame)
        if frame.get('id') == intent and frame.get('type') == 'response':
            assert frame['command'] == command and frame['success'], frame
            return frame.get('data')
    raise AssertionError(f'Pi RPC response unavailable for {intent}')


def wait_checkpoint(owner, file):
    deadline = time.monotonic() + 30
    while not file.exists() and owner.poll() is None and time.monotonic() < deadline:
        time.sleep(.03)
    assert file.is_file(), file.name
    return file.read_text(encoding='utf-8')


def exercise_owner(owner, trace_path, checkpoints):
    assert owner.stdin and owner.stdout
    frames = Queue()
    observed = []
    reader = threading.Thread(target=read_rpc, args=(owner.stdout, trace_path, frames), daemon=True)
    reader.start()
    before = request(owner, frames, observed, 'initial-state', 'get_state')
    assert before['messageCount'] == 0 and not before['isStreaming']
    session = before['sessionId']
    request(owner, frames, observed, 'owner-prompt', 'prompt', message=PROMPT)
    for stage in STAGES:
        assert wait_checkpoint(owner, checkpoints / stage) == session
        state = request(owner, frames, observed, stage, 'get_state')
        assert state['sessionId'] == session and state['isStreaming'] and state['pendingMessageCount'] == 0
        (checkpoints / ('release-' + stage)).touch()
    report = json.loads(wait_checkpoint(owner, checkpoints / 'summary.json'))
    final = request(owner, frames, observed, 'final-state', 'get_state')
    assert final['sessionId'] == session and not final['isStreaming']
    assert request(owner, frames, observed, 'result', 'get_last_assistant_text')['text'] == RESULT
    assert sum(frame.get('type') == 'agent_settled' for frame in observed) == 1
    owner.stdin.close()
    assert owner.wait(timeout=10) == 0
    reader.join(3)
    assert not reader.is_alive()
    assert wait_checkpoint(owner, checkpoints / 'owner-disposed') == '1'
    return report, Path(final['sessionFile'])


def verify_history(directory, session_file, session_id):
    assert list(directory.glob('*.jsonl')) == [session_file]
    history = [json.loads(line) for line in session_file.read_text(encoding='utf-8').splitlines()]
    assert history[0]['id'] == session_id
    messages = [entry['message'] for entry in history if entry.get('type') == 'message']
    assert [message['role'] for message in messages] == ['system', 'user', 'assistant']
    assert messages[1]['content'][0]['text'] == PROMPT
    assert messages[2]['content'][0]['text'] == RESULT


async def wait_for_turn(journal, operation_key):
    async with asyncio.timeout(20):
        while True:
            receipt = await journal.get_receipt(operation_key)
            if receipt.stage == 'SUCCEEDED':
                return
            assert receipt.stage in ('SUBMISSION_STARTED', 'SUBMITTED', 'ACCEPTED'), receipt.stage
            await asyncio.sleep(.03)


async def exercise_core(argv, env, root, checkpoints, version_command):
    from nexus_connector_core import (
        R4_PREVIEW_REVISION,
        CloseOperation,
        CoreError,
        EventCursor,
        InstallationCandidate,
        LaunchIntent,
        NativeSessionTarget,
        OpenOperation,
        OperationKey,
        SessionKey,
        ShutdownPolicy,
        TurnOperation,
        __version__,
    )
    from nexus_connector_core.discovery import fingerprint
    from nexus_connector_core.journal import SQLiteJournal
    from nexus_connector_core.native import runtime_bridge
    from nexus_connector_core.native.adapters.pi import PiRpcConnector
    from nexus_connector_core.runtime import LocalRuntimeCore
    from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost

    assert __version__ == '0.0.16'
    created = []

    def fixture_adapter(adapter_id):
        assert adapter_id == 'pi_rpc'

        def construct(*, command, **options):
            assert Path(command[0]) == Path(argv[0])
            connector = PiRpcConnector(command=argv, version_command=version_command,
                                       handshake_timeout_s=40, command_timeout_s=10, **options)
            created.append(connector)
            return connector

        return construct

    async def environment(_prepared):
        return env

    factory = runtime_bridge.CopiedAdapterFactory(environment)
    journal = SQLiteJournal(root / 'core-journal.db')
    node = Path(argv[0])
    candidate = InstallationCandidate('pi_rpc', str(node), fingerprint(node), 'explicit', 'selected',
                                      version='0.87.1', architecture='x86_64')
    runtime = LocalRuntimeCore(journal, factory, candidates={'pi_rpc': candidate},
                               workspace_roots={'workspace': str(root / 'project')})
    key = SessionKey('server', 'executor', 'test-session')
    cursor = EventCursor(key.server_id, key.executor_id, key.session_id, 'epoch')
    turn = TurnOperation('pi-probe-turn', key.session_id, PROMPT)
    scope = {
        'server_id': key.server_id, 'executor_id': key.executor_id, 'session_id': key.session_id,
        'binding_id': 'binding', 'agent_id': 'agent', 'workspace_id': 'workspace',
        'workspace_binding_id': 'workspace-binding', 'session_owner_generation': 1,
        'authorization_revision': 1, 'configuration_revision': 1, 'binding_revision': 1, 'credential_epoch': 1,
    }
    channel = {'connection_id': 'connection', 'connection_generation': 1}
    host = EmbeddedRuntimeHost(root / 'embedded-core')
    host_key = (key.executor_id, key.session_id)

    async def register_fixture_runtime():
        return runtime, journal

    host._selections[host_key] = ({'pi_rpc': candidate}, {'workspace': str(root / 'project')},
                                  None, False, key.server_id, None)
    host._runtime_tasks[host_key] = asyncio.create_task(register_fixture_runtime())
    await host._runtime_tasks[host_key]

    async def native_state():
        reply = await asyncio.to_thread(transport.request, 'get_state', {}, timeout_s=10)
        assert reply['success'] is True
        return reply['data']

    try:
        request = await runtime.begin_r4_lease_request(scope=scope, grant_id='grant', purpose='initial', **channel)
        installed = await runtime.install_r4_lease(request, {
            'protocol_major': 1, 'contract_revision': R4_PREVIEW_REVISION, 'type': 'lease.granted',
            'request_id': request.request_id, 'lease_id': 'lease', 'lease_serial': request.expected_lease_serial + 1,
            'grant_id': request.grant_id, 'scope': dict(request.scope), 'valid_for_ms': 60000,
            'allowed_actions': ['runtime.open', 'turn.submit', 'runtime.close'],
        })
        context = installed.context
        prepared = await runtime.prepare(LaunchIntent('agent', 'workspace', 'pi_rpc'), context)
        with patch.object(runtime_bridge, 'load_adapter', fixture_adapter):
            opened = await runtime.open(OpenOperation('pi-probe-open', key.session_id, 'epoch', prepared), context)
        assert opened.stage == 'SUBMITTED' and len(created) == 1
        transport = created[0]._transport  # Fixture-only read of the already-owned RPC channel.
        owner = transport._proc
        birth = await journal.get_process_birth(key)
        assert birth.evidence.pid == owner.pid and birth.opening_operation_id == opened.operation_id
        assert (await journal.get_process_launch(key)).spawn_claimed
        initial = await native_state()
        session = initial['sessionId']
        assert session == opened.native_id and initial['messageCount'] == 0
        target = NativeSessionTarget(opened.operation_id, 'pi_rpc', session, cursor.stream_epoch)
        proof = await runtime.prove_live_native_session(scope, target, **channel)
        assert proof.process == birth
        try:
            await host.read_r4_pi_session(scope, replace(target, native_session_id='sibling'), **channel)
        except CoreError as error:
            assert error.code == 'SESSION_CONFLICT'
        else:
            raise AssertionError('Core proved a foreign native session')
        submitted = await runtime.submit(turn, context)
        assert submitted.stage == 'SUBMITTED'
        for stage in STAGES:
            assert await asyncio.to_thread(wait_checkpoint, owner, checkpoints / stage) == session
            assert await host.read_r4_pi_session(scope, target, **channel) == {
                'native_session_id': session, 'is_streaming': True,
                'is_compacting': False, 'pending_message_count': 0,
            }
            assert await runtime.prove_live_native_session(scope, target, **channel) == proof
            if stage == 'between-views':
                # Repeating the same canonical operation while detached must not prompt the native owner again.
                assert await runtime.submit(turn, context) == submitted
            (checkpoints / ('release-' + stage)).touch()
        report = json.loads(await asyncio.to_thread(wait_checkpoint, owner, checkpoints / 'summary.json'))
        await wait_for_turn(journal, OperationKey(key.server_id, key.executor_id, turn.operation_id))
        settled = [event async for event in journal.events(cursor) if event.native_type == 'agent_settled']
        assert len(settled) == 1 and settled[0].operation_id == turn.operation_id
        final = await native_state()
        assert final['sessionId'] == session and not final['isStreaming']
        assert await host.read_r4_pi_session(scope, target, **channel) == {
            'native_session_id': session, 'is_streaming': False,
            'is_compacting': False, 'pending_message_count': 0,
        }
        result = await asyncio.to_thread(transport.request, 'get_last_assistant_text', {}, timeout_s=10)
        assert result['success'] and result['data']['text'] == RESULT
        closed = await runtime.close(
            CloseOperation('pi-probe-close', key.session_id, 'End isolated probe', ShutdownPolicy(1, 1)),
            context, wait_for_completion=True,
        )
        assert closed.stage == 'SUCCEEDED' and owner.poll() is not None
        assert (await journal.get_process_birth(key)) == birth
        try:
            await host.read_r4_pi_session(scope, target, **channel)
        except CoreError as error:
            assert error.code in ('SESSION_CONFLICT', 'SESSION_UNKNOWN', 'STALE_GENERATION'), error.code
        else:
            raise AssertionError('Pi state remained available after owner close')
        report.update({
            'core': __version__, 'same_birth_while_viewer_attached_and_detached': True,
            'native_session_matches_core_receipt': True, 'core_turn_replay_during_detach': True,
            'core_settled_events': len(settled), 'core_close_stage': closed.stage,
            'r4_owner_proof': True, 'foreign_native_session_refused': True,
            'embedded_state_during_all_checkpoints': True, 'embedded_state_after_settled': True,
            'embedded_state_refused_after_close': True,
        })
        return report, Path(final['sessionFile'])
    finally:
        await runtime.shutdown(ShutdownPolicy(1, 1))
        factory.close()
        journal.close()


def fingerprints(node, release, script):
    namespace = release / 'node_modules' / '@earendil-works'
    installed = namespace / 'pi-coding-agent'
    inputs = {
        'node': node,
        'probe': script,
        'pi_package': installed / 'package.json',
        'pi_sdk': installed / 'dist/index.js',
        'interactive_mode': installed / 'dist/modes/interactive/interactive-mode.js',
        'rpc_mode': installed / 'dist/modes/rpc/rpc-mode.js',
        'faux_provider': namespace / 'pi-ai/dist/providers/faux.js',
    }
    return {name: hashlib.sha256(file.read_bytes()).hexdigest() for name, file in inputs.items()}


def run(node, release, *, core):
    root = Path(tempfile.mkdtemp(prefix='nexus-si-pi-observer-')).resolve()
    script = root / 'probe.mjs'
    shutil.copyfile(Path(__file__).with_suffix('.mjs'), script)
    project, agent, checkpoints = root / 'project', root / 'agent', root / 'checkpoints'
    for directory in (project, agent, checkpoints, root / 'bin', root / 'tmp', root / 'appdata', root / 'local'):
        directory.mkdir()
    # Pi's discovery walks ancestors looking for this boundary.
    (project / '.git').mkdir()
    (project / '.git/HEAD').write_text('ref: refs/heads/fixture\n', encoding='ascii')
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'COMSPEC') if key in os.environ}
    env.update({
        'PATH': str(root / 'bin'), 'PATHEXT': '.COM;.EXE', 'HOME': str(root), 'USERPROFILE': str(root),
        'APPDATA': str(root / 'appdata'), 'LOCALAPPDATA': str(root / 'local'),
        'TMP': str(root / 'tmp'), 'TEMP': str(root / 'tmp'), 'PI_CODING_AGENT_DIR': str(agent),
        'PI_OFFLINE': '1', 'TERM': 'xterm-256color',
    })
    argv = [
        str(node), '--permission', f'--allow-fs-read={release}', f'--allow-fs-read={root}',
        f'--allow-fs-write={root}', str(script), str(release), str(project), str(agent), str(checkpoints),
    ]
    print(f'Isolated probe directory {root}', flush=True)
    if core:
        cli = release / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'
        version_command = [*argv[:5], str(cli), '--version']
        report, session_file = asyncio.run(exercise_core(argv, env, root, checkpoints, version_command))
    else:
        with (root / 'stderr.txt').open('w', encoding='utf-8') as stderr, subprocess.Popen(
            argv, cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            text=True, encoding='utf-8', bufsize=1,
        ) as owner:
            try:
                report, session_file = exercise_owner(owner, root / 'rpc.jsonl', checkpoints)
            except BaseException:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=10)
                raise
        report.update({'native_rpc_owner_exit': 0, 'disposals_after_rpc_eof': 1})
    verify_history(agent / 'sessions', session_file, report.pop('sessionId'))
    report.update({
        'rpc_continued_while_detached': True, 'exact_persisted_history': True,
        'sha256': fingerprints(node, release, script),
    })
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--pi-release', type=Path, required=True, help='Pi release root containing node_modules')
    parser.add_argument('--core', action='store_true', help='Drive the Pi process through the installed Core 0.0.16')
    args = parser.parse_args()
    run(args.node.resolve(strict=True), args.pi_release.resolve(strict=True), core=args.core)
