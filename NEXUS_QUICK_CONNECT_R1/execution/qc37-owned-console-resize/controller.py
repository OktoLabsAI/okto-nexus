"""Read and resize only the exactly owned hidden console; never send signals."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from win import Owned, console_members, hidden_window, input_handle, kernel, same_image, write_y


class Coord(ctypes.Structure):
    _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]


class Rect(ctypes.Structure):
    _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short), ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]


class Info(ctypes.Structure):
    _fields_ = [('size', Coord), ('cursor', Coord), ('attributes', w.WORD), ('window', Rect), ('max_size', Coord)]


kernel.GetConsoleScreenBufferInfo.argtypes = [w.HANDLE, ctypes.POINTER(Info)]
kernel.SetConsoleWindowInfo.argtypes = [w.HANDLE, w.BOOL, ctypes.POINTER(Rect)]
kernel.SetConsoleScreenBufferSize.argtypes = [w.HANDLE, Coord]
kernel.ReadConsoleOutputCharacterW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, Coord, ctypes.POINTER(w.DWORD)]
(ROOT / 'controller-started.json').write_text(json.dumps({'pid': os.getpid(), 'parent_pid': os.getppid()}))
deadline = time.monotonic() + 160
attached = False
input_fd = output_fd = None
try:
    while not (ROOT / 'permit.json').exists():
        assert time.monotonic() < deadline
        time.sleep(.05)
    permit = json.loads((ROOT / 'permit.json').read_text())
    allowed = {row['pid']: row for row in permit['owned_processes']}
    assert os.getpid() in allowed and permit['child_main_pid'] in allowed
    kernel.FreeConsole()
    assert kernel.AttachConsole(permit['child_main_pid'])
    attached = True
    input_fd = input_handle()
    output_fd = kernel.CreateFileW('CONOUT$', 0x80000000 | 0x40000000, 3, None, 3, 0, None)
    assert output_fd != ctypes.c_void_p(-1).value

    def fence(stage):
        members = console_members()
        assert os.getpid() in members and permit['child_main_pid'] in members and set(members) <= set(allowed)
        proofs = []
        for pid in members:
            owner = Owned(pid)
            try:
                assert owner.alive() and owner.birth == allowed[pid]['birth_filetime'] and same_image(owner.image, allowed[pid]['image'])
                proofs.append(owner.facts())
            finally:
                owner.close()
        window = hidden_window()
        assert not window['visible'] and window['hwnd'] == permit['console_window']['hwnd']
        (ROOT / ('console-proof-' + stage + '.json')).write_text(json.dumps({'members': members, 'proofs': proofs, 'window': window}, indent=2))

    def info():
        result = Info()
        assert kernel.GetConsoleScreenBufferInfo(output_fd, ctypes.byref(result))
        return result

    def snapshot(label):
        value = info()
        count = value.size.X * value.size.Y
        assert 0 < count <= 1000000
        buffer, read = ctypes.create_unicode_buffer(count), w.DWORD()
        assert kernel.ReadConsoleOutputCharacterW(output_fd, buffer, count, Coord(0, 0), ctypes.byref(read))
        text = buffer[:read.value]
        (ROOT / ('buffer-' + label + '.txt')).write_text(text, encoding='utf-8')
        return '\n'.join(text[i:i + value.size.X] for i in range(0, len(text), value.size.X)), value

    def wait_for(prompt, label):
        while True:
            text, value = snapshot(label)
            compact = text.replace('\n', '')
            if prompt in compact:
                return value
            assert time.monotonic() < deadline, 'Exact console prompt missing; no input sent'
            assert not (ROOT / 'child-result.json').exists(), 'Child exited before expected prompt'
            time.sleep(.05)

    def resize(columns, label):
        fence('before-resize-' + label)
        before = info()
        # First shrink the owned viewport, then resize its own buffer, then viewport.
        tiny = Rect(0, 0, min(columns, before.size.X) - 1, 9)
        assert kernel.SetConsoleWindowInfo(output_fd, True, ctypes.byref(tiny))
        assert kernel.SetConsoleScreenBufferSize(output_fd, Coord(columns, max(3000, before.size.Y)))
        window = Rect(0, 0, columns - 1, 19)
        assert kernel.SetConsoleWindowInfo(output_fd, True, ctypes.byref(window))
        after = info()
        assert after.size.X == columns and after.window.Right - after.window.Left + 1 == columns
        (ROOT / ('resize-' + label + '.json')).write_text(json.dumps({'before_buffer': [before.size.X, before.size.Y], 'after_buffer': [after.size.X, after.size.Y], 'after_window': [after.window.Left, after.window.Top, after.window.Right, after.window.Bottom]}))

    wait_for('Confirm this review, including the model connection test? [y/customize/cancel] ', 'review')
    resize(50, 'narrow')
    fence('before-review-input')
    assert write_y(input_fd) == 4
    wait_for('Confirm resume? [y/N] ', 'resume')
    resize(100, 'wide')
    fence('before-resume-input')
    assert write_y(input_fd) == 4
    while True:
        text, _ = snapshot('final')
        if 'PTY_RESUME_CONFIRMED_ONE_TEST_TOTAL' in text.replace('\n', ''):
            break
        assert time.monotonic() < deadline
        time.sleep(.05)
    assert 'ID do Harness: codex' in text.replace('\n', '')
    (ROOT / 'controller-result.json').write_text(json.dumps({'status': 'RESIZE_AND_ONE_TEST_RESUME_CONFIRMED', 'inputs': 2, 'signals': 0, 'narrow_columns': 50, 'wide_columns': 100, 'public_id_observed': 'codex'}))
except BaseException as error:
    (ROOT / 'controller-refused.json').write_text(json.dumps({'error': type(error).__name__, 'reason': str(error)}))
    raise
finally:
    for handle in [input_fd, output_fd]:
        if handle is not None:
            kernel.CloseHandle(handle)
    if attached:
        kernel.FreeConsole()
