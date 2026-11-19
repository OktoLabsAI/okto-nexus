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
from contextlib import asynccontextmanager
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
    assert list(directory.rglob('*.jsonl')) == [session_file]
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


async def exercise_core(argv, env, root, checkpoints, version_command, *, hosted_cli=None, hosted_turn=False):
    from nexus_connector_core import (
        R4_PREVIEW_REVISION,
        CloseOperation,
        CoreError,
        EventCursor,
        HarnessSettings,
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
    from nexus_connector_core.discovery import candidate_pi_node_cli, fingerprint
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

    node = Path(argv[0])
    candidate = (await asyncio.to_thread(candidate_pi_node_cli, node, hosted_cli, explicit=True) if hosted_cli else
                 InstallationCandidate('pi_rpc', str(node), fingerprint(node), 'explicit', 'selected',
                                       version='0.87.1', architecture='x86_64'))
    workspaces = {'workspace': str(root / 'project')}
    key = SessionKey('server', 'executor', 'test-session')
    host = EmbeddedRuntimeHost(root / 'embedded-core', pi_presentation_enabled=bool(hosted_cli))
    host_key = (key.executor_id, key.session_id)
    if hosted_cli:
        runtime = await host.acquire(server_id=key.server_id, executor_id=key.executor_id, session_id=key.session_id,
                                     candidates={'pi_rpc': candidate}, workspace_roots=workspaces, environment=environment)
        journal = host._runtime_tasks[host_key].result()[1]
    else:
        journal = SQLiteJournal(root / 'core-journal.db')
        factory = runtime_bridge.CopiedAdapterFactory(environment)
        runtime = LocalRuntimeCore(journal, factory, candidates={'pi_rpc': candidate}, workspace_roots=workspaces)

        async def register_fixture_runtime():
            return runtime, journal

        host._selections[host_key] = ({'pi_rpc': candidate}, workspaces, None, False, key.server_id, None, False)
        host._runtime_tasks[host_key] = asyncio.create_task(register_fixture_runtime())
        await host._runtime_tasks[host_key]
    cursor = EventCursor(key.server_id, key.executor_id, key.session_id, 'epoch')
    turn = TurnOperation('pi-probe-turn', key.session_id, PROMPT)
    scope = {
        'server_id': key.server_id, 'executor_id': key.executor_id, 'session_id': key.session_id,
        'binding_id': 'binding', 'agent_id': 'agent', 'workspace_id': 'workspace',
        'workspace_binding_id': 'workspace-binding', 'session_owner_generation': 1,
        'authorization_revision': 1, 'configuration_revision': 1, 'binding_revision': 1, 'credential_epoch': 1,
    }
    channel = {'connection_id': 'connection', 'connection_generation': 1}
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
        if hosted_cli:
            assert host.has_hosted_pi_renderer(key.server_id, key.executor_id, key.session_id)
            provider, model = ('nexus-fixture', 'faux-1') if hosted_turn else ('openai', 'gpt-4.1-mini')
            intent = LaunchIntent('agent', 'workspace', 'pi_rpc', model=model,
                                  harness_settings=HarnessSettings(provider=provider))
            prepared = await runtime.prepare(intent, context)
            opened = await runtime.open(OpenOperation('pi-probe-open', key.session_id, 'epoch', prepared), context)
            assert opened.stage == 'SUBMITTED', opened
            target = NativeSessionTarget(opened.operation_id, 'pi_rpc', opened.native_id, cursor.stream_epoch)
            proof = await runtime.prove_live_native_session(scope, target, **channel)
            assert await host.read_r4_pi_session(scope, target, **channel) == {
                'native_session_id': opened.native_id, 'is_streaming': False,
                'is_compacting': False, 'pending_message_count': 0,
            }
            assert proof.process == await journal.get_process_birth(key)
            assert await journal.get_process_launch(key)
            renderer_facts = await exercise_hosted_renderer(runtime, host, journal, scope, target, channel,
                                                            context, turn, checkpoints, active_turn=hosted_turn)
            assert proof == await runtime.prove_live_native_session(scope, target, **channel)
            closed = await runtime.close(
                CloseOperation('pi-probe-close', key.session_id, 'End isolated probe', ShutdownPolicy(1, 1)),
                context, wait_for_completion=True,
            )
            assert closed.stage == 'SUCCEEDED', closed
            return {'core': __version__, 'production_factory': True, 'hosted_rpc_readiness': True, **renderer_facts,
                    'r4_live_process_proof': True, 'core_close_stage': closed.stage,
                    'turns_submitted': int(hosted_turn)}, opened.native_id
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
        if hosted_cli:
            await host.shutdown(ShutdownPolicy(1, 1))
        else:
            await runtime.shutdown(ShutdownPolicy(1, 1))
            journal.close()


async def exercise_hosted_renderer(runtime, host, journal, scope, target, channel, context, turn, checkpoints,
                                   *, active_turn):
    from nexus_connector_core import CoreError, OperationKey

    @asynccontextmanager
    async def attach():
        async with host.open_r4_pi_renderer(scope, target, **channel, columns=100, rows=36) as frames:
            yield frames

    async def observe(frames, expected=None):
        async with asyncio.timeout(10):
            output = bytearray()
            async for chunk in frames:
                output.extend(chunk)
                assert len(output) <= 256 * 1024
                if expected is None or expected.encode() in output:
                    return
        raise AssertionError('Pi renderer disconnected before producing the expected output')

    try:
        async with host.open_r4_pi_renderer(scope, replace(target, native_session_id='sibling'),
                                          **channel, columns=100, rows=36):
            raise AssertionError('Foreign native session admitted')
    except CoreError as error:
        assert error.code == 'SESSION_CONFLICT'

    async with attach() as first:
        await observe(first)
        try:
            async with attach():
                raise AssertionError('Second concurrent renderer admitted')
        except CoreError as error:
            assert error.code == 'NATIVE_UNAVAILABLE'
        if active_turn:
            submitted = await runtime.submit(turn, context)
            assert submitted.stage == 'SUBMITTED'
            await observe(first, PROMPT)
            assert (await runtime.read_live_pi_session(scope, target, **channel))['is_streaming']

    # Wait for the socket close to reach the renderer before requesting the same owner again.
    if active_turn:
        detached = await runtime.read_live_pi_session(scope, target, **channel)
        assert detached['native_session_id'] == target.native_session_id and detached['is_streaming']
    deadline = time.monotonic() + 5
    while True:
        try:
            async with attach() as second:
                await observe(second, PROMPT if active_turn else None)
                if active_turn:
                    assert await runtime.submit(turn, context) == submitted
                    (checkpoints / 'release-hosted-turn').touch()
                    await observe(second, RESULT)
            break
        except CoreError as error:
            if error.code != 'NATIVE_UNAVAILABLE' or time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.03)
    if active_turn:
        await wait_for_turn(journal, OperationKey(scope['server_id'], scope['executor_id'], turn.operation_id))
    return {'renderer_reattached': True, 'foreign_and_second_viewer_refused': True,
            'renderer_saw_turn_across_detach': active_turn}


def fingerprints(node, release, script):
    namespace = release / 'node_modules' / '@earendil-works'
    installed = namespace / 'pi-coding-agent'
    inputs = {
        'node': node,
        'probe': script,
        'cli_main': installed / 'dist/main.js',
        'cli_setup': installed / 'dist/cli/setup.js',
        'cli_modes': installed / 'dist/modes/index.js',
        'pi_package': installed / 'package.json',
        'pi_sdk': installed / 'dist/index.js',
        'interactive_mode': installed / 'dist/modes/interactive/interactive-mode.js',
        'rpc_mode': installed / 'dist/modes/rpc/rpc-mode.js',
        'faux_provider': namespace / 'pi-ai/dist/providers/faux.js',
    }
    return {name: hashlib.sha256(file.read_bytes()).hexdigest() for name, file in inputs.items()}


def run(node, release, *, core, cli_owner, hosted_core, hosted_turn):
    root = Path(tempfile.mkdtemp(prefix='nexus-si-pi-observer-')).resolve()
    script = root / 'probe.mjs'
    shutil.copyfile(Path(__file__).with_suffix('.mjs'), script)
    project, agent, checkpoints = root / 'project', root / 'agent', root / 'checkpoints'
    for directory in (project, agent, checkpoints, root / 'bin', root / 'tmp', root / 'appdata', root / 'local'):
        directory.mkdir()
    # Pi's discovery walks ancestors looking for this boundary.
    (project / '.git').mkdir()
    (project / '.git/HEAD').write_text('ref: refs/heads/fixture\n', encoding='ascii')
    if cli_owner:
        (agent / 'settings.json').write_text(json.dumps({'defaultThinkingLevel': 'low'}), encoding='utf-8')
        project_config = project / '.pi'
        project_config.mkdir()
        (project_config / 'settings.json').write_text(json.dumps({'defaultThinkingLevel': 'high'}), encoding='utf-8')
        for config, command in ((agent, 'nexus-profile-command'), (project_config, 'nexus-unapproved-command')):
            extensions = config / 'extensions'
            extensions.mkdir()
            (extensions / 'probe.js').write_text(
                f'export default (pi) => pi.registerCommand({json.dumps(command)}, {{handler() {{}}}});\n',
                encoding='utf-8',
            )
        skill = agent / 'skills' / 'nexus-owner-skill'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text(
            '---\nname: nexus-owner-skill\ndescription: Disposable owner proof\n---\n# Fixture skill\n',
            encoding='utf-8',
        )
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'COMSPEC') if key in os.environ}
    env.update({
        'PATH': str(root / 'bin'), 'PATHEXT': '.COM;.EXE', 'HOME': str(root), 'USERPROFILE': str(root),
        'APPDATA': str(root / 'appdata'), 'LOCALAPPDATA': str(root / 'local'),
        'TMP': str(root / 'tmp'), 'TEMP': str(root / 'tmp'), 'PI_CODING_AGENT_DIR': str(agent),
        'PI_OFFLINE': '1', 'TERM': 'xterm-256color',
    })
    hosted = None
    if cli_owner or hosted_core:
        from nexus_connector_core.pi_extension_resource import pi_hosted_rpc_path

        hosted = pi_hosted_rpc_path()
    cli = release / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'
    argv = [
        str(node), '--permission', f'--allow-fs-read={release}', f'--allow-fs-read={root}',
        f'--allow-fs-write={root}', str(script), str(release), str(project), str(agent), str(checkpoints),
    ]
    if cli_owner:
        argv.insert(4, f'--allow-fs-read={hosted.parent}')
        argv.extend(('--cli-owner', str(hosted)))
    print(f'Isolated probe directory {root}', flush=True)
    if hosted_core:
        (project / '.pi').mkdir()
        (project / '.pi/settings.json').write_text('{}', encoding='utf-8')
        preload = root / 'isolated-cli.mjs'
        preload.write_text(
            'import net from "node:net";\n'
            'const denyNetwork = () => { throw new Error("Network forbidden in the hosted Pi probe"); };\n'
            'net.Socket.prototype.connect = denyNetwork;\n'
            'globalThis.fetch = denyNetwork;\n'
            'process.argv.push("--no-context-files");\n'
            + ('process.argv.push("--api-key", "synthetic-fixture-token");\n' if hosted_turn else ''),
            encoding='utf-8',
        )
        if hosted_turn:
            extension = agent / 'extensions' / 'synthetic-provider.js'
            extension.parent.mkdir()
            provider = release / 'node_modules/@earendil-works/pi-ai/dist/providers/faux.js'
            extension.write_text(
                f'import {{ fauxProvider, fauxAssistantMessage }} from {json.dumps(provider.as_uri())};\n'
                'import { access } from "node:fs/promises";\n'
                'import { setTimeout as delay } from "node:timers/promises";\n'
                'export default (pi) => {\n'
                '  const faux = fauxProvider({ provider: "nexus-fixture", api: "nexus-fixture" });\n'
                '  pi.registerProvider(faux.provider);\n'
                '  faux.setResponses([async () => {\n'
                '    for (let count = 0; count < 500; count++) {\n'
                f'      try {{ await access({json.dumps(str(checkpoints / "release-hosted-turn"))});'
                f' return fauxAssistantMessage({json.dumps(RESULT)}); }}\n'
                '      catch (error) { if (error.code !== "ENOENT") throw error; }\n'
                '      await delay(30);\n'
                '    }\n'
                '    throw new Error("Hosted renderer probe did not release the turn");\n'
                '  }]);\n'
                '};\n', encoding='utf-8',
            )
        else:
            env['OPENAI_API_KEY'] = 'synthetic-fixture-key'
        env['NODE_OPTIONS'] = ' '.join((
            '--permission', f'--allow-fs-read="{release.as_posix()}"', f'--allow-fs-read="{root.as_posix()}"',
            f'--allow-fs-read="{hosted.parent.as_posix()}"', f'--allow-fs-write="{root.as_posix()}"',
            f'--import={preload.as_uri()}',
        ))
        report, session_id = asyncio.run(exercise_core(argv, env, root, checkpoints, None, hosted_cli=cli,
                                                       hosted_turn=hosted_turn))
        histories = list((agent / 'sessions').rglob('*.jsonl'))
        if hosted_turn:
            assert len(histories) == 1
            verify_history(agent / 'sessions', histories[0], session_id)
        else:
            assert not histories
        report['exact_persisted_history'] = True
        report['hosted_rpc_sha256'] = hashlib.sha256(hosted.read_bytes()).hexdigest()
        print(json.dumps(report, sort_keys=True))
        return
    if core:
        version_command = [*argv[:argv.index(str(script))], str(cli), '--version']
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
    parser.add_argument('--cli-owner', action='store_true', help='Use the official unbundled Pi CLI to open the owner')
    parser.add_argument('--hosted-core', action='store_true', help='Open the packaged owner via the real Core composition')
    parser.add_argument('--hosted-turn', action='store_true', help='Exercise the private renderer with one synthetic turn')
    args = parser.parse_args()
    if args.hosted_core and (args.core or args.cli_owner):
        parser.error('--hosted-core selects the real Core launch path')
    if args.hosted_turn and not args.hosted_core:
        parser.error('--hosted-turn requires --hosted-core')
    run(args.node.resolve(strict=True), args.pi_release.resolve(strict=True),
        core=args.core, cli_owner=args.cli_owner, hosted_core=args.hosted_core, hosted_turn=args.hosted_turn)
