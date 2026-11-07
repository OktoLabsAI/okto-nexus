import json, pathlib, subprocess, datetime
B=pathlib.Path('C:/Users/jpamb/AppData/Local/Temp/m1-v8-handoff-ready-s4wcxb28')
C=json.loads((B/'proposed-commands.json').read_text())
argv=list(next(s for s in C['steps'] if s['component']=='nexus' and s['action']=='start')['argv'])
argv[argv.index('service')+1]='status'
argv[argv.index('--timeout')+1]='10'
r=subprocess.run(argv,capture_output=True)
v=json.loads(r.stdout)
safe={k:v.get(k) for k in ('component','instance_id','generation','state','ready_for_queries','reason','pid','process_started_at','user_service')}
safe['observed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
out=B.parent/'m1-fresh-v8-pg0b6zbf/campaign/public'/('nexus-status-'+str(datetime.datetime.now().timestamp())+'.json')
out.write_text(json.dumps(safe,indent=2))
print(json.dumps(safe))
