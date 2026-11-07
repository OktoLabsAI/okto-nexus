from pathlib import Path
import hashlib,json,re,subprocess,tempfile
repos={
 'nexus':Path('D:/Projetos/Techridy/okto_labs_okto_nexus'),
 'connector':Path('D:/Projetos/Techridy/okto-nexus-connector'),
 'core':Path('D:/Projetos/Techridy/okto-nexus-connector-core'),
}
out=Path(tempfile.mkdtemp(prefix='r3-public-review-'))
patterns={
 'nexus_credential_shape':re.compile(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}'),
 'provider_key_shape':re.compile(rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}'),
 'github_key_shape':re.compile(rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}'),
 'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'url_password':re.compile(rb'https?://[^\s/:<>"\x27]+:[^\s/@<>"\x27]+@'),
 'url_sensitive_query':re.compile(rb'https?://[^\s<>"\x27]+[?&](?:api_key|access_token|token|secret|password)=[A-Za-z0-9_-]{16,}',re.I),
}
inventory={};findings=[];exclusions={};heads={}
for name,repo in repos.items():
    heads[name]=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    paths=subprocess.check_output(['git','-C',str(repo),'ls-files','-z']).decode().split('\0')
    selected=[p for p in paths if p and (p.startswith(('plans/agent_ops/','docs/','examples/')) or '/' not in p and p.endswith(('.md','.json','.toml'))) ]
    inventory[name]={};exclusions[name]=[]
    for rel in selected:
        p=repo/rel
        if not p.is_file():
            exclusions[name].append(dict(path=rel,reason='tracked path absent'))
            continue
        raw=p.read_bytes()
        inventory[name][rel]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        if p.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.mp4','.woff','.woff2','.zip','.whl','.pdf'}:
            exclusions[name].append(dict(path=rel,reason='binary hashed, not text-scanned'))
            continue
        for kind,pattern in patterns.items():
            for match in pattern.finditer(raw):
                findings.append(dict(repo=name,path=rel,line=raw[:match.start()].count(b'\n')+1,kind=kind,
                    literal_sha256=hashlib.sha256(match.group()).hexdigest(),literal_length=len(match.group())))
result=dict(scope='Tracked public docs/examples/root metadata and plans/agent_ops in three repos; no private homes, vaults, registry, databases or user configuration enumerated.',heads=heads,inventory=inventory,findings=findings,exclusions=exclusions,
 limitations=['Pattern matching is not proof of absence of every secret or binary image content. Findings require classification; no matching values are emitted.',
 'Public code copied into evidence can contain synthetic literal credentials; distinguish them from runtime-generated secrets.',
 'Current snapshot only; no broad Git history rewrite or personal account scan.'])
(out/'scan.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(out/'scan.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(dict(output=str(out),files={k:len(v) for k,v in inventory.items()},findings=len(findings),kinds={k:sum(x['kind']==k for x in findings) for k in patterns},finding_paths=sorted(set(x['repo']+':'+x['path'] for x in findings))),indent=2))
