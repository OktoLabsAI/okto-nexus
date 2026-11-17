"""Prepare a one-shard captured-evidence curator, without launching tests."""
from pathlib import Path
import ast

here = Path(__file__).resolve().parent
target = here/'curate_regression.py'
assert not target.exists()
text = (here.parent/'package-hst-r3/curate_regression.py').read_text(encoding='utf-8')
text = text.replace("ROOTS = ('w0nhy3vj', 'cizcqxnv')", "ROOTS = ('gweb2v6c',)")
text = text.replace("    left=read(HERE/'installed-shard-0/collected.json')\n    right=read(HERE/'installed-shard-1/collected.json')\n    assert not set(left)&set(right), 'Shard inventories overlap'\n",
    "    assert len(read(HERE/'installed-shard-0/collected.json')) == sum(totals.values())\n")
text = text.replace("antecedents=['installed-gate-failure.json','installed-collection-failure/qualification.json']", "antecedents=[]")
text = text.replace('Browser functional journeys ran concurrently; no benchmark claim.',
    'Functional browser and Root source Home regression ran concurrently; no benchmark claim.')
ast.parse(text)
target.write_text(text,encoding='utf-8')
print('One-shard R5 curator prepared; no test executed')
