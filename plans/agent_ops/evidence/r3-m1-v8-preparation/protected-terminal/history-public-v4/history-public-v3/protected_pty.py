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
import threading

sys.path.insert(0, str(Path(__file__).parent))
from owned_job import Job, birth

HERE = Path(__file__).parent
BASE_PYTHON = Path('C:/Python313/python.exe')
SITE = HERE.parent / 'venv/Lib/site-packages'
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

def _worker(spec, progress):
    # Parent assigns and verifies this worker before sending the stdin gate.
    sys.path.insert(0, str(SITE))
    from winpty import PTY, Backend, WinptyError
    assert job_identity(spec['job_name'], os.getpid())['exact_job_member']
    deadline = time.monotonic() + spec['timeout_seconds']
    pty = PTY(240, 60, backend=Backend.ConPTY)
    producer = spec['producer_argv']
    assert pty.spawn(producer[0], cmdline=' ' + subprocess.list2cmdline(producer[1:]),
                     cwd=spec['cwd'], env='\0'.join(k + '=' + v for k, v in spec['env'].items()) + '\0')
    progress.update(producer_started=True, possible_effect=True,
                    producer=job_identity(spec['job_name'], pty.pid))
    raw = ''
    material = None
    consumer = None
    io_thread = None
    io_done = threading.Event()
    io_result = {}
    eof = False
    empty_after_exit = 0
    try:
        if spec.get('synthetic_probe'):
            pty.write('go\r\n')
        while True:
            chunk = ''
            if not eof:
                try:
                    chunk = pty.read(blocking=False)
                except WinptyError:
                    if pty.isalive():
                        raise
                    eof = True
                raw += chunk
                if len(raw) > 131072:
                    raise TransferError('PTY_OUTPUT_LIMIT')
            alive = pty.isalive()
            if not alive:
                progress['producer_exit'] = pty.get_exitstatus()
                if progress['producer_exit'] != 0:
                    raise TransferError('PRODUCER_NONZERO')
                empty_after_exit = empty_after_exit + 1 if not chunk else 0
                if empty_after_exit >= 5:
                    eof = True
            clean = ANSI.sub('', raw).replace('\r', '')
            if time.monotonic() >= deadline:
                raise TransferError('TRANSFER_DEADLINE')
            # Deliver at the complete block, not process exit. The real producer
            # waits for the consumer to finish materialization before it exits.
            if FOOTER in clean:
                candidate = extract(raw)
                if material is not None and candidate != material:
                    raise TransferError('MATERIAL_CHANGED_AFTER_DELIVERY')
                if consumer is None:
                    material = candidate
                    if any(material in arg for arg in producer + spec['consumer_argv']):
                        raise TransferError('MATERIAL_IN_ARGV')
                    if any(material in value for mapping in (spec['env'], spec['consumer_env']) for value in mapping.values()):
                        raise TransferError('MATERIAL_IN_ENV')
                    startup = subprocess.STARTUPINFO()
                    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startup.wShowWindow = subprocess.SW_HIDE
                    consumer = subprocess.Popen(spec['consumer_argv'], cwd=spec['cwd'], env=spec['consumer_env'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
                    progress.update(consumer_started=True, possible_consumer_effect=True,
                                    consumer_start_count=1, producer_alive_at_consumer_start=alive,
                                    consumer=job_identity(spec['job_name'], consumer.pid))
                    progress['delivery_attempted'] = True

                    def communicate_once():
                        try:
                            io_result['output'], io_result['error'] = consumer.communicate((material + '\n').encode())
                        except BaseException as error:
                            io_result['failure_type'] = type(error).__name__
                        finally:
                            io_done.set()

                    # One owned I/O worker, no transcript and no second delivery.
                    # On timeout the outer exact Job contains this whole worker
                    # plus every disposable child; there is no detached thread.
                    io_thread = threading.Thread(target=communicate_once, daemon=True)
                    io_thread.start()
            if consumer is not None and io_done.is_set():
                io_thread.join()
                progress['consumer_io_completed'] = True
                progress['consumer_exit'] = consumer.returncode
                if 'failure_type' in io_result:
                    raise TransferError('CONSUMER_IO_FAILED')
                if material.encode() in io_result['output'] or material.encode() in io_result['error']:
                    raise TransferError('CONSUMER_ECHOED_MATERIAL')
                if consumer.returncode != 0:
                    raise TransferError('CONSUMER_NONZERO')
                if eof:
                    break
            if eof and consumer is None:
                raise TransferError('MATERIAL_MISSING')
            if time.monotonic() >= deadline:
                raise TransferError('TRANSFER_DEADLINE')
            time.sleep(.01)
        result = {**progress, 'status': 'TRANSFERRED_ONCE', 'material_in_public_result': False,
                  'material_in_argv_or_env': False, 'consumer_did_not_echo': True}
        if spec.get('synthetic_probe'):
            clean = ANSI.sub('', raw).replace('\r', '')
            match = re.search(r'PTY_PROBE (\{[^\n]+\})', clean)
            probe = json.loads(match.group(1)) if match else {}
            expected = hashlib.sha256(material.encode()).hexdigest().encode()
            assert io_result['output'].strip() == expected
            assert probe.get('streams') == {'stdin': True, 'stdout': True, 'stderr': True}
            assert probe.get('visible') is False
            result.update(tty_probe=probe, consumer_material_matches=True)
            for path in Path(spec['cwd']).rglob('*'):
                if path.is_file() and material.encode() in path.read_bytes():
                    raise TransferError('MATERIAL_PERSISTED')
            result['material_absent_from_synthetic_files'] = True
        return result
    finally:
        raw = None
        # Do not wait indefinitely for consumer I/O after a failure. The parent
        # closes the exact Job, then observes active0. No service belongs here.
        del pty

def transfer_once(*, producer_argv, consumer_argv, env, cwd, timeout_seconds=30, synthetic_probe=False, consumer_env=None):
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
    result = {'status': 'UNCONFIRMED', 'possible_effect': True, 'delivery_attempted': None, 'consumer_started': None, 'worker_pid': worker.pid,
              'worker_birth_filetime': birth(worker._handle), 'forced_owned_cleanup': False}
    try:
        job.assign(worker)  # the worker is waiting only for the gate, no PTY yet
        result['worker_assigned_before_gate'] = True
        spec = {'job_name': job.name, 'producer_argv': producer_argv, 'consumer_argv': consumer_argv,
                'env': env, 'consumer_env': env if consumer_env is None else consumer_env,
                'cwd': str(cwd), 'timeout_seconds': timeout_seconds,
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
        if result['status'] == 'TRANSFERRED_ONCE' and (result['forced_owned_cleanup'] or result['active_job_processes_after']):
            result.update(status='UNCONFIRMED', reason='OWNED_DESCENDANTS_UNCONFIRMED', possible_effect=True)
        return result
    finally:
        if worker.poll() is None:
            # Before assignment failure the worker gate still prevents any
            # descendants; this targets the retained Popen handle only.
            worker.kill()
            worker.wait(timeout=5)
        job.close()

if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    progress = {'producer_started': False, 'consumer_started': False, 'consumer_start_count': 0,
                'delivery_attempted': False, 'possible_effect': False, 'possible_consumer_effect': False,
                'consumer_io_completed': False}
    try:
        result = _worker(json.loads(sys.stdin.buffer.read()), progress)
    except BaseException as error:
        result = {**progress, 'status': 'UNCONFIRMED', 'error_type': type(error).__name__}
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
