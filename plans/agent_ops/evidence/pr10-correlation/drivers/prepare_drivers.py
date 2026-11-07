"""Prepare detached qualification drivers without building an unfrozen tree."""
from pathlib import Path

root = Path(__file__).resolve().parent
prior = root.parent / 'pr10-external-installed-xb13pb6_'
build = (prior / 'build_release_v4.py').read_text(encoding='utf-8')
build = build.replace(" / 'qualified-v4'", " / 'candidate-v1'")
(root / 'build_release.py').write_text(build, encoding='utf-8')
qualify = (prior / 'qualify_installed_v4.py').read_text(encoding='utf-8')
qualify = qualify.replace("ROOT = Path(__file__).resolve().parent / 'qualified-v4'", "BASE = Path(__file__).resolve().parent / 'candidate-v1'\nROOT = BASE / ('tests-' + sys.argv[3])\nROOT.mkdir(exist_ok=False)")
qualify = qualify.replace("SITE = ROOT / 'venv/Lib/site-packages'", "SITE = BASE / 'venv/Lib/site-packages'")
qualify = qualify.replace("(tests / 'execution_r4').mkdir()", "(tests / 'execution_r4').mkdir()\nshutil.copytree(REPO / 'tests/fixtures/diagnostics_v1', tests / 'fixtures/diagnostics_v1')")
start = qualify.index('nodes = [')
end = qualify.index('\nimport pytest', start)
qualify = qualify[:start] + '''suites = {
    'correlation': [
        'test_observation_correlation_domain.py',
        'test_observation_correlations_storage.py',
        'test_observation_process_birth.py',
        'test_observation_correlation_http.py',
        'test_observation_correlation_proof.py',
        'test_observation_correlation_projection.py',
        'test_observation_correlation_view.py',
        'test_observation_correlation_reads.py',
        'test_observation_settings.py',
    ],
    'regression': [
        'test_import_boundary.py', 'test_observation_service.py',
        'test_observation_http.py', 'test_observation_summary_http.py',
        'test_attention_external.py', 'test_attention_external_upgrade.py',
        'test_attention_snapshot_query.py', 'test_attention_external_query.py',
        'test_attention_engine_bounds.py', 'test_attention_api.py',
        'test_attention_stream.py', 'test_attention_storage.py',
        'execution_r4/test_external_observation_isolation.py',
    ],
    'diagnostics': ['test_diagnostic_report_contract.py',
        'test_doctor_diagnostic_format.py', 'test_project_doctor_cli.py'],
}
nodes = suites[sys.argv[3]]''' + qualify[end:]
qualify = qualify.replace("'pr10-external-installed-final.xml'", "'installed.xml'")
(root / 'qualify_installed.py').write_text(qualify, encoding='utf-8')
print(root)
