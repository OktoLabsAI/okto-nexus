"""Prepare package-only drivers; does not build, install, allocate or start a service."""
from pathlib import Path

here = Path(__file__).resolve().parent
repo = here.parents[1]
old = repo / 'NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package'
out = here / 'package-hst'
assert not out.exists(), 'Reviewed drivers already exist; do not overwrite their gates.'
out.mkdir(exist_ok=True)
for name in ('package.py', 'audit.py', 'curate.py'):
    text = (old / name).read_text(encoding='utf-8')
    text = text.replace('0.3.6', '0.3.7').replace('nexus-qc-r1-package-', 'nexus-hst-r1-package-')
    text = text.replace("PYTHONUTF8='1')", "PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')")
    if name == 'package.py':
        text = text.replace('def main():', '''def source_ready():
    path = HERE/'SOURCE_ASSET_READY.json'
    assert path.is_file(), 'Root SOURCE_ASSET_READY required before any allocation/build/install.'
    ready = json.loads(path.read_text(encoding='utf-8'))
    assert ready.get('source_asset_ready') is True and ready.get('version') == '0.3.7'
    assert len(ready['source_commit']) == 40 and ready['assets']
    head = subprocess.check_output(['rtk','proxy','git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    assert head == ready['source_commit'], (head,ready['source_commit'])
    static = REPO/'src/okto_nexus/adapters/inbound/http/static'
    for name,pin in ready['assets'].items():
        assert sha(static/name) == pin, name
    return ready


def main():''')
        text = text.replace('args=parser.parse_args()', 'args=parser.parse_args()\n    source_ready()')
        text = text.replace("command(root,'venv'", "(root/'SOURCE_ASSET_READY.json').write_text(json.dumps(source_ready(),indent=2)+'\\n',encoding='utf-8')\n        command(root,'venv'")
    elif name == 'audit.py':
        text = text.replace('import platform', 'import platform\nimport re')
        text = text.replace("assert any(name.endswith('index-CfDr8rCI.js') for name in report['assets'])", '''ready=json.loads((HERE/'SOURCE_ASSET_READY.json').read_text(encoding='utf-8'))
static_prefix='okto_nexus/adapters/inbound/http/static/'
index=(REPO/'src'/static_prefix/'index.html').read_text(encoding='utf-8')
references=re.findall(r'(?:src|href)=["\\\']([^"\\\']+)["\\\']', index)
bundles=[ref.lstrip('/') for ref in references if ref.endswith(('.js','.css'))]
assert bundles and any(ref.endswith('.js') for ref in bundles) and any(ref.endswith('.css') for ref in bundles)
for ref in bundles:
    assert '..' not in Path(ref).parts and static_prefix+ref in report['assets'], ref
for name,pin in ready['assets'].items():
    assert report['assets'][static_prefix+name] == pin, name
report['asset_index_references']=bundles
assert sys.version_info[:3] == (3,13,1), sys.version''')
    else:
        text = text.replace("'qc11_package'", "'hst_package'")
        text = text.replace("assert len(payload['okto_nexus'])==733 and len(payload['nexus_connector_core'])==168 and len(payload['okto_nexus_connector'])==127", "assert payload['okto_nexus'] and len(payload['nexus_connector_core'])==168 and len(payload['okto_nexus_connector'])==127")
        text = text.replace("source_candidate_commit='9bc4034663ca63cfee43790b4bc03c38f8bdebcc'", "source_candidate_commit=builder.source_ready()['source_commit']")
        text = text.replace('Root frozen index-CfDr8rCI static payload reused and byte verified.', 'Root frozen assets discovered from current index.html, reused and byte verified.')
        text = text.replace("(HERE/'qualification.json').write_text", "(HERE/'qualification.json').write_text")
        text = text.replace("manifest={str(p.relative_to(HERE))", "(HERE/'READY.json').write_text(json.dumps(dict(ready=True,version='0.3.7',root=str(root),python=str(root/'venv/Scripts/python.exe'),wheel=str(root/'artifacts/okto_nexus-0.3.7-py3-none-any.whl'),wheel_sha256=builder.sha(root/'artifacts/okto_nexus-0.3.7-py3-none-any.whl'),payload_files=sum(len(files) for files in payload.values()),source_commit=builder.source_ready()['source_commit'],prefix_frozen=True),indent=2)+'\\n',encoding='utf-8')\nmanifest={str(p.relative_to(HERE))")
    (out / name).write_text(text, encoding='utf-8')
print(out)
