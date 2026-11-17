"""Hold presentation through the existing asynchronous focus restoration."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tree = Path(json.loads((HERE / 'g08-ui-worktree-allocation.json').read_text())['root'])
path = tree / 'frontend/src/components/home/OperationalHome.tsx'
text = path.read_text(encoding='utf-8')
old = '  const [manualPause, setManualPause] = useState(false);'
assert text.count(old) == 1
text = text.replace(old, old + '\n  const [restoringFocus,setRestoringFocus]=useState(false);')
old = """  useEffect(()=>{if(!panel&&!manualPause&&!listFocused)setPresentationVersion(offeredPresentationVersion);},
    [panel,manualPause,listFocused,offeredPresentationVersion]);"""
new = """  useEffect(()=>{if(!panel&&!manualPause&&!listFocused&&!restoringFocus)setPresentationVersion(offeredPresentationVersion);},
    [panel,manualPause,listFocused,restoringFocus,offeredPresentationVersion]);"""
assert text.count(old) == 1
text = text.replace(old, new)
old = '  const close = useCallback(() => {\n    setPanel(null);'
assert text.count(old) == 1
text = text.replace(old, '  const close = useCallback(() => {\n    setRestoringFocus(true);\n    setPanel(null);')
old = '      destination?.focus({preventScroll:true});'
assert text.count(old) == 1
text = text.replace(old, '      try {destination?.focus({preventScroll:true});} finally {setRestoringFocus(false);}')
path.write_text(text, encoding='utf-8')
print(tree)
