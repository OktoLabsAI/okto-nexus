from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
public = root / 'public-campaign'
review = Path('C:/Users/jpamb/AppData/Local/Temp/r3-authorized-campaign-review-cd5aqjtk/empty-lifecycle-v3-final-review.json')


def digest(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


assert digest(review)['sha256'] == '3c15f6213eec758330d55c3edc6b4c8ab3d3c991ba38ef3dd2a05585a95415b8'
manifest_path = public / 'artifact-manifest.json'
manifest = json.loads(manifest_path.read_text())
assert all(digest(public / name) == facts for name, facts in manifest['files'].items())
for source, name in ((review, 'independent-final-review.json'), (Path(__file__), 'append_final_review.py')):
    assert not (public / name).exists()
    shutil.copyfile(source, public / name)
    manifest['files'][name] = digest(public / name)

forbidden = {'native_xml', 'token', 'secret', 'session_secret', 'authorization', 'cookie', 'password'}
findings = []


def walk(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in forbidden:
                findings.append(path + '/' + key)
            walk(item, path + '/' + key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            walk(item, path + '/' + str(i))


for name in manifest['files']:
    if name.endswith('.json'):
        walk(json.loads((public / name).read_text()), name)
assert findings == [], findings
scan = {'scope': 'Public JSON recursively checked for raw secret/XML fields; no homes/DB/context files selected.',
        'forbidden_fields_found': [], 'allowlist_exact': True,
        'real_generated_credentials_or_tokens_copied': False,
        'limitation': 'This is structural artifact validation, not a universal secret detector.'}
(public / 'public-artifact-check.json').write_text(json.dumps(scan, indent=2) + '\n', encoding='utf-8')
manifest['files']['public-artifact-check.json'] = digest(public / 'public-artifact-check.json')
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
assert {p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file()} == set(manifest['files']) | {'artifact-manifest.json'}
print(json.dumps({'public': str(public), 'payloads': len(manifest['files']), 'manifest': digest(manifest_path)}))
