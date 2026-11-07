"""Prepare a new candidate; retain the original package and all its reports."""
from pathlib import Path

root = Path(__file__).resolve().parent
build = (root / 'build_release.py').read_text(encoding='utf-8')
assert build.count(" / 'candidate-v1'") == 1
with (root / 'build_release_v2.py').open('x', encoding='utf-8') as output:
    output.write(build.replace(" / 'candidate-v1'", " / 'candidate-v2'"))
qualify = (root / 'qualify_installed.py').read_text(encoding='utf-8')
assert qualify.count(" / 'candidate-v1'") == 1
qualify = qualify.replace(" / 'candidate-v1'", " / 'candidate-v2'")
qualify = qualify.replace("nodes = suites[sys.argv[3]]", "suites['attention-followup'] = suites['regression'] + [\n"
    "    'test_observation_correlation_reads.py', 'test_attention_correlation_policy.py']\n"
    "nodes = suites[sys.argv[3]]")
with (root / 'qualify_installed_v2.py').open('x', encoding='utf-8') as output:
    output.write(qualify)
print('Candidate-v2 build and installed affected-regression drivers prepared; not executed.')
