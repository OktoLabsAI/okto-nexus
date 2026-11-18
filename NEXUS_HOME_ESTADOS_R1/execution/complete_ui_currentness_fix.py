"""Preserve freshness distinctions when applying held operational snapshots."""
from pathlib import Path

tree = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-ui-current-usosb3j6')
path = tree / 'frontend/src/homeController.ts'
text = path.read_text(encoding='utf-8')
old = """    if(this.trackingFamily()){this.emit({...this.entryCache,hasPendingUpdate:false,
      status:(this.harnessFamily()?this.entryCache.harnessBoard:this.boardFamily()?this.entryCache.board:this.entryCache.entries)?.status==='ready'&&!this.refreshPending?'ready':'stale',staleSections:this.refreshPending?[...sections]:[]});return;}
"""
new = """    if(this.trackingFamily()){
      const value=this.harnessFamily()?this.entryCache.harnessBoard:this.boardFamily()?this.entryCache.board:this.entryCache.entries;
      const currentReply=value?.status==='ready'||this.harnessFamily()&&this.context.presentationVersion===2&&value?.status==='partial';
      this.emit({...this.entryCache,hasPendingUpdate:false,
        status:currentReply&&!this.refreshPending&&!this.state.error?'ready':'stale',staleSections:this.refreshPending?[...sections]:[]});return;
    }
"""
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding='utf-8')
tests = tree / 'frontend/tests/uiHarnessController.test.mjs'
text = tests.read_text(encoding='utf-8')
old = """  assert.ok(h.controller.getState().staleSections.length>0);h.controller.dispose();
});

test('held v2 partial updates"""
new = """  assert.ok(h.controller.getState().staleSections.length>0);
  h.controller.pause(false);assert.equal(h.controller.getState().status,'stale');
  assert.ok(h.controller.getState().error);h.controller.dispose();
});

test('held v2 partial updates"""
assert text.count(old) == 1
text = text.replace(old, new)
old = """  assert.equal(h.controller.getState().harnessBoard.revision,'b2');h.controller.dispose();
});
"""
new = """  assert.equal(h.controller.getState().harnessBoard.revision,'b2');
  assert.equal(h.controller.getState().status,'ready');h.controller.dispose();
});
"""
assert text.count(old) == 1
tests.write_text(text.replace(old, new), encoding='utf-8')
print('Updated only isolated UI worktree; paused-apply and refresh-error invariants covered.')
