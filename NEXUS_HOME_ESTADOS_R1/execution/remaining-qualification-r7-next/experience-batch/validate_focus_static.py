"""Parse wrapper AND its generated runner; never execute that runner."""
import ast
from pathlib import Path

path=Path(__file__).resolve().parent/'run_focus_return.py'
source=path.read_text();ast.parse(source)
old="exec(compile(source,str(HERE/'run.py'),'exec'))"
assert source.count(old)==1
source=source.replace(old,'ast.parse(source)')
exec(compile(source,str(path),'exec'),{'__file__':str(path),'ast':ast})
print('Wrapper and generated runner AST PASS; no application imports/allocation')
