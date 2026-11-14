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
import queue
import math

sys.path.insert(0, str(Path(__file__).parent))
from owned_job import Job, birth

HERE = Path(__file__).parent
BASE_PYTHON = Path('C:/Python313/python.exe')
SITE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/venv/Lib/site-packages')
HEADER = 'Canonical agent key â€” shown once. Paste it into the Connector masked prompt:'
FOOTER = 'Keep this key if you need to resume import; the Server cannot recover its plaintext.'
READY_PREFIX = 'Host handoff (contains no key): '
KEY = re.compile(r'nxs_[0-9a-f]{48}')
ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))')

class TransferError(RuntimeError):
    pass


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise TransferError('IPC_DUPLICATE_KEY')
            value[key] = item
        return value
    def invalid(_):
        raise TransferError('IPC_NONFINITE')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError):
        raise TransferError('IPC_INVALID_JSON') from None


class _Lines:
    """One retained bounded pipe reader. No raw bytes are published."""
    def __init__(self, pipe, *, limit=65536, total=131072):
        self.pipe, self.limit, self.total = pipe, limit, total
        self.frames = queue.Queue(maxsize=8)
        self.error = None
        self.bytes = 0
        self.thread = threading.Thread(target=self._read, daemon=True, name='pty-public-ipc')
        self.thread.start()

    def _read(self):
        try:
            while True:
                raw = self.pipe.readline(self.limit + 1)
                if not raw:
                    self.frames.put_nowait(None)
                    return
                self.bytes += len(raw)
                if len(raw) > self.limit or self.bytes > self.total or not raw.endswith(b'\n'):
                    raise TransferError('IPC_FRAME_LIMIT')
                self.frames.put_nowait(raw)
        except BaseException:
            self.error = 'IPC_READER_FAILED'

    def next(self, deadline):
        while True:
            if self.error:
                raise TransferError(self.error)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransferError('TRANSFER_DEADLINE')
            try:
                raw = self.frames.get(timeout=min(.05, remaining))
            except queue.Empty:
                continue
            if raw is None:
                raise TransferError('IPC_EOF')
            if KEY.search(raw.decode('utf-8', errors='replace')):
                raise TransferError('IPC_MATERIAL_FORBIDDEN')
            return _json(raw)


def _reply_allowed(value, phase, sequence):
    if (type(value) is not dict or set(value) != {'kind', 'phase', 'sequence', 'allow'}
            or value['kind'] != 'effect_gate_reply' or value['phase'] != phase
            or type(value['sequence']) is not int or value['sequence'] != sequence
            or type(value['allow']) is not bool):
        raise TransferError('IPC_GATE_REPLY_INVALID')
    return value['allow']


def _request_gate(phase, sequence, inbox, deadline, progress):
    progress['effect_gates_requested'].append(phase)
    print(json.dumps({'kind': 'effect_gate', 'phase': phase, 'sequence': sequence}), flush=True)
    allowed = _reply_allowed(inbox.next(deadline), phase, sequence)
    if time.monotonic() >= deadline:
        raise TransferError('TRANSFER_DEADLINE')
    if not allowed:
        raise TransferError('EFFECT_GUARD_DENIED')
    progress['effect_gates_allowed'].append(phase)


class _Protocol:
    """Only producer, then consumer, then one terminal result is accepted."""
    def __init__(self):
        self.requested = []
        self.allowed = []
        self.finished = False

    def gate(self, value):
        if (self.finished or type(value) is not dict or set(value) != {'kind', 'phase', 'sequence'}
                or value['kind'] != 'effect_gate' or len(self.requested) >= 2
                or value['phase'] != ('producer', 'consumer')[len(self.requested)]
                or type(value['sequence']) is not int or value['sequence'] != len(self.requested) + 1
                or (self.requested and self.allowed != ['producer'])):
            raise TransferError('IPC_GATE_ORDER_INVALID')
        self.requested.append(value['phase'])
        return value['phase'], value['sequence']

    def finish(self, value):
        allowed_keys = {'producer_started','consumer_started','consumer_start_count','delivery_attempted',
            'possible_effect','possible_consumer_effect','consumer_io_completed','producer','consumer',
            'producer_exit','consumer_exit','producer_alive_at_consumer_start','consumer_ready_marker_observed',
            'material_block_observed','material_seen_before_ready_marker','status','material_in_public_result',
            'material_in_argv_or_env','consumer_did_not_echo','tty_probe','consumer_material_matches',
            'material_absent_from_synthetic_files','error_type','error_frames','reason',
            'effect_gates_requested','effect_gates_allowed','dependency_probe'}
        if (self.finished or type(value) is not dict or set(value) != {'kind', 'result'}
                or value['kind'] != 'result' or type(value['result']) is not dict):
            raise TransferError('IPC_RESULT_INVALID')
        result = value['result']
        if (not set(result) <= allowed_keys or result.get('status') not in ('UNCONFIRMED','TRANSFERRED_ONCE')
                or result.get('effect_gates_requested') != self.requested
                or type(result.get('effect_gates_allowed')) is not list
                or result['effect_gates_allowed'] != self.allowed[:len(result['effect_gates_allowed'])]
                or len(result['effect_gates_allowed']) > len(self.allowed)
                or any(type(result.get(name)) is not bool for name in
                    ('producer_started','consumer_started','delivery_attempted','possible_effect',
                     'possible_consumer_effect','consumer_io_completed'))
                or type(result.get('consumer_start_count')) is not int
                or result['consumer_start_count'] not in (0, 1)):
            raise TransferError('IPC_RESULT_INVALID')
        if result['status'] == 'TRANSFERRED_ONCE' and not (
                self.allowed == ['producer', 'consumer'] and result['producer_started']
                and result['consumer_started'] and result['delivery_attempted']
                and result['consumer_start_count'] == 1 and result.get('producer_exit') == 0
                and result.get('consumer_exit') == 0):
            raise TransferError('IPC_SUCCESS_UNCONFIRMED')
        self.finished = True
        return result

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

def _worker(spec, progress, inbox):
    # Parent assigns and verifies this worker before sending the stdin gate.
    sys.path.insert(0, str(SITE))
    import winpty
    from winpty import PTY, Backend, WinptyError
    assert Path(winpty.__file__).resolve() == (SITE / 'winpty/__init__.py').resolve()
    if spec.get('synthetic_probe'):
        extension = Path(sys.modules['winpty.winpty'].__file__).resolve()
        assert extension.is_relative_to(SITE.resolve())
        progress['dependency_probe'] = {'module': str(Path(winpty.__file__).resolve()),
            'module_sha256': hashlib.sha256(Path(winpty.__file__).read_bytes()).hexdigest(),
            'extension': str(extension), 'extension_sha256': hashlib.sha256(extension.read_bytes()).hexdigest()}
    assert job_identity(spec['job_name'], os.getpid())['exact_job_member']
    deadline = spec['deadline_monotonic']
    _request_gate('producer', 1, inbox, deadline, progress)
    pty = PTY(240, 60, backend=Backend.ConPTY)
    producer = spec['producer_argv']
    if time.monotonic() >= deadline:
        raise TransferError('TRANSFER_DEADLINE')
    progress['possible_effect'] = True
    assert pty.spawn(producer[0], cmdline=' ' + subprocess.list2cmdline(producer[1:]),
                     cwd=spec['cwd'], env='\0'.join(k + '=' + v for k, v in spec['env'].items()) + '\0')
    progress.update(producer_started=True, possible_effect=True)
    progress['producer'] = job_identity(spec['job_name'], pty.pid)
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
            marker = spec.get('consumer_ready_marker')
            ready = marker is None
            if marker is not None:
                # Only complete lines count. A path prefix or another handoff
                # marker does not authorize importing this one-shot material.
                announced = [line for line in clean.split('\n')[:-1] if line.startswith(READY_PREFIX)]
                if announced:
                    if len(announced) != 1 or announced[0] != marker:
                        raise TransferError('CONSUMER_READY_MARKER_MISMATCH')
                    ready = True
                    progress['consumer_ready_marker_observed'] = True
            # Deliver at the complete block, not process exit. The real producer
            # waits for the consumer to finish materialization before it exits.
            if FOOTER in clean:
                candidate = extract(raw)
                if material is not None and candidate != material:
                    raise TransferError('MATERIAL_CHANGED_AFTER_DELIVERY')
                if material is None:
                    material = candidate
                    progress['material_block_observed'] = True
                    progress['material_seen_before_ready_marker'] = marker is not None and not ready
                if consumer is None and ready:
                    if any(material in arg for arg in producer + spec['consumer_argv']):
                        raise TransferError('MATERIAL_IN_ARGV')
                    if any(material in value for mapping in (spec['env'], spec['consumer_env']) for value in mapping.values()):
                        raise TransferError('MATERIAL_IN_ENV')
                    _request_gate('consumer', 2, inbox, deadline, progress)
                    startup = subprocess.STARTUPINFO()
                    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startup.wShowWindow = subprocess.SW_HIDE
                    if time.monotonic() >= deadline:
                        raise TransferError('TRANSFER_DEADLINE')
                    progress['possible_consumer_effect'] = True
                    consumer = subprocess.Popen(spec['consumer_argv'], cwd=spec['cwd'], env=spec['consumer_env'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
                    progress.update(consumer_started=True, possible_consumer_effect=True,
                                    consumer_start_count=1, producer_alive_at_consumer_start=alive)
                    progress['consumer'] = job_identity(spec['job_name'], consumer.pid)
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
                if material is not None and marker is not None:
                    raise TransferError('CONSUMER_READY_MARKER_MISSING')
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

def transfer_once(*, producer_argv, consumer_argv, env, cwd, timeout_seconds=30, synthetic_probe=False,
                  consumer_env=None, consumer_ready_marker=None, effect_guard=None, deadline_monotonic=None):
    """Caller owns authorization and supplies a bounded fresh-accounting guard.

    The guard runs on this transfer thread. It must return literal True within
    the transfer deadline, and must not mutate an owner-only controller here.
    A future caller bridges the request to that controller's own polling thread.
    Denial never replays a CLI or key delivery. A gate cannot cancel a CLI that
    already started; cleanup owns only this auxiliary Job and its descendants.
    """
    if not 1 <= timeout_seconds <= 120:
        raise ValueError('invalid deadline')
    if not callable(effect_guard):
        raise ValueError('explicit effect guard required')
    for argv in (producer_argv, consumer_argv):
        if not argv or not Path(argv[0]).is_absolute() or any(KEY.search(item) for item in argv):
            raise ValueError('public absolute argv required')
    if consumer_ready_marker is not None:
        if (type(consumer_ready_marker) is not str or not consumer_ready_marker.isprintable()
                or not consumer_ready_marker.startswith(READY_PREFIX)
                or not Path(consumer_ready_marker[len(READY_PREFIX):]).is_absolute()
                or KEY.search(consumer_ready_marker)):
            raise ValueError('public canonical handoff marker required')
    deadline = time.monotonic() + timeout_seconds
    if deadline_monotonic is not None:
        if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
            raise ValueError('finite shared deadline required')
        deadline = min(deadline, deadline_monotonic)
    if deadline <= time.monotonic():
        raise TransferError('TRANSFER_DEADLINE')
    job = Job()
    worker = None
    output_reader = None
    error_reader = None
    protocol = _Protocol()
    decisions = []
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    result = {'status': 'UNCONFIRMED', 'possible_effect': True, 'delivery_attempted': None,
              'consumer_started': None, 'forced_owned_cleanup': False,
              'effect_guard_decisions': decisions, 'effect_guard_required': True}
    try:
        worker = subprocess.Popen([str(BASE_PYTHON), '-I', '-B', str(HERE / 'protected_pty.py'), '--worker'],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        result['worker_pid'] = worker.pid
        result['worker_birth_filetime'] = birth(worker._handle)
        job.assign(worker)  # the worker is waiting only for the gate, no PTY yet
        result['worker_assigned_before_gate'] = True
        output_reader = _Lines(worker.stdout)
        error_reader = _Lines(worker.stderr, limit=4096, total=8192)
        spec = {'job_name': job.name, 'producer_argv': producer_argv, 'consumer_argv': consumer_argv,
                'env': env, 'consumer_env': env if consumer_env is None else consumer_env,
                'cwd': str(cwd), 'timeout_seconds': timeout_seconds,
                'deadline_monotonic': deadline,
                'consumer_ready_marker': consumer_ready_marker,
                'synthetic_probe': synthetic_probe}
        raw = json.dumps(spec, allow_nan=False).encode('utf-8') + b'\n'
        if len(raw) > 65536:
            raise TransferError('IPC_SPEC_LIMIT')
        worker.stdin.write(raw)
        worker.stdin.flush()
        try:
            while not protocol.finished:
                value = output_reader.next(deadline)
                if type(value) is dict and value.get('kind') == 'effect_gate':
                    phase, sequence = protocol.gate(value)
                    decision = {'phase': phase, 'allowed': False}
                    if time.monotonic() < deadline:
                        try:
                            decision['allowed'] = effect_guard(phase) is True
                        except BaseException as error:
                            decision['error_type'] = type(error).__name__
                    if time.monotonic() >= deadline:
                        decision.update(allowed=False, deadline_expired=True)
                    decisions.append(decision)
                    if decision['allowed']:
                        protocol.allowed.append(phase)
                    reply = {'kind': 'effect_gate_reply', 'phase': phase,
                             'sequence': sequence, 'allow': decision['allowed']}
                    worker.stdin.write(json.dumps(reply).encode('utf-8') + b'\n')
                    worker.stdin.flush()
                else:
                    result.update(protocol.finish(value))
            worker.stdin.close()
            # Only auxiliary cleanup remains. This interval does not authorize
            # any new producer/consumer after the single transfer deadline.
            try:
                worker.wait(timeout=max(.01, min(5, deadline - time.monotonic() + 1)))
            except subprocess.TimeoutExpired:
                result.update(status='OWNER_DEADLINE', possible_effect=True)
        except (TransferError, BrokenPipeError, OSError) as error:
            result.update(status='UNCONFIRMED', error_type=type(error).__name__)
            if type(error) is TransferError:
                result['reason'] = error.args[0]
        teardown_until = time.monotonic() + 1
        while worker.poll() is not None and job.active() and time.monotonic() < teardown_until:
            time.sleep(.01)
        if worker.poll() is None or job.active():
            job.terminate()
            result['forced_owned_cleanup'] = True
            worker.wait(timeout=5)
        until = time.monotonic() + 5
        while job.active() and time.monotonic() < until:
            time.sleep(.01)
        if worker.stdin and not worker.stdin.closed:
            worker.stdin.close()
        for reader in (output_reader, error_reader):
            reader.thread.join(timeout=5)
        result['public_ipc_readers_joined'] = not any(r.thread.is_alive() for r in (output_reader, error_reader))
        result['worker_stderr_observed'] = bool(error_reader.bytes or error_reader.error)
        result['active_job_processes_after'] = job.active()
        result['worker_exit'] = worker.returncode
        # A second result or any data after the final frame is never accepted.
        extra = []
        while not output_reader.frames.empty():
            extra.append(output_reader.frames.get_nowait())
        protocol_error = output_reader.error or any(frame is not None for frame in extra)
        if result['status'] == 'TRANSFERRED_ONCE' and (result['forced_owned_cleanup'] or result['active_job_processes_after']
                or worker.returncode != 0 or not result['public_ipc_readers_joined']
                or result['worker_stderr_observed'] or protocol_error):
            result.update(status='UNCONFIRMED', reason='OWNED_DESCENDANTS_UNCONFIRMED', possible_effect=True)
        return result
    finally:
        if worker is not None and worker.poll() is None:
            # Before assignment failure the worker gate still prevents any
            # descendants; this targets the retained Popen handle only.
            worker.kill()
            worker.wait(timeout=5)
        job.close()
        if worker is not None:
            for pipe in (worker.stdin, worker.stdout, worker.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    progress = {'producer_started': False, 'consumer_started': False, 'consumer_start_count': 0,
                'delivery_attempted': False, 'possible_effect': False, 'possible_consumer_effect': False,
                'consumer_io_completed': False, 'effect_gates_requested': [], 'effect_gates_allowed': []}
    inbox = None
    try:
        raw = sys.stdin.buffer.readline(65537)
        if len(raw) > 65536 or not raw.endswith(b'\n'):
            raise TransferError('IPC_SPEC_LIMIT')
        inbox = _Lines(sys.stdin.buffer, limit=1024, total=4096)
        result = _worker(_json(raw), progress, inbox)
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
    print(json.dumps({'kind': 'result', 'result': result}, allow_nan=False), flush=True)
    if inbox is not None:
        # Parent closes this public pipe after the terminal result. Join before
        # Python finalization so no reader owns stdin's buffered lock at exit.
        inbox.thread.join(timeout=5)
        if inbox.thread.is_alive():
            os._exit(4)
