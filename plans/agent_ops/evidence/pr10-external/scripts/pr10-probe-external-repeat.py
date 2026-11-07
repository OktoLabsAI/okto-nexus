"""A single synthetic instance confirms aggregate/page projection repetition."""
from collections import Counter
import json
from pathlib import Path
import sys
import time

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'tests'))
import pytest
from okto_nexus.application import attention_external
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries

calls, durations = Counter(), Counter()
phase = 'outside_snapshot'
original_project = attention_external.project
original_snapshot = SqliteAttentionQueries.snapshot


def project(*args, **kwargs):
    start = time.perf_counter()
    try:
        return original_project(*args, **kwargs)
    finally:
        calls[phase] += 1
        durations[phase] += (time.perf_counter() - start) * 1000


def trace(sql):
    global phase
    if sql.lstrip().startswith('WITH source_facts AS'):
        phase = 'aggregate' if 'SELECT COUNT(*) AS total' in sql else 'page'


def snapshot(self, uow, **kwargs):
    global phase
    uow.connection.set_trace_callback(trace)
    try:
        return original_snapshot(self, uow, **kwargs)
    finally:
        uow.connection.set_trace_callback(None)
        phase = 'outside_snapshot'


attention_external.project = project
SqliteAttentionQueries.snapshot = snapshot
status = pytest.main(['tests/test_attention_external.py::test_blocked_is_observational_navigation_only_and_read_does_not_mutate',
    '-q', '--junitxml=C:/Users/jpamb/AppData/Local/Temp/pr10-external-repeat-probe.xml'])
result = dict(synthetic_instances=1, pytest_exit_code=int(status),
    external_project_calls_by_phase=dict(calls), external_project_milliseconds_by_phase=dict(durations),
    instrumentation_scope='One source checkout test; no benchmark fixture, provider or personal data read.')
target = Path('C:/Users/jpamb/AppData/Local/Temp/pr10-external-repeat-probe.json')
assert not target.exists()
target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(status)
