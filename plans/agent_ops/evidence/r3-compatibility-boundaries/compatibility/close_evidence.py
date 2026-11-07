"""Close public RG-07 evidence with an explicit allowlist, no homes/binaries."""
from pathlib import Path
import ctypes
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / 'matrix-final-pairs'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pid_exit(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        assert ctypes.get_last_error() == 87
        return {'pid': pid, 'state': 'not_present'}
    try:
        code = ctypes.c_ulong()
        assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        assert code.value != 259, 'Owned fixture still active'
        return {'pid': pid, 'state': 'exited', 'exit_code': code.value}
    finally:
        kernel.CloseHandle(handle)


def main():
    summary = json.loads((FINAL / 'summary.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'PASS' and summary['pair_count'] == 4
    exits = {}
    tables = {}
    for label in ('old', 'new'):
        ready = json.loads((FINAL / (label + '-server/ready.json')).read_text(encoding='utf-8'))
        exits[label] = pid_exit(ready['pid'])
        proof = json.loads((FINAL / (label + '-server/proof.json')).read_text(encoding='utf-8'))
        assert proof['changed_tables'] == [] and proof['all_requests_public_uncredentialed']
        tables[label] = len(proof['before'])
    nexus = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
    connector = Path('D:/Projetos/Techridy/okto-nexus-connector')
    commits = {name: subprocess.check_output(['rtk', 'proxy', 'git', 'rev-parse', 'HEAD'], cwd=path).decode().strip()
               for name, path in [('nexus', nexus), ('connector', connector)]}
    source = []
    new = json.loads((FINAL / 'new-artifact-spec.json').read_text(encoding='utf-8'))
    import zipfile
    for item, repo in [(new['artifacts'][0], nexus), (new['artifacts'][2], connector)]:
        with zipfile.ZipFile(item['wheel']) as wheel:
            members = [name for name in wheel.namelist() if name.startswith(item['module'] + '/') and not name.endswith('/')]
            for name in members:
                assert (repo / 'src' / name).read_bytes() == wheel.read(name), name
        source.append({'component': item['module'], 'current_commit': commits['nexus' if repo == nexus else 'connector'],
                       'wheel_sha256': item['sha256'], 'source_equal_package_members': len(members)})
    (ROOT / 'qualification.json').write_text(json.dumps({
        'scenario': 'RG-07', 'plan_reference': 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md:974',
        'status': 'PASS', 'pair_count': 4, 'http_requests': 4,
        'requests': 'GET /v1/connections/protocol only; zero credentials, body or query parameters',
        'database_tables_unchanged': tables, 'actual_server_process_cleanup': exits,
        'current_source_comparison': source,
        'historical_sources': {'nexus': 'c1e78e26fb2bd57ace3370417a2cb7529856b603',
                               'connector': 'a3017d97b6a295cb2b46b9dd391b4c04ed121ee2',
                               'core_wheel_sha256': 'b01d4e2c6882b581d41cdf40179d5a96a6ff671b9f762244f3a4cae929a99988'},
        'preparation_attempts': [
            {'path': 'matrix', 'qualification_requests': 0, 'reason': 'Missing dependency .pth bootstrap for pywin32'},
            {'path': 'matrix-final', 'qualification_requests': 0, 'reason': 'Preparation one-liner rewrote dependency expression repeatedly'},
            {'path': 'matrix-qualified', 'qualification_requests': 0, 'reason': 'Windows venv redirector PID differs from real Python child; server closed normally'},
        ],
        'final_driver': 'matrix-final-pairs',
        'documentation_candidate': {'file': 'connection-setup-compatibility-section.md',
                                     'intended_target': 'docs/connection-setup.md', 'applied': False},
        'limitations': ['Public protocol negotiation only; no authenticated work/provider qualification',
                        'No daemon/native-service lifecycle, remote TLS, actual external MCP client versions or M1/M2 qualification',
                        'No checkout, ledger or historical artifact modifications'],
    }, indent=2) + '\n', encoding='utf-8')
    allowlist = [
        'prepare.py', 'configure_dependencies.py', 'server_probe.py', 'client_probe.py',
        'verify_installed.py', 'run_matrix.py', 'run_matrix-initial.py',
        'run_matrix-before-process-check.py', 'close_evidence.py', 'environment.json',
        'preparation.json', 'runtime-dependencies-final.json', 'qualification.json',
        'connection-setup-compatibility-section.md', 'nexus-build.log', 'connector-build.log', 'old-install.log',
        'matrix/old-server.log', 'matrix/old-cleanup.json', 'matrix-final/old-verify.log',
        'matrix-qualified/old-cleanup.json', 'matrix-qualified/old-server/ready.json',
        'matrix-qualified/old-server/proof.json',
    ]
    allowlist += ['matrix-final-pairs/' + name for name in (
        'summary.json', 'old-artifact-spec.json', 'new-artifact-spec.json', 'old-installed.json',
        'new-installed.json', 'old-pipcheck.log', 'new-pipcheck.log',
        'old-client--old-server.json', 'new-client--old-server.json',
        'old-client--new-server.json', 'new-client--new-server.json',
        'old-server/ready.json', 'new-server/ready.json',
        'old-server/proof.json', 'new-server/proof.json',
        'old-cleanup.json', 'new-cleanup.json', 'old-ownership.json', 'new-ownership.json',
    )]
    public = ROOT / 'public'
    public.mkdir()
    artifacts = []
    for name in allowlist:
        source_path = ROOT / name
        raw = source_path.read_bytes()
        assert not re.search(rb'(?<![A-Za-z0-9_])(?:nxs_|nxobs_)[A-Za-z0-9_-]{32,}', raw), name
        target = public / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        artifacts.append({'path': name, 'source': str(source_path), 'bytes': len(raw),
                          'original_sha256': sha(raw), 'artifact_sha256': sha(raw), 'redactions': 0})
    manifest = {'format': 'rg07-protocol-pairs-v1', 'artifact_count': len(artifacts),
                'artifacts': artifacts, 'excluded': ['venvs', 'wheels', 'archives', 'homes', 'databases'],
                'aggregate_sha256': sha(json.dumps(artifacts, sort_keys=True, separators=(',', ':')).encode())}
    (public / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'public': str(public), 'artifacts': len(artifacts), 'pairs': 4,
                      'manifest_sha256': sha((public / 'manifest.json').read_bytes()),
                      'aggregate_sha256': manifest['aggregate_sha256'], 'server_processes': exits}))


if __name__ == '__main__':
    main()
