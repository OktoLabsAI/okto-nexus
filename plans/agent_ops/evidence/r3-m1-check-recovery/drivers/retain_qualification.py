from pathlib import Path
import json,hashlib,shutil,zipfile,datetime,xml.etree.ElementTree as ET
R=Path(__file__).parent;REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
E=REPO/'plans/agent_ops/evidence/r3-m1-check-recovery'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
P=json.loads((R/'build-install-result.json').read_text()); counts={}; all_nodes=set(); campaigns={}
for group in ('client','adjacent'):
    source=R/('installed-'+group)
    c=json.loads((source/'canonical/campaign.json').read_text())
    assert c['status']=='PASS' and c['exit_code']==0 and c['changed_inputs']==[]
    x=ET.parse(source/'canonical/tests.xml');nodes=list(x.iter('testcase'))
    assert not any(e.tag in ('failure','error','skipped') for n in nodes for e in n)
    keys={(n.attrib['classname'],n.attrib['name']) for n in nodes}
    assert len(keys)==len(nodes) and not all_nodes.intersection(keys)
    all_nodes.update(keys);counts[group]=len(nodes);campaigns[group]={'input_count':len(c['input_hashes']),'inputs_unchanged':True}
    target=E/('installed-'+group);target.mkdir()
    for name in ('command.json','stdout.txt','stderr.txt'):shutil.copyfile(source/name,target/name)
    shutil.copytree(source/'canonical',target/'canonical')
assert counts=={'client':34,'adjacent':25} and len(all_nodes)==59
installed_proof={}
modules=['okto_nexus','nexus_connector_core','okto_nexus_connector']
for entry,module in zip(P['products'],modules):
    wheel=Path(entry['path']);assert sha(wheel)==entry['sha256']
    with zipfile.ZipFile(wheel) as z:
        payload=[n for n in z.namelist() if n.startswith(module+'/') and not n.endswith('/')]
        for name in payload:assert (R/'venv/Lib/site-packages'/name).read_bytes()==z.read(name),name
    installed_proof[module]={'files':len(payload),'wheel_sha256':entry['sha256'],'post_test_payloads_unchanged':True}
assert sum(x['files'] for x in installed_proof.values())==982
pins={'src/okto_nexus/application/terminal_connection.py':'614dd004363fc78295f3ff38241900fc352dad65beb4fb04a4278639a705222e',
 'tests/execution_r4/test_terminal_connect.py':'33d38379fbc505efffadc79ce122c1775517aa314695d34c1b1a8647b24fadd3'}
for name,expected in pins.items():assert sha(REPO/name)==sha(R/'source'/name)==expected
for name in ('build-install-result.json','build.stdout','build.stderr','install.stdout','install.stderr','pip-check.stdout','pip-check.stderr','dependency-preparation.json','snapshot-inputs.json'):
    shutil.copyfile(R/name,E/name)
(E/'drivers').mkdir()
for name in ('build_and_install.py','prepare_dependencies.py','test_installed.py','retain_qualification.py'):shutil.copyfile(R/name,E/'drivers'/name)
q={'status':'INSTALLED_CLIENT_RECOVERY_VERIFIED','wheel_sha256':P['wheel_sha256'],'source_files':pins,
 'installed_unique_cases':59,'installed_groups':counts,'campaigns':campaigns,'package_payloads':installed_proof,
 'source_diagnostics':{'intermediate_runs':[26,33],'final_new_case_only':1,'final_whole_module_source_run':False},
 'cause':'Local CLI abandoned installations:check after a lost response although the exact version observation was durable and published; timing supports the30s transport boundary.',
 'correction':'Recover only OUTCOME_UNKNOWN/possible_effect from the same check through bounded GETs; preserve exact identity, fresh inventory, authority, deadlines and non-replayable checkpoints.',
 'definite_post_refusal_preserved':True,'per_http_timeout_unchanged':True,
 'native_provider_calls':0,'native_service_actions':0,'historical_campaign_modified':False,'acceptance_promoted':False,
 'limits':['An in-flight bounded HTTP request can outlast the observation deadline; no hard cancellation is claimed.',
 'A persisted test_submitted checkpoint with no POST is conservatively unconfirmed on later resume, never automatically replayed.',
 'Synthetic installed qualification does not satisfy M1, BASE-06 or real provider requirements.']}
(E/'qualification.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(E/'milestone.md').write_text('''# Recuperação da resposta da checagem de versão

A campanha M1 v8 parou antes de setup:test: a observação da versão já estava
persistida e publicada quando a CLI perdeu a resposta do POST. A fronteira de
30 segundos é sustentada por horários e fonte; não há trace interno desse await.

O cliente agora observa a mesma seleção por GET após OUTCOME_UNKNOWN com efeito
possível, sem repetir POST nem comando de versão. Exige Server/executor/candidato/
adapter exatos, inventário fresco e autoridade atual. O prazo é verificado entre
consultas e após gravações antes do próximo efeito. Recusas definitivas permanecem
recusas; falhas de leitura preservam a incerteza do check submetido.

Os bytes finais passaram em59 casos instalados:34 no fluxo de conexão e25 nos
contratos adjacentes. Os982 payloads dos três wheels foram conferidos antes/depois,
com imports exclusivos no novo prefixo e entradas de teste inalteradas. As rodadas
fonte26/33 são intermediárias; apenas o novo caso final foi repetido na fonte.

O timeout de cada HTTP continua limitado separadamente; não há promessa de
cancelamento rígido. Um test_submitted salvo antes de expirar o prazo permanece
conservador se o POST não começou, sem replay automático. Nenhum provedor real,
serviço Windows ou campanha foi reexecutado. M1 e demais aceites reais continuam
pendentes. A v8 permanece encerrada com fault/reserva preservados.
''',encoding='utf-8')
manifest={'status':q['status'],'files':{}}
for p in sorted(E.rglob('*')):
    if p.is_file() and p != E/'artifact-manifest.json':manifest['files'][p.relative_to(E).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
(E/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
lp=REPO/'plans/agent_ops/ledger.json';l=json.loads(lp.read_text(encoding='utf-8'))
l['campaigns']['r3_m1_v8_execution'].update(productive_admissions_status='READ_ONLY_RECONCILIATION_BEFORE_SETUP_TEST',
 closure_sha256='678dd44b316496fc847fe3b3686a233a2fd40d7afe89fd6e5d1d3132ca04f03d',
 remaining='Campaign permanently closed. A separately reviewed successor is required for M1; reserved slot and fault retained.')
l['campaigns']['r3_m1_check_recovery']={'status':q['status'],'nexus_wheel_sha256':P['wheel_sha256'],
 'installed_unique_cases':59,'package_payloads':982,'native_provider_calls':0,'native_service_actions':0,
 'acceptance_promoted':False,'evidence':['plans/agent_ops/evidence/r3-m1-check-recovery/qualification.json','plans/agent_ops/evidence/r3-m1-check-recovery/artifact-manifest.json']}
l['history'].append({'date':'2026-11-07','milestone':'M1 version-check response recovery fix',
 'status':q['status'],'summary':'Read-only diagnosis places v8 before inference. Corrected client uses bounded canonical GET recovery without check replay;59 installed cases PASS,982 payloads unchanged. No M1 acceptance.',
 'evidence':['plans/agent_ops/evidence/r3-m1-check-recovery/qualification.json']})
l['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();lp.write_text(json.dumps(l,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (REPO/'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').open('a',encoding='utf-8') as f:f.write('''
## 2026-11-07 — recuperação da checagem de versão qualificada

Diagnóstico somente leitura confirmou v8 em check_submitted, observação de
versão persistida e zero operações/sessões/recibos/Finish. A resposta perdida
é consistente com timeoutHTTP30 durante refresh posterior. O cliente recupera
agora por GET limitado, sem repetir o check, exigindo seleção exata, freshness,
autoridade e prazo. Falhas posteriores mantêm efeito possível; recusas não são
transformadas em autorização. Guardas cobrem consultas e gravações antes do teste.

59 casos dos bytes finais passaram instalados em ambiente separado (34+25),
com982 payloads conferidos e entradas inalteradas. Rodadas fonte26/33 são
intermediárias;1 novo caso final passou na fonte. Sem provedor/serviço real,
sem replay/reset da v8 e sem promoção de aceite. A reserva conservadora permanece.

Evidência: `plans/agent_ops/evidence/r3-m1-check-recovery/qualification.json`.
''')
with (REPO/'.gitattributes').open('a',encoding='utf-8') as f:f.write('plans/agent_ops/evidence/r3-m1-check-recovery/** -text -whitespace\n')
print(json.dumps({'installed_unique_cases':59,'evidence_files':len(manifest['files']),'wheel_sha256':P['wheel_sha256']}))
