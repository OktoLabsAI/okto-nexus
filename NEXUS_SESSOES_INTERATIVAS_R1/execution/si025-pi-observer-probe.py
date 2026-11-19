"""Exercise the installed Pi renderer and RPC owner in an isolated process."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from queue import Empty, Queue

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


def run(node, release):
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
    verify_history(agent / 'sessions', session_file, report.pop('sessionId'))
    report.update({
        'rpc_continued_while_detached': True, 'exact_persisted_history': True,
        'native_rpc_owner_exit': 0, 'disposals_after_rpc_eof': 1, 'sha256': fingerprints(node, release, script),
    })
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--pi-release', type=Path, required=True, help='Pi release root containing node_modules')
    args = parser.parse_args()
    run(args.node.resolve(strict=True), args.pi_release.resolve(strict=True))
