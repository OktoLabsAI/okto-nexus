"""Complement RG-06 for this installed wheel; no adapter/service execution."""
import _thread
from collections.abc import MutableMapping
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import threading
import zipfile

import win32cred
import win32crypt

wheel = Path(sys.argv[1])
core_source = Path(sys.argv[2])
verifier = Path(sys.argv[3])
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
assert digest == '5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb'
verify = runpy.run_path(str(verifier))['verify_import_boundaries']
with zipfile.ZipFile(wheel) as archive:
    package_files = [n for n in archive.namelist() if n.startswith('nexus_connector_core/') and not n.endswith('/')]
    names = sorted(n for n in package_files if n.endswith('.py'))
    for name in package_files:
        assert (Path(sys.prefix)/'Lib/site-packages'/name).read_bytes() == archive.read(name), name
        assert (core_source/name).read_bytes() == archive.read(name), name
    for name in names:
        verify(archive.read(name), name)
modules = sorted(set(n[:-3].replace('/', '.') if not n.endswith('/__init__.py') else n[:-12].replace('/', '.') for n in names))
assert not any(name.startswith(('nexus_connector_core', 'okto_nexus')) for name in sys.modules)
assert sys.flags.isolated and sys.flags.dont_write_bytecode
allowed = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
original_environment = dict(os.environ)
assert original_environment['RG06_IMPORT_CREDENTIAL_SENTINEL'] == 'fixture-only-not-a-real-secret'
assert Path(original_environment['HOME']).resolve() == Path(original_environment['USERPROFILE']).resolve()
denied, controls, environment_reads = [], [], []
console_bindings = []
file_reads = 0
phase = 'controls'


class GuardRejected(RuntimeError):
    pass


def reject(event):
    (controls if phase == 'controls' else denied).append(event)
    raise GuardRejected(event)


def audit(event, args):
    global file_reads
    if event.startswith('ctypes.dlsym') or event == 'ctypes.dlopen':
        frame = sys._getframe(1)
        while frame and frame.f_globals.get('__name__') in ('ctypes', '__main__'):
            frame = frame.f_back
        caller = frame.f_globals.get('__name__') if frame else ''
        target = str(args[0] if event == 'ctypes.dlopen' else args[1])
        # click._winconsole binds these console/buffer APIs during MCP import.
        # This exact reviewed exception grants no credential/library access.
        approved = ('kernel32', 'shell32') if event == 'ctypes.dlopen' else (
            'GetStdHandle', 'ReadConsoleW', 'WriteConsoleW', 'GetConsoleMode', 'GetLastError',
            'CommandLineToArgvW', 'LocalFree', 'PyObject_GetBuffer', 'PyBuffer_Release')
        if phase == 'imports' and caller == 'click._winconsole' and target in approved:
            console_bindings.append(dict(event=event, target=target, caller=caller))
            return
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn', 'os.spawn',
                                               'ctypes.dlopen', 'ctypes.dlsym', 'ctypes.dlsym/handle', 'os.putenv', 'os.unsetenv'):
        reject(event + ':' + str(args[1]) if event.startswith('ctypes.dlsym') else event)
    if event == 'import' and args[0].split('.')[0] in ('okto_nexus', 'okto_nexus_connector', 'keyring', 'keyrings'):
        reject('forbidden_import:' + args[0])
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            reject('file_write')
        if not any(path.is_relative_to(base) for base in allowed):
            reject('read_outside_python_installations')
        file_reads += 1


class GuardEnvironment(MutableMapping):
    def __getitem__(self, key):
        caller = sys._getframe(1)
        while caller and caller.f_globals.get('__name__') in ('os', 'collections.abc', '_collections_abc'):
            caller = caller.f_back
        module = caller.f_globals.get('__name__', '') if caller else ''
        if phase == 'imports':
            environment_reads.append(dict(key=str(key), caller=module))
        if re.search(r'(^|_)(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)(_|$)', str(key), re.I):
            reject('credential_environment_lookup')
        if module.startswith('nexus_connector_core'):
            reject('core_environment_lookup')
        return original_environment[key]

    def __iter__(self):
        reject('environment_enumeration')

    def __len__(self):
        return len(original_environment)

    def __setitem__(self, key, value):
        reject('environment_mutation')

    def __delitem__(self, key):
        reject('environment_mutation')


os.environ = GuardEnvironment()
if os.name == 'nt':
    import nt
    nt.environ = os.environ


def guarded(label):
    def call(*args, **kwargs):
        reject(label)
    return call


guarded_native = []
for name in dir(win32cred):
    if name.startswith('Cred') and callable(getattr(win32cred, name)):
        label = 'win32cred.' + name
        setattr(win32cred, name, guarded(label))
        guarded_native.append(label)
win32crypt.CryptUnprotectData = guarded('win32crypt.CryptUnprotectData')
guarded_native.append('win32crypt.CryptUnprotectData')
for module in (_thread, threading):
    for name in ('start_new_thread', 'start_new', '_start_new_thread', 'start_joinable_thread', '_start_joinable_thread'):
        if hasattr(module, name):
            setattr(module, name, guarded('thread_start'))
sys.addaudithook(audit)

checks = (
    ('os.getenv', lambda: os.getenv('RG06_IMPORT_CREDENTIAL_SENTINEL')),
    ('os.environ.get', lambda: os.environ.get('RG06_IMPORT_CREDENTIAL_SENTINEL')),
    ('os.environ[index]', lambda: os.environ['RG06_IMPORT_CREDENTIAL_SENTINEL']),
    ('dict(os.environ)', lambda: dict(os.environ)),
    ('win32cred.CredRead', lambda: win32cred.CredRead('rg06-synthetic-target', 1)),
    ('win32cred.CredEnumerate', lambda: win32cred.CredEnumerate(None, 0)),
    ('win32crypt.CryptUnprotectData', lambda: win32crypt.CryptUnprotectData(b'synthetic-not-encrypted')),
    ('ctypes.WinDLL', lambda: ctypes.WinDLL('advapi32.dll')),
    ('ctypes.dlsym', lambda: ctypes.pythonapi['CredReadW']),
)
control_results = []
for name, check in checks:
    try:
        check()
    except GuardRejected:
        control_results.append(dict(name=name, blocked=True))
    else:
        raise AssertionError('Guard did not reject ' + name)
phase = 'imports'
loaded, failure = [], None
try:
    for module in modules:
        value = importlib.import_module(module)
        assert Path(value.__file__).is_relative_to(Path(sys.prefix))
        loaded.append(module)
except BaseException as error:
    failure = dict(type=type(error).__name__, module=module)
    trace, frames = error.__traceback__, []
    while trace:
        frames.append(dict(module=trace.tb_frame.f_globals.get('__name__'),
                           function=trace.tb_frame.f_code.co_name, line=trace.tb_lineno))
        trace = trace.tb_next
    failure['frames'] = frames
app_imports = sorted(name for name in sys.modules if name.split('.')[0] in ('okto_nexus', 'okto_nexus_connector'))
result = dict(status='PASS' if not denied and failure is None and not app_imports else 'FAIL',
    core_wheel_sha256=digest, package_files_equal_to_source_and_install=len(package_files),
    static_python_files=len(names), imported_modules=loaded, denied_events=denied, import_failure=failure,
    environment_reads=environment_reads, guarded_native_apis=guarded_native, controls=control_results,
    allowed_dependency_console_bindings=console_bindings,
    reads_within_python_installations=file_reads, forbidden_applications_loaded=app_imports,
    isolated=True, bytecode_disabled=True,
    limits=['Windows local installed-import path only; no runtime adapter or credential resolution.',
            'Native guards cover win32cred entry points, DPAPI unprotect and ctypes dynamic loads/symbol lookup.',
            'Only the listed click._winconsole console/buffer bindings are allowed; stdin is DEVNULL.',
            'Python environment lookup instrumentation is not an arbitrary C-extension/system-call tracer.',
            'No credential value, inherited user environment, real user home, vault read or vault write is used.'])
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
