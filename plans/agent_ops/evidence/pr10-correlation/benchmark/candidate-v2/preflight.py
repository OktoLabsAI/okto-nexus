"""Installed-only import/bootstrap/empty-read preflight; no benchmark seed/timing."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installed_obs12_benchmark', ROOT/'benchmark_installed.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proof', required=True)
    parser.add_argument('--dependency-path', required=True)
    args = parser.parse_args()
    output, home = ROOT/'preflight.json', ROOT/'private-preflight'
    if output.exists() or home.exists():
        raise RuntimeError('Preflight needs fresh absent report and disposable home')
    result = dict(status='PREPARING', not_a_performance_sample=True, heavy_seed_started=False)
    deps = None
    try:
        driver.isolate_environment(home)
        sys.path.append(str(Path(args.dependency_path).resolve()))
        proof = json.loads(Path(args.proof).read_text(encoding='utf-8'))
        result['package_before'] = driver.package_check(proof)
        from okto_nexus.bootstrap import embedded_inventory, runtime_host
        from okto_nexus.adapters.outbound.file.artifacts import LocalArtifactStore
        import subprocess
        with ExitStack() as guards:
            guards.enter_context(driver.patch.object(subprocess, 'Popen', driver.NoProcess))
            guards.enter_context(driver.patch.object(embedded_inventory, 'discover_local_candidates', driver.forbidden))
            for name in ('open_journal','create_runtime'):
                guards.enter_context(driver.patch.object(runtime_host, name, driver.forbidden))
            guards.enter_context(driver.patch.object(runtime_host.EmbeddedRuntimeHost, '_compose', driver.forbidden))
            for name in ('describe','read_text','read_bytes'):
                guards.enter_context(driver.patch.object(LocalArtifactStore, name, driver.forbidden))
            from okto_nexus.bootstrap.dependencies import bootstrap
            from okto_nexus.bootstrap.execution_authority import build_execution_access
            from okto_nexus.application.observations import ObservationService
            from okto_nexus.application.attention import AttentionService
            from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
            from okto_nexus.adapters.outbound.sqlite import observation_correlation_projection as batch
            from okto_nexus.domain.runtime_context import RuntimeRequestContext
            argv = ['--home',str(home),'--embedding-mode','off','--feature-harness-integrations','false',
                '--feature-observations','true','--feature-attention','true','--metrics-mode','disabled']
            for key,value in driver.QUOTAS.items():
                argv.extend(['--'+key.replace('_','-'),str(value)])
            deps = bootstrap({}, argv)
            service = ObservationService(deps=deps, access=build_execution_access(deps), correlations=batch)
            attention = AttentionService(factory=deps.connection_factory, access=service.access,
                queries=SqliteAttentionQueries(decision_registry=deps.approvals.attention_decision_actions),
                clock=deps.clock, config=deps.config)
            operator = RuntimeRequestContext(None, 'http_loopback', trusted_local_operator=True)
            assert service.summary(context=operator)['total_instances'] == 0
            assert attention.read(context=operator)['total'] == 0
            result.update(status='PASS', empty_summary=True, empty_attention=True,
                package_after=driver.package_check(proof))
    except Exception as error:
        result.update(status='ERROR', error=driver.error_metadata(error))
    finally:
        if deps is not None:
            deps.connection_factory.close()
        result['factory_closed'] = True
        output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], report=output.name, not_a_performance_sample=True)), flush=True)
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
