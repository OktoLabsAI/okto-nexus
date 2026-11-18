"""Read frozen controller/test support and create a diagnostic outside canonical tests."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
out=HERE/'frontend-reproduction'
out.mkdir(exist_ok=True)
source=REPO/'frontend/tests/uiHarnessController.test.mjs'
prefix=source.read_text(encoding='utf-8').split("test('one Server board",1)[0]
prefix=prefix.replace("'./homeR1Support.mjs'",repr((REPO/'frontend/tests/homeR1Support.mjs').as_uri()))
extra='''
const observations=[];
test('characterization: identical paused polling prevents contextual pagination',async()=>{
 const h=harness();h.configure();await h.clock.advance();
 const before=JSON.stringify(h.controller.getState().harnessBoard);
 h.controller.pause(true);
 for(let cycle=1;cycle<=2;cycle++){
  await h.clock.advance(15000);
  const state=h.controller.getState();
  h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
  observations.push({cycle,clock:h.clock.now,paused:state.paused,pending:state.hasPendingUpdate,
   sameVisibleSnapshot:JSON.stringify(state.harnessBoard)===before,status:state.status,error:state.error,
   staleSections:state.staleSections,boardReads:h.calls.filter(c=>c.name==='harnessBoard').length,
   childReads:h.calls.filter(c=>c.name==='harnessChildren').length,peak:h.peak()});
 }
 console.log('REPRODUCTION '+JSON.stringify(observations));
 assert.equal(observations.length,2);
 assert.ok(observations.every(o=>o.pending&&o.sameVisibleSnapshot&&o.childReads===0&&o.status==='ready'&&o.error===null));
 assert.equal(h.calls.filter(c=>c.name==='harnessBoard').length,3);
 assert.equal(h.peak(),1);h.controller.dispose();
});
test('control: paused contextual pagination works before the first identical poll',async()=>{
 const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
 h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
 assert.equal(h.calls.filter(c=>c.name==='harnessChildren').length,1);
 assert.deepEqual(h.controller.getState().harnessChildren.card.items.map(x=>x.id),['work','work2']);
 assert.equal(h.controller.getState().hasPendingUpdate,false);h.controller.dispose();
});
test('HST-T-F01 desired contract: two identical polls must not block exact detail',async()=>{
 const h=harness();h.configure();await h.clock.advance();h.controller.pause(true);
 await h.clock.advance(30000);
 const pending=h.controller.getState().hasPendingUpdate;
 h.controller.loadHarnessChildren('card');await h.clock.advance(1000);
 const childReads=h.calls.filter(c=>c.name==='harnessChildren').length;h.controller.dispose();
 assert.deepEqual({pending,childReads},{pending:false,childReads:1});
});
'''
(out/'reproduction.mjs').write_text(prefix+extra,encoding='utf-8')
paths=['frontend/src/homeController.ts','frontend/src/components/home/OperationalHome.tsx',
       'frontend/src/components/home/HomeEntryInspection.tsx','frontend/src/homeEntryInspection.ts',
       'frontend/src/hooks/useHomeOverview.ts','frontend/src/homeSessionInspection.ts',
       'frontend/src/components/home/HomeSessionInspection.tsx','frontend/tests/uiHarnessController.test.mjs',
       'frontend/tests/homeR1Support.mjs','frontend/package.json','CONTRIBUTING.md','.github/workflows/ci.yml']
pins={name:dict(bytes=(REPO/name).stat().st_size,sha256=hashlib.sha256((REPO/name).read_bytes()).hexdigest()) for name in paths}
(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
print(json.dumps(dict(script=str(out/'reproduction.mjs'),source_files=len(pins))))
