from pathlib import Path
import hashlib,json,re,shutil,xml.etree.ElementTree as ET
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-public-review-vy7ixf88')
OUT=ROOT/'plans/agent_ops/evidence/r3-public-artifact-review'
assert not OUT.exists()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def dump(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
scan=json.loads((BASE/'scan.json').read_text(encoding='utf-8'))
targets={
 'docs/harness-integrations/evidence/EV-UAT-05-target-grammar-results.json':('904b6c330b070906868dbc09db45ed28d15f04879c21d295986da018cd4fcaa4',b'[REDACTED_HISTORICAL_UAT_API_KEY]'),
 'plans/agent_ops/evidence/pr06-attention-completion-authority-r3-messages-migration.xml':('578d939e9301918020be2a34550c4a78ee694391ffb7aeb11b9eae6423574652',b'[REDACTED_SYNTHETIC_LANE_TICKET]'),
}
pattern=re.compile(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}')
corrections=[]
for rel,(expected,replacement) in targets.items():
    path=ROOT/rel; before=path.read_bytes()
    matches=[m for m in pattern.finditer(before) if sha(m.group())==expected]
    assert len(matches)==1
    match=matches[0];after=before[:match.start()]+replacement+before[match.end():]
    assert pattern.search(after) is None
    if path.suffix=='.json':
        parsed=json.loads(before); parsed['register_operator']['response']['data']['api_key']=replacement.decode()
        assert json.loads(after)==parsed
    else:
        old=ET.fromstring(before);new=ET.fromstring(after)
        assert [e.attrib for e in old.iter()]==[e.attrib for e in new.iter()]
        assert [e.tag for e in old.iter()]==[e.tag for e in new.iter()]
        assert sum(1 for e in old.iter() if e.tag in ('failure','error','skipped'))==sum(1 for e in new.iter() if e.tag in ('failure','error','skipped'))
    path.write_bytes(after)
    corrections.append(dict(path=rel,before_sha256=sha(before),after_sha256=sha(after),redactions=1,
        removed_literal_sha256=expected,marker=replacement.decode(),outcomes_preserved=True))

report_path=ROOT/'plans/agent_ops/evidence/pr06-attention-completion-source-reports.json'
report=json.loads(report_path.read_text(encoding='utf-8'))
correction=corrections[1]
row=next(x for x in report['reports'] if x['artifact']==correction['path'])
assert row['artifact_sha256']==correction['before_sha256']
row['artifact_sha256']=correction['after_sha256']
row['security_redaction_2026_11_07']=dict(prior_artifact_sha256=correction['before_sha256'],synthetic_lane_tickets_redacted=1,
    correction_record='plans/agent_ops/evidence/r3-public-artifact-review/corrections.json',
    results_unchanged=True)
report['transformations']['security_amendment_2026_11_07']='The single synthetic lane ticket in the historical r3-messages-migration traceback was additionally redacted. The report entry records the previous artifact SHA and current SHA; all failures and testcase identities are preserved.'
dump(report_path,report)

OUT.mkdir()
shutil.copyfile(BASE/'scan.json',OUT/'scan-before.json')
shutil.copyfile(BASE/'scan.py',OUT/'scan.py')
shutil.copyfile(__file__,OUT/'redact.py')
dump(OUT/'corrections.json',dict(corrections=corrections,scope='Exactly two public report values; no database, personal account or secret store accessed.',
    historical_git_objects='Unchanged. This corrects current public files; it does not revoke credentials or rewrite existing Git history.',
    historical_uat_key_validity='Unknown; no authentication attempt or credential rotation performed.',
    raw_values_retained_in_new_artifacts=False))

url_sources={
 'fbddae166ead16d1dd67736b19403ab1ac0095e344f663573848af911a7ce273':('../okto-nexus-connector-core/tests/test_harness_config.py',21),
 '7f8183fd094a7b10753ce6a5f1a4388aa1afeda990c4134417045c78fcec9a2d':('../okto-nexus-connector/tests/unit/test_proxy.py',43),
 'ec25b8fa54a9d7a878a86e6f38233af24d5d27d184b396136d6d7f0251d33c19':('tests/execution_r4/test_remote_operator_terminal.py',236),
 '27b1f1415482004fafa005369ef6f6834a0e8f69dbc8d529e663898f8bc34d7e':('frontend/tests/mcpSnippet.test.mjs',24),
 'db194731c60fea84cc9cf3eb0e1ed6eec4e9a819afc6021324573b3ed46b1546':('tests/test_observation_client.py',205),
}
invalid={sha(('nxs_'+letter*count).encode()) for letter,count in [('g',48),('a',47),('a',49)]}
classifications=[]
for finding in scan['findings']:
    h=finding['literal_sha256'];row=dict(finding)
    if h in {c['removed_literal_sha256'] for c in corrections}:
        row['classification']='REMOVED_FROM_CURRENT_PUBLIC_FILE'
    elif h in invalid:
        row.update(classification='INVALID_SYNTHETIC_KEY_PARAMETER',source='tests/test_agent_keys.py',source_line=54,source_sha256=sha((ROOT/'tests/test_agent_keys.py').read_bytes()))
    else:
        assert h in url_sources,h
        name,line=url_sources[h];raw=(ROOT/name).read_bytes()
        candidates=re.findall(rb'https?://[^\s/:<>"\x27]+:[^\s/@<>"\x27]+@',raw)
        assert any(sha(x)==h for x in candidates)
        row.update(classification='SYNTHETIC_INVALID_URL_REJECTION_PARAMETER',source=name,source_line=line,source_sha256=sha(raw))
    classifications.append(row)
dump(OUT/'classifications.json',dict(findings=classifications,removed=2,synthetic_test_parameters=35,unclassified=0))
print(json.dumps(dict(corrections=2,classified=len(classifications),out=str(OUT))))
