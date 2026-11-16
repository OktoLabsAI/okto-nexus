"""Own RO fixture; private controls inject one source failure or hold genuine HTTP bytes."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs
from fastapi.responses import JSONResponse

ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('ui10_base',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/empty-fixture.py')
empty=importlib.util.module_from_spec(spec);spec.loader.exec_module(empty)
base=empty.base
original=base.serve


async def serve(s,args,home,identities):
    original_app=s.app
    flags={'fail_results':False,'hold_a':False,'release':False}
    events=[]
    query=original_app.state.home_entries.queries
    actual=query._results
    def results(*a,**kw):
        if flags['fail_results']:
            events.append({'event':'results_query_OperationalError'})
            raise sqlite3.OperationalError('Own controlled single-source failure')
        return actual(*a,**kw)
    query._results=results
    class Controlled:
        def __getattr__(self,name):return getattr(original_app,name)
        async def __call__(self,scope,receive,send):
            if scope['type']=='http' and scope['path'].startswith('/__ui10/'):
                command=scope['path'].rsplit('/',1)[1]
                if command=='fail-results':flags['fail_results']=True
                elif command=='hold-a':flags.update(hold_a=True,release=False)
                elif command=='release-a':flags.update(hold_a=False,release=True)
                elif command=='events':pass
                else:return await JSONResponse({},status_code=404)(scope,receive,send)
                return await JSONResponse({'flags':flags,'events':events})(scope,receive,send)
            qs=parse_qs(scope.get('query_string',b'').decode())
            hold=scope.get('path')=='/api/v1/home/entries' and qs.get('workspace_id')==['ws'] and flags['hold_a']
            if not hold:return await original_app(scope,receive,send)
            messages=[]
            async def collect(message):messages.append(message)
            await original_app(scope,receive,collect)
            events.append({'event':'A_canonical_response_buffered','status':messages[0]['status'],
                'body':json.loads(b''.join(m.get('body',b'') for m in messages[1:]))})
            for _ in range(200):
                if flags['release']:break
                await asyncio.sleep(.1)
            events.append({'event':'A_response_release_attempt'})
            for message in messages:await send(message)
    s.app=Controlled()
    try:await original(s,args,home,identities)
    finally:args.ready_file.with_name('controlled-events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')


base.serve=serve
if __name__=='__main__':base.main()
