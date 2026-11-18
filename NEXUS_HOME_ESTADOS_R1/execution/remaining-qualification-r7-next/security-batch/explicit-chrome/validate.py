"""Additional instrumental gate; no browser/product/allocation is started."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
BASE_MANIFEST='37f0fea6bd0b0363d0fb9292d9b277a6041355d8c1a182964288169bc5b7bf01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(gate_path):
    gate=json.loads(Path(gate_path).read_text())
    manifest_path=HERE/'manifest.json'
    manifest=json.loads(manifest_path.read_text())
    assert gate.get('approved') is True and gate.get('approved_by')=='root'
    assert gate['case']=='S1' and re.fullmatch(r'hst-security-r8-s1-[a-z0-9-]{1,80}',gate['cut_id'])
    assert gate['instrumentation_manifest_sha256']==sha(manifest_path)
    assert gate['manifest_sha256']==sha(BASE/'prepared-manifest.json')==BASE_MANIFEST
    assert gate['browser_executable_sha256']==manifest['browser']['sha256']
    assert Path(gate['browser_executable_path']).resolve()==Path(manifest['browser']['path']).resolve()
    assert sha(gate['browser_executable_path'])==manifest['browser']['sha256']
    assert gate['browser_config_sha256']==sha(HERE/'playwright-cli.json')==manifest['config_sha256']
    expected={'browser':{'launchOptions':{'executablePath':manifest['browser']['path']}}}
    assert json.loads((HERE/'playwright-cli.json').read_text())==expected
    for name,pin in manifest['input_pins'].items():
        path=(BASE/name).resolve()
        assert path.is_relative_to(BASE.resolve()) and sha(path)==pin
    assert not (HERE/('attempt-'+gate['cut_id']+'.json')).exists(), 'One allocation per new gate; no retry'
    assert not (BASE/'runs'/gate['cut_id']).exists(), 'Prior cut preserved'
    return {'base_manifest_sha256':BASE_MANIFEST,'instrumentation_manifest_sha256':sha(manifest_path),
            'browser_executable_path':manifest['browser']['path'],
            'browser_executable_sha256':manifest['browser']['sha256'],
            'config_sha256':manifest['config_sha256'],
            'gate_sha256':sha(gate_path),'cut_id':gate['cut_id']}


def claim(proof):
    path=HERE/('attempt-'+proof['cut_id']+'.json')
    with path.open('x',encoding='utf-8') as output:
        output.write(json.dumps(proof,indent=2)+'\n')


def after(proof, runtime_config):
    manifest=json.loads((HERE/'manifest.json').read_text())
    assert sha(proof['browser_executable_path'])==proof['browser_executable_sha256']
    assert sha(runtime_config)==sha(HERE/'playwright-cli.json')==proof['config_sha256']
    assert sha(HERE/'manifest.json')==proof['instrumentation_manifest_sha256']
    for name,pin in manifest['input_pins'].items():
        assert sha(BASE/name)==pin
    return dict(proof, runtime_config_sha256=sha(runtime_config), unchanged=True)
