"""Disposable ConPTY transfer helper. Raw terminal data never leaves the worker.

This module does not grant authorization. Its future caller must validate the
final proposal, approval, exact CLI arguments and package pins before invoking.
No product was invoked in its qualification: only synthetic Python children.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
from owned_job import Job, birth

HERE = Path(__file__).parent
BASE_PYTHON = Path('C:/Python313/python.exe')
SITE = HERE / 'venv/Lib/site-packages'
HEADER = 'Canonical agent key — shown once. Paste it into the Connector masked prompt:'
FOOTER = 'Keep this key if you need to resume import; the Server cannot recover its plaintext.'
KEY = re.compile(r'nxs_[0-9a-f]{48}')
ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))')

class TransferError(RuntimeError):
    pass

def extract(text):
    text = ANSI.sub('', text).replace('\r', '')
    matches = list(KEY.finditer(text))
    if len(matches) != 1 or text.count(HEADER) != 1 or text.count(FOOTER) != 1:
        raise TransferError('MATERIAL_NOT_UNIQUE')
    middle = text.split(HEADER, 1)[1].split(FOOTER, 1)[0].strip()
    if middle != matches[0].group():
        raise TransferError('MATERIAL_LAYOUT_UNCONFIRMED')
    return middle

def job_identity(name, pid):
    # Do not hold a second Job handle across child waits: the parent owns
    # kill-on-close. This query handle exists only during synchronous checks.
    job = Job(name)
    try:
        return job.identity(pid)
    finally:
        job.close()

def _worker(spec):
    # This branch cannot run before the parent assigns/verifies our process in
    # its Job and writes the gate message. Imports/PTY spawn happen only now.
    sys.path.insert(0, str(SITE))
    from winpty import PTY, Backend, WinptyError
    assert job_identity(spec['job_name'], os.getpid())['exact_job_member']
    deadline = time.monotonic() + spec['timeout_seconds']
    pty = PTY(240, 60, backend=Backend.ConPTY)
    producer = spec['producer_argv']
    assert pty.spawn(producer[0], cmdline=' ' + subprocess.list2cmdline(producer[1:]),
                     cwd=spec['cwd'], env='\0'.join(k + '=' + v for k, v in spec['env'].items()) + '\0')
    identity = job_identity(spec['job_name'], pty.pid)
    raw = ''
    try:
        # A synthetic producer waits for this gate so identity is captured
        # before its benign one-shot output. Real CLI mode has no extra input.
        if spec.get('synthetic_probe'):
            pty.write('go\r\n')
        while True:
            try:
                chunk = pty.read(blocking=False)
            except WinptyError:
                if not pty.isalive():
                    break
                raise
            raw += chunk
            if len(raw) > 131072:
                raise TransferError('PTY_OUTPUT_LIMIT')
            if time.monotonic() >= deadline:
                raise TransferError('PRODUCER_DEADLINE')
            if not pty.isalive():
                # Drain pending ConPTY display frames after process exit.
                for _ in range(5):
                    try:
                        raw += pty.read(blocking=False)
                    except WinptyError:
                        if not pty.isalive():
                            break
                        raise
                    time.sleep(.02)
                break
            time.sleep(.01)
        if pty.get_exitstatus() != 0:
            raise TransferError('PRODUCER_NONZERO')
        material = extract(raw)
        if any(material in argument for argument in producer + spec['consumer_argv']):
            raise TransferError('MATERIAL_IN_ARGV')
        if any(material in value for value in spec['env'].values()):
            raise TransferError('MATERIAL_IN_ENV')
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        consumer = subprocess.Popen(spec['consumer_argv'], cwd=spec['cwd'], env=spec['env'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        consumer_identity = job_identity(spec['job_name'], consumer.pid)
        output, error = consumer.communicate((material + '\n').encode(), timeout=max(.01, deadline - time.monotonic()))
        if material.encode() in output or material.encode() in error:
            raise TransferError('CONSUMER_ECHOED_MATERIAL')
        if consumer.returncode != 0:
            raise TransferError('CONSUMER_NONZERO')
        result = {'status': 'TRANSFERRED_ONCE', 'producer': identity, 'consumer': consumer_identity,
                  'producer_exit': 0, 'consumer_exit': 0, 'material_in_public_result': False,
                  'material_in_argv_or_env': False, 'consumer_did_not_echo': True}
        if spec.get('synthetic_probe'):
            clean = ANSI.sub('', raw).replace('\r', '')
            match = re.search(r'PTY_PROBE (\{[^\n]+\})', clean)
            probe = json.loads(match.group(1)) if match else {}
            expected = hashlib.sha256(material.encode()).hexdigest().encode()
            assert output.strip() == expected
            assert probe.get('streams') == {'stdin': True, 'stdout': True, 'stderr': True}
            assert probe.get('visible') is False
            result.update(tty_probe=probe, consumer_material_matches=True)
            for path in Path(spec['cwd']).rglob('*'):
                if path.is_file() and material.encode() in path.read_bytes():
                    raise TransferError('MATERIAL_PERSISTED')
            result['material_absent_from_synthetic_files'] = True
        return result
    finally:
        # No stdout/raw terminal text and no secret-bearing exception text.
        raw = None
        # No blocking reader exists: ConPTY does not implement cancel_io in
        # this release. Drop its owner; the outer exact Job remains the fence.
        del pty

def transfer_once(*, producer_argv, consumer_argv, env, cwd, timeout_seconds=30, synthetic_probe=False):
    if not 1 <= timeout_seconds <= 120:
        raise ValueError('invalid deadline')
    for argv in (producer_argv, consumer_argv):
        if not argv or not Path(argv[0]).is_absolute() or any(KEY.search(item) for item in argv):
            raise ValueError('public absolute argv required')
    job = Job()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    worker = subprocess.Popen([str(BASE_PYTHON), '-I', str(HERE / 'protected_pty.py'), '--worker'],
        cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    result = {'status': 'UNCONFIRMED', 'worker_pid': worker.pid,
              'worker_birth_filetime': birth(worker._handle), 'forced_owned_cleanup': False}
    try:
        job.assign(worker)  # the worker is waiting only for the gate, no PTY yet
        result['worker_assigned_before_gate'] = True
        spec = {'job_name': job.name, 'producer_argv': producer_argv, 'consumer_argv': consumer_argv,
                'env': env, 'cwd': str(cwd), 'timeout_seconds': timeout_seconds,
                'synthetic_probe': synthetic_probe}
        try:
            output, error = worker.communicate(json.dumps(spec).encode(), timeout=timeout_seconds + 5)
            if error or worker.returncode != 0:
                result['status'] = 'WORKER_UNCONFIRMED'
            else:
                result.update(json.loads(output))
        except subprocess.TimeoutExpired:
            result['status'] = 'OWNER_DEADLINE'
        teardown_until = time.monotonic() + 1
        while worker.poll() is not None and job.active() and time.monotonic() < teardown_until:
            time.sleep(.01)
        if worker.poll() is None or job.active():
            job.terminate()
            result['forced_owned_cleanup'] = True
            worker.communicate(timeout=5)
        until = time.monotonic() + 5
        while job.active() and time.monotonic() < until:
            time.sleep(.01)
        result['active_job_processes_after'] = job.active()
        result['worker_exit'] = worker.returncode
        return result
    finally:
        if worker.poll() is None:
            # Before assignment failure the worker gate still prevents any
            # descendants; this targets the retained Popen handle only.
            worker.kill()
            worker.wait(timeout=5)
        job.close()

if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    try:
        result = _worker(json.loads(sys.stdin.buffer.read()))
    except BaseException as error:
        result = {'status': 'UNCONFIRMED', 'error_type': type(error).__name__}
        frames = []
        trace = error.__traceback__
        while trace is not None:
            frames.append({'file': Path(trace.tb_frame.f_code.co_filename).name,
                           'function': trace.tb_frame.f_code.co_name, 'line': trace.tb_lineno})
            trace = trace.tb_next
        result['error_frames'] = frames
        if type(error) is TransferError:
            result['reason'] = error.args[0]
    print(json.dumps(result), flush=True)
