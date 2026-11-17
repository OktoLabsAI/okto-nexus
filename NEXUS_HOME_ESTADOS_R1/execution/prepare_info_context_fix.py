"""Defer negotiated presentation switches while an exact context is open."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tree = Path(json.loads((HERE / 'g08-ui-worktree-allocation.json').read_text())['root'])
path = tree / 'frontend/src/components/home/OperationalHome.tsx'
text = path.read_text(encoding='utf-8')
old = 'registerLeaveGuard,presentationVersion=1}: {'
new = 'registerLeaveGuard,presentationVersion:offeredPresentationVersion=1}: {'
assert text.count(old) == 1
text = text.replace(old, new)
old = """  const [listFocused,setListFocused]=useState(false);
  const home = useHomeOverview"""
new = """  const [listFocused,setListFocused]=useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [presentationVersion,setPresentationVersion]=useState(offeredPresentationVersion);
  // A late capability reply must not reset the snapshot and unmount an active
  // canonical form. Adopt the offered version after that exact context closes.
  // Identity, workspace and authority changes still clear the controller normally.
  useEffect(()=>{if(!panel)setPresentationVersion(offeredPresentationVersion);},[panel,offeredPresentationVersion]);
  const home = useHomeOverview"""
assert text.count(old) == 1
text = text.replace(old, new)
old = "  const [panel, setPanel] = useState<Panel | null>(null), [manualPause, setManualPause] = useState(false);"
assert text.count(old) == 1
text = text.replace(old, '  const [manualPause, setManualPause] = useState(false);')
path.write_text(text, encoding='utf-8')
print(tree)
