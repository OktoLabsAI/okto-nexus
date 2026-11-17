"""Preserve explicit pause and board keyboard focus across capability arrival."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tree = Path(json.loads((HERE / 'g08-ui-worktree-allocation.json').read_text())['root'])
path = tree / 'frontend/src/components/home/OperationalHome.tsx'
text = path.read_text(encoding='utf-8')
manual = '  const [manualPause, setManualPause] = useState(false);'
assert text.count(manual) == 1
text = text.replace(manual + '\n', '')
old = '  const [panel, setPanel] = useState<Panel | null>(null);'
assert text.count(old) == 1
text = text.replace(old, old + '\n' + manual)
old = """  // A late capability reply must not reset the snapshot and unmount an active
  // canonical form. Adopt the offered version after that exact context closes.
  // Identity, workspace and authority changes still clear the controller normally.
  useEffect(()=>{if(!panel)setPresentationVersion(offeredPresentationVersion);},[panel,offeredPresentationVersion]);"""
new = """  // A late capability reply must not unmount a canonical form or replace a
  // board being read. Adopt it after the context, manual pause and focus release.
  // Identity, workspace and authority changes still clear the controller normally.
  useEffect(()=>{if(!panel&&!manualPause&&!listFocused)setPresentationVersion(offeredPresentationVersion);},
    [panel,manualPause,listFocused,offeredPresentationVersion]);"""
assert text.count(old) == 1
text = text.replace(old, new)
old = 'useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause]);'
assert text.count(old) == 1
text = text.replace(old, 'useEffect(() => {pause(manualPause || !!panel);}, [manualPause, !!panel, pause, presentationVersion]);')
path.write_text(text, encoding='utf-8')
print(tree)
