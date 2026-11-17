import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
prior = HERE / 'installed_regression_shard1_counterpart.py'
before = prior.read_text(encoding='utf-8')
old = "'-v','--tb=short','-x','--junitxml='"
assert before.count(old) == 1
after = before.replace(old, "'-v','--tb=short','--junitxml='")
observer = '''
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid.split('::')[-1] != 'test_metadata_hint_is_not_an_identity_or_root_selector':
        yield
        return
    from okto_nexus.adapters.outbound import git_project_hint
    original = git_project_hint.discover_project_name
    def observe(*args, **kwargs):
        started = time.perf_counter()
        result = original(*args, **kwargs)
        record = dict(nodeid=item.nodeid, name=result.name, source=result.source,
            status=result.status, reason=result.reason,
            duration_seconds=time.perf_counter()-started,
            behavior='identical result object returned; no arguments or settings modified')
        with (OUT/'git-hint-observation.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(record)+'\\n')
        return result
    git_project_hint.discover_project_name = observe
    try:
        yield
    finally:
        git_project_hint.discover_project_name = original
'''
assert after.count('def main():') == 1
after = after.replace('def main():', 'GUARD += ' + repr(observer) + '\n\ndef main():')
target = HERE / 'installed_regression_shard1_final.py'
target.write_text(after, encoding='utf-8')
out = HERE / 'installed-shard-1-final-proposal'
out.mkdir(exist_ok=True)
(out / 'runner.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=prior.name, tofile=target.name)), encoding='utf-8')
(out / 'mechanism.json').write_text(json.dumps({'scope': 'Only remove fail-fast -x; observe exactly one Git test through identity-returning wrapper restored in finally.',
    'prior_runner_sha256': hashlib.sha256(prior.read_bytes()).hexdigest(),
    'final_runner_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    'no_test_product_budget_prefix_change': True, 'concurrency': 'No other suite active per Root.'}, indent=2), encoding='utf-8')
curator = (HERE / 'curate_regression.py').read_text(encoding='utf-8')
curator = curator.replace("choices=['installed-shard-0','installed-shard-1','installed-legacy']", "choices=['installed-shard-1-final']")
(HERE / 'curate_shard1_final.py').write_text(curator, encoding='utf-8')
print(json.dumps({'runner_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'prepared_no_test_started': True}))
