"""One exact failed node in a fresh own home, installed only; no source edits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from run_shard import ROOT, PACKAGE, PYTHON, WHEEL, EXPECTED, GUARD

NODE = 'tests/execution_r4/test_canonical_admission_shutdown.py::test_feature_disable_preserves_unprojected_terminal_and_exclusive_claim'
HERE = Path(__file__).resolve().parent


def main():
    label = sys.argv[1]
    assert label in ('candidate', 'baseline')
    prefix = PACKAGE / 'venv' if label == 'candidate' else Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv')
    python = PYTHON if label == 'candidate' else prefix / 'Scripts/python.exe'
    assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == EXPECTED
    own = Path(tempfile.mkdtemp(prefix='nexus-qc09-focal-' + label + '-'))
    out = own / 'output'
    out.mkdir()
    for name in ('home', 'appdata', 'localappdata', 'tmp', 'guard'):
        (own / name).mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS')}
    env.update(HOME=str(own / 'home'), USERPROFILE=str(own / 'home'), APPDATA=str(own / 'appdata'),
        LOCALAPPDATA=str(own / 'localappdata'), TEMP=str(own / 'tmp'), TMP=str(own / 'tmp'),
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
        PATH=os.pathsep.join(map(str, [prefix / 'Scripts', Path('C:/Python313'), Path('C:/Windows/System32'),
            Path('C:/Windows'), Path('C:/Windows/System32/WindowsPowerShell/v1.0'), Path('C:/Program Files/nodejs'), Path('C:/Program Files/Git/cmd')])))
    (own / 'guard/qc_installed_origin_guard.py').write_text(GUARD.replace('PREFIX_VALUE', repr(str(prefix))).replace('OUT_VALUE', repr(str(out))), encoding='utf-8')
    config = own / 'pytest.ini'
    config.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    args = ['-p', 'qc_installed_origin_guard', '-c', str(config), '--rootdir=' + str(ROOT),
        '--confcutdir=' + str(ROOT / 'tests'), str(ROOT / NODE), '-vv', '--tb=long',
        '-o', 'faulthandler_timeout=120', '--junitxml=' + str(out / 'tests.xml')]
    code = ('import sys;sys.path.insert(0,' + repr(str(own / 'guard')) + ');'
        'import importlib.metadata;print("NEXUS_VERSION",importlib.metadata.version("okto-nexus"),flush=True);'
        'import pytest;raise SystemExit(pytest.main(' + repr(args) + '))')
    argv = [str(python), '-I', '-B', '-X', 'utf8', '-u', '-c', code]
    started = time.time()
    with (out / 'stdout.txt').open('w', encoding='utf-8') as stdout, (out / 'stderr.txt').open('w', encoding='utf-8') as stderr:
        child = subprocess.Popen(argv, cwd=own, env=env, stdout=stdout, stderr=stderr)
        ready = dict(label=label, own_root=str(own), output=str(out), command=argv, child_pid=child.pid)
        (HERE / f'focal-{label}-ready.json').write_text(json.dumps(ready, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(ready), flush=True)
        result = child.wait()
    final = dict(ready, exit_code=result, elapsed_seconds=time.time()-started)
    (out / 'result.json').write_text(json.dumps(final, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(label=label, exit_code=result, output=str(out))), flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
