"""Attach only to the proven owned console; send y, then one scoped Ctrl-C."""
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from win import Owned, console_members, hidden_window, input_handle, kernel, same_image, write_y

(ROOT / 'controller-started.json').write_text(json.dumps(dict(pid=os.getpid(), parent_pid=os.getppid())))
deadline = time.monotonic() + 160
attached = False
handle = None
try:
    while not (ROOT / 'permit.json').exists():
        assert time.monotonic() < deadline, 'No ownership permit'
        time.sleep(.05)
    permit = json.loads((ROOT / 'permit.json').read_text())
    allowed = {row['pid']: row for row in permit['owned_processes']}
    assert os.getpid() in allowed and permit['child_main_pid'] in allowed
    kernel.FreeConsole()
    assert kernel.AttachConsole(permit['child_main_pid']), 'Cannot attach to the exact child console'
    attached = True
    assert kernel.SetConsoleCtrlHandler(None, True), 'Controller must ignore its own console Ctrl-C'
    handle = input_handle()

    def fence(stage):
        members = console_members()
        assert os.getpid() in members and permit['child_main_pid'] in members
        assert set(members) <= set(allowed), 'Unexpected console client: refusing input/signal'
        proofs = []
        for pid in members:
            process = Owned(pid)
            try:
                expected = allowed[pid]
                assert process.alive() and process.birth == expected['birth_filetime']
                assert same_image(process.image, expected['image'])
                proofs.append(process.facts())
            finally:
                process.close()
        window = hidden_window()
        assert not window['visible'] and window['hwnd'] == permit['console_window']['hwnd']
        value = dict(stage=stage, members=members, proofs=proofs, window=window)
        (ROOT / ('console-proof-' + stage + '.json')).write_text(json.dumps(value, indent=2))
        return value

    log = ROOT / 'child.log'
    prompt = b'Confirm this review, including the model connection test? [y/customize/cancel] '
    while prompt not in log.read_bytes():
        assert time.monotonic() < deadline, 'No exact review prompt; no input sent'
        assert not (ROOT / 'child-result.json').exists()
        time.sleep(.05)
    fence('before-input')
    with (ROOT / 'input-intent.json').open('x') as output:
        json.dump(dict(pid=os.getpid(), keys='y+Enter', records=4), output)
    written = write_y(handle)
    (ROOT / 'input-result.json').write_text(json.dumps(dict(records_written=written)))
    while not re.search(rb'PTY_TEST_ISSUED_SEND_CTRL_C_NOW\r?\n', log.read_bytes()):
        assert time.monotonic() < deadline, 'No issued-Test marker; no Ctrl-C sent'
        assert not (ROOT / 'child-result.json').exists()
        time.sleep(.05)
    proof = fence('before-signal')
    with (ROOT / 'signal-intent.json').open('x') as output:
        json.dump(dict(event='CTRL_C_EVENT', group=0, exactly_one_attempt=True, members=proof['members']), output)
    sent = bool(kernel.GenerateConsoleCtrlEvent(0, 0))
    (ROOT / 'signal-result.json').write_text(json.dumps(dict(sent=sent, error=ctypes.get_last_error() if not sent else 0)))
    assert sent, 'Ctrl-C delivery not confirmed; no retry'
    while b'PTY_INTERRUPT_CHECKPOINT_PRESERVED_NO_BINDING_OR_GRANT' not in log.read_bytes():
        assert time.monotonic() < deadline, 'No preservation marker after the sole Ctrl-C'
        assert not (ROOT / 'child-result.json').exists()
        time.sleep(.05)
    (ROOT / 'controller-result.json').write_text(json.dumps(dict(status='SIGNAL_AND_PRESERVATION_MARKER_CONFIRMED')))
except BaseException as error:
    (ROOT / 'controller-refused.json').write_text(json.dumps(dict(error=type(error).__name__, reason=str(error))))
    raise
finally:
    if handle is not None:
        kernel.CloseHandle(handle)
    if attached:
        kernel.FreeConsole()
