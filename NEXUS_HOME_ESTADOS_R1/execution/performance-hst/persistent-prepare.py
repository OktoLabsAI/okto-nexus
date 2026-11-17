"""Pure AST/text preparation; never imports product or runs a benchmark."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
raw=(HERE/'benchmark.py').read_text(encoding='utf-8')
tree=ast.parse(raw)
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='measure')
measure=ast.get_source_segment(raw,node)
replacements={
 'def measure(args, ready):':'async def persistent_measure(args, ready):',
 'from fastapi.testclient import TestClient':'from httpx import AsyncClient, ASGITransport',
 "client = TestClient(app, client=('127.0.0.1', 65123))  # no lifespan/native startup":
 "client = AsyncClient(transport=ASGITransport(app, client=('127.0.0.1',65123)), base_url='http://hst-own.invalid')  # no lifespan/network",
 "transport='ASGI HTTP; no TCP/browser/lifespan'":
 "transport='httpx AsyncClient/ASGITransport, one persistent asyncio loop; no TCP/browser/lifespan'",
 '    def read(path):':'    async def read(path):',
 'response = client.get(path, params=params)':'response = await client.get(path, params=params)',
 '= read(base)':'= await read(base)',
 '                read(path)':'                await read(path)',
 '= read(path)':'= await read(path)',
 '        client.close()':'        await client.aclose()',
}
for before,after in replacements.items():
    assert before in measure,before
    measure=measure.replace(before,after)
guardraw=(HERE/'measure-worker.py').read_text(encoding='utf-8')
gt=ast.parse(guardraw)
guardnode=next(n for n in gt.body if isinstance(n,ast.FunctionDef) and n.name=='guarded')
guard='@contextmanager\n'+ast.get_source_segment(guardraw,guardnode)
prefix='''"""Prepared persistent-ASGI counterpart; requires a new Root window."""
import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hst_persistent_original', HERE / 'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)
REPO = benchmark.REPO
sha, schema, load, trace, productive, stats = (getattr(benchmark, n) for n in ('sha','schema','load','trace','productive','stats'))

'''
suffix='''

def measure(args, ready):
    result = asyncio.run(persistent_measure(args, ready))
    result['counterpart'] = dict(original_runner_sha256=sha(HERE/'benchmark.py'), original_guard_sha256=sha(HERE/'measure-worker.py'),
        persistent_worker_sha256=sha(__file__), interpretation='Transport/lifecycle counterpart; preserves original TestClient cuts. Not browser DOM/network latency.')
    return result

if __name__ == '__main__':
    if len(sys.argv)<2 or sys.argv[1]!='measure':
        raise RuntimeError('Measurement only: never rebuild original datasets.')
    benchmark.no_external_effects = guarded
    benchmark.measure = measure
    benchmark.main()
'''
out=prefix+guard+'\n\n'+measure+suffix
parsed=ast.parse(out)
assert len([n for n in ast.walk(parsed) if isinstance(n,ast.AsyncFunctionDef) and n.name=='persistent_measure'])==1
(HERE/'persistent-worker.py').write_text(out,encoding='utf-8',newline='\n')
pins={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ['benchmark.py','measure-worker.py','dataset.py','persistent-worker.py','persistent-prepare.py']}
(HERE/'persistent-prepared.json').write_text(json.dumps(dict(status='PREPARED_NOT_EXECUTED',syntax='AST_PASS',pins=pins),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',worker_sha256=pins['persistent-worker.py'])))
