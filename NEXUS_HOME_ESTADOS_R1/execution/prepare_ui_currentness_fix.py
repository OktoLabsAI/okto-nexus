"""Edit only the isolated UI worktree; keep the installed-test checkout frozen."""
from pathlib import Path
import tempfile

tree = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-ui-current-usosb3j6').resolve()
assert tree.parent == Path(tempfile.gettempdir()).resolve()
assert tree.name.startswith('nexus-hst-ui-current-') and (tree / '.git').is_file()
path = tree / 'frontend/src/homeController.ts'
text = path.read_text(encoding='utf-8')
old = """    this.emit({...(changed&&(this.state.paused||held)?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:held||this.refreshPending||value.status!=='ready'?'stale':'ready',error:null,notice,staleSections:this.refreshPending?[...sections]:[]});
"""
new = """    // A current response can have incomplete coverage. Its per-source and
    // per-harness proof remains explicit; coverage is not snapshot age.
    const currentReply=value.status==='ready'||this.context.presentationVersion===2&&value.status==='partial';
    this.emit({...(changed&&(this.state.paused||held)?{hasPendingUpdate:true}:{...this.entryCache,hasPendingUpdate:false}),
      status:held||this.refreshPending||!currentReply?'stale':'ready',error:null,notice,staleSections:this.refreshPending?[...sections]:[]});
"""
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding='utf-8')
tests = tree / 'frontend/tests/uiHarnessController.test.mjs'
with tests.open('a', encoding='utf-8') as stream:
    stream.write("""
test('current v2 partial coverage does not age current harness proof; legacy mapping stays compatible',async()=>{
  for(const version of [1,2]){
    const h=harness();
    h.behavior.harnessBoard=q=>version===2?v2board(q,{status:'partial'}):board(q,{status:'partial'});
    h.configure({presentationVersion:version});await h.clock.advance();
    const state=h.controller.getState();
    assert.equal(state.status,version===2?'ready':'stale');
    assert.equal(state.harnessBoard.status,'partial');
    assert.equal(state.harnessBoard.source_status.external,'disabled');
    if(version===2)assert.equal(state.harnessBoard.columns.active.items[0].operational_status.freshness,'current');
    h.controller.dispose();
  }
});

test('v2 partial snapshots keep unknown proof and real refresh failure stale',async()=>{
  const h=harness();
  h.behavior.harnessBoard=q=>v2board(q,{status:'partial',columns:{...v2board(q).columns,
    active:slice([v2card({operational_status:operational({connection:'unknown',activity:'unknown',blocking:'unknown',freshness:'unavailable'})})])}});
  h.configure({presentationVersion:2});await h.clock.advance();
  assert.equal(h.controller.getState().status,'ready');
  assert.equal(h.controller.getState().harnessBoard.columns.active.items[0].operational_status.freshness,'unavailable');
  h.behavior.harnessBoard=()=>{throw Error('offline');};h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().status,'stale');assert.ok(h.controller.getState().error);
  assert.ok(h.controller.getState().staleSections.length>0);h.controller.dispose();
});

test('held v2 partial updates still age the displayed snapshot and preserve current data for apply',async()=>{
  const h=harness();h.behavior.harnessBoard=q=>v2board(q,{status:'partial'});
  h.configure({presentationVersion:2});await h.clock.advance();h.controller.pause(true);
  h.behavior.harnessBoard=q=>v2board(q,{status:'partial',revision:'b2'});
  h.controller.refresh();await h.clock.advance(1000);
  assert.equal(h.controller.getState().hasPendingUpdate,true);
  assert.equal(h.controller.getState().harnessBoard.revision,'b1');
  h.controller.applyPending();
  assert.equal(h.controller.getState().harnessBoard.revision,'b2');h.controller.dispose();
});
""")
print('Edited isolated UI controller and three regression cases; original checkout untouched.')
