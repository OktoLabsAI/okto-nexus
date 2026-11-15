"""One explicit discovery correction; original draft selection stays untouched."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import os
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recovery_context import require, read_json, pin, sha


class NativePathEnvironment:
    def __init__(self, base, native):
        self.base, self.native = base, native

    def __getattr__(self, name):
        return getattr(self.base, name)

    def connector_env(self):
        value = self.base.connector_env()
        parent = str(Path(self.native['path']).resolve().parent)
        inherited = value.get('PATH', '').split(os.pathsep)
        value['PATH'] = os.pathsep.join([parent] + [part for part in inherited if part and Path(part).resolve() != Path(parent)])
        return value


def require_draft_unselected(X):
    require(not (X.PUBLIC / 'draft02-draft-reserved.json').exists()
        and not X.draft_path.exists(), 'ORIGINAL_DRAFT_ALREADY_SELECTED')


def discovery_proxy(X):
    private = X.PRIVATE / 'draft02-discovery-retry1'
    private.mkdir(exist_ok=False)

    def save(name, value):
        require(name.startswith('draft02-discover-'), 'DISCOVERY_NAMESPACE_REQUIRED')
        X.save(name.replace('draft02-discover-', 'draft02-discover-retry1-', 1), value)

    return SimpleNamespace(PRIVATE=private, PUBLIC=X.PUBLIC, ROOT=X.ROOT, base=X.base, save=save)


def prior_discovery(X):
    path = X.PRIVATE / 'draft02-discovery-retry1/draft02-discover.stdout'
    result = read_json(X.PUBLIC / 'draft02-discover-retry1-returned.json')
    require(result.get('draft_plan_sha256') == X.plan_sha and result.get('returncode') == 0
        and result.get('stdout_sha256') == sha(path), 'RETRY_DISCOVERY_UNCONFIRMED')
    return read_json(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('action', choices=['discover', 'draft'])
    args = parser.parse_args()
    require(Path(args.manifest).resolve() == HERE / 'draft02-discovery-retry-manifest.json'
        and sha(args.manifest) == args.expected_manifest_sha256, 'RETRY_MANIFEST_CHANGED')
    manifest = read_json(args.manifest)
    for item in manifest['pins'].values():
        pin(item)
    require(manifest['scope'] == 'ONE_NATIVE_PARENT_PATH_DISCOVERY_RETRY_ORIGINAL_DRAFT_ONCE', 'RETRY_SCOPE_CHANGED')
    old = read_json(pin(manifest['pins']['original_discovery_returned']))
    prior = pin(manifest['pins']['original_discovery_stdout'])
    require(old['returncode'] == 0 and old['stdout_sha256'] == sha(prior)
        and read_json(prior).get('candidates') == [], 'ORIGINAL_NO_CANDIDATE_FAILURE_REQUIRED')
    import recovery_onboarding as original
    p = manifest['pins']['original_plan']
    X = original.Context(pin(p), p['sha256'])
    require_draft_unselected(X)
    X.base = NativePathEnvironment(X.base, X.P['native'])
    discover = original.commands(X)[0]
    if args.action == 'discover':
        pin(X.P['native'])
        value = original.Context.invoke(discovery_proxy(X), 'discover', discover)
        selected = X.validators.validate_inventory(value, X.P['native'])
        X.save('draft02-discover-retry1-validated.json', {'selected': selected,
            'native_parent_path_explicit': str(Path(X.P['native']['path']).resolve().parent),
            'original_discovery_preserved': True, 'provider_calls': 0})
    else:
        value = prior_discovery(X)
        X.validators.validate_inventory(value, X.P['native'])
        invoke = X.invoke

        def retained_discovery(name, argv, answers=None):
            if name == 'discover':
                require(argv == discover and answers is None, 'DISCOVERY_SELECTION_CHANGED')
                return value
            require(name == 'draft', 'ORIGINAL_DRAFT_ONLY')
            return invoke(name, argv, answers)

        X.invoke = retained_discovery
        original.draft(X)
    print('COMPLETED_' + args.action.upper())


if __name__ == '__main__':
    main()
