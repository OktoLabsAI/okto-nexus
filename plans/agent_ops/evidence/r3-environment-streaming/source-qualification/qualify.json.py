from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources={
    'nexus':('D:/Projetos/Techridy/okto_labs_okto_nexus','src/okto_nexus/service_environment.py','tests/test_service_environment_streaming.py'),
    'connector':('D:/Projetos/Techridy/okto-nexus-connector','src/okto_nexus_connector/service_environment.py','tests/unit/test_service_environment_streaming.py')}
pins={}
for host,(repo,source,test) in sources.items():
    total=ET.parse(ROOT/(host+'-source.xml')).getroot().find('testsuite')
    assert int(total.get('tests'))==18 and total.get('errors')==total.get('failures')=='0'
    pins[host]={'source':{'path':str(Path(repo)/source),'sha256':sha(Path(repo)/source)},
        'test':{'path':str(Path(repo)/test),'sha256':sha(Path(repo)/test)},'passed':18,
        'new_cases':16,'existing_regressions':2,'xml':host+'-source.xml'}
    (ROOT/host).mkdir()
    shutil.copyfile(Path(repo)/source,ROOT/host/'service_environment.py')
    shutil.copyfile(Path(repo)/test,ROOT/host/'test_service_environment_streaming.py')
diagnostic=Path('C:/Users/jpamb/AppData/Local/Temp/m1-w12-upgrade-probe-e8597493')
report={'status':'SOURCE_QUALIFIED_INSTALLED_PROBE_PENDING','hosts':pins,
    'contract':{'chunk_bytes':65536,'file_bytes':67108864,'distribution_bytes':268435456,'manifest_entries':10000,
        'probe_timeout_seconds':60,'ordered_fingerprint_unchanged':True,'core_exact_pin_unchanged':True,
        'caching':False,'concurrency':False},
    'readonly_comparison':{'path':str(diagnostic/'streaming-result.json'),'sha256':sha(diagnostic/'streaming-result.json'),
        'algorithm_same_installed_payload_snapshot_equal':True,'original_wall_seconds':62.014,
        'streaming_wall_seconds':1.6965,'limitation':'Comparison used unchanged old installed bytes and an in-memory alternative inspector. New wheel probe60 not yet run.'},
    'validation':{'nexus_ruff_tool':'9c5329','connector_ruff_tool':'a960f0','nexus_diffcheck_tool':'75cc38',
        'connector_diffcheck_tool':'d241b4','source_tests_first_run_passed':True,
        'connector_warnings':'Two pytest config warnings because asyncio plugin autoload disabled; selected tests are synchronous.'},
    'effects':{'service_calls':0,'provider_calls':0,'venv_installs':0,'Core_changes':0},
    'risks':['Streaming still observes the filesystem over time; no new atomic snapshot guarantee.',
        'Original and streaming paths reject excess bytes; streaming refuses earlier instead of reading the rest of an oversized distribution.',
        'The implementation file changes the installed payload hash on new wheels as expected; equality is algorithmic on the same bytes.']}
with (ROOT/'qualification.json').open('x',encoding='utf-8') as out:json.dump(report,out,indent=2);out.write('\n')
names=['run_source.py','qualify.json.py','qualification.json','nexus-source.xml','connector-source.xml',
    'nexus/service_environment.py','nexus/test_service_environment_streaming.py',
    'connector/service_environment.py','connector/test_service_environment_streaming.py']
with (ROOT/'public-allowlist.json').open('x',encoding='utf-8') as out:
    json.dump({'source_root':str(ROOT),'files':[{'path':name,'sha256':sha(ROOT/name),'bytes':(ROOT/name).stat().st_size} for name in names]},out,indent=2)
print(json.dumps({'qualification_sha256':sha(ROOT/'qualification.json'),'source_pins':pins}))
