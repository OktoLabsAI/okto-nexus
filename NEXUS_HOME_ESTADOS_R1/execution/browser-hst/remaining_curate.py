"""Sanitize a completed small fixture, preserving old reports and helper pins."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from curation_privacy import cas_values,redact
HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--tag',required=True);p.add_argument('--classification',required=True);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')and all(c.isalnum()or c in '-_'for c in a.tag)
    subprocess.run([sys.executable,'-B',str(HERE/'curate.py'),'--root',str(root),'--tag',a.tag,'--classification',a.classification],check=True)
    dest=HERE/'remaining-cuts'/a.tag;assert not dest.exists();dest.mkdir(parents=True)
    names=['remaining-builder-proof.json','remaining-failure.json','remaining-payload-proof.json','remaining-steps.json','control/remaining-session-metadata.json','control/remaining-fresh-questions.json']
    names += [p.name for p in root.glob('*.js')]
    cookiefile=root/'control/browser-storage.private.json';cookies=[x['value'].encode()for x in json.loads(cookiefile.read_text())['cookies']];cas=cas_values(root);copies=[]
    for name in names:
        source=root/name
        if not source.exists():continue
        raw,count=redact(source.read_bytes(),cas);assert not any(value in raw for value in cookies)
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);copies.append(dict(path=name,source_sha256=sha(source),sha256=sha(target),bytes=len(raw),cas_redactions=count))
    base=HERE/'cuts'/a.tag/'qualification.json';q=json.loads(base.read_text());manifest=dict(status=a.classification,base_cut='../../cuts/'+a.tag,base_qualification_sha256=sha(base),checks_pass=q['checks_pass'],checks_fail=q['checks_fail'],copies=copies,active_resources=False,credentials='Cookie/storage/wire/private question proposal never copied; exactCAS redacted')
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(path=str(dest),checks_pass=q['checks_pass'],checks_fail=q['checks_fail'],manifest_sha256=sha(dest/'manifest.json'))))
if __name__=='__main__':main()
