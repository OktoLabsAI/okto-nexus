from pathlib import Path
import re,json,hashlib
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
source=(ROOT/'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').read_text(encoding='utf-8')
path=ROOT/'plans/agent_ops/ledger.json';ledger=json.loads(path.read_text(encoding='utf-8'))
assert hashlib.sha256(source.encode()).hexdigest()==ledger['plan_sha256']=='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
requirements={
 'tasks':dict(re.findall(r'^\*\*((?:BASE|SVC|DX|ATN|OBS)-\d+) — (.*?)\.\*\*',source,re.M)),
 'scenarios':dict(re.findall(r'^\| ((?:SVC-T|DX-T|AT-|OB-|RG-)\d+) \| (.*?) \|$',source,re.M)),
 'invariants':dict(re.findall(r'^\| (INV-\d+) \| (.*?) \|$',source,re.M)),
 'completion_criteria':{f'AC-{int(n):02}':text for n,text in re.findall(r'^(\d+)\. (.+)$',source.split('# 17.')[1].split('# 18.')[0],re.M)},
}
changes=[]
for section,rows in requirements.items():
    assert set(rows)==set(ledger[section]),(section,set(rows)^set(ledger[section]))
    field='title' if section=='tasks' else 'requirement'
    for key,current in rows.items():
        previous=ledger[section][key][field]
        if previous==current: continue
        variants=[]
        for encoding in ('latin1','cp1252'):
            try: variants.append(previous.encode(encoding).decode('utf-8'))
            except (UnicodeEncodeError,UnicodeDecodeError): pass
        assert current in variants,(section,key,'Difference is not just encoding; requires explicit review')
        changes.append(dict(section=section,id=key,field=field,previous_sha256=hashlib.sha256(previous.encode()).hexdigest(),corrected_text=current,source='fixed plan literal; only repaired encoding'))
        ledger[section][key][field]=current
path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
out=ROOT/'plans/agent_ops/evidence/r3-task-reconciliation';out.mkdir(exist_ok=True)
(out/'requirement-encoding.json').write_text(json.dumps(dict(plan_sha256=ledger['plan_sha256'],changed_fields=changes,statuses_changed=False,scope_changed=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'reconcile-encoding.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(dict(corrected_fields=len(changes),counts={k:len(v) for k,v in requirements.items()})))
