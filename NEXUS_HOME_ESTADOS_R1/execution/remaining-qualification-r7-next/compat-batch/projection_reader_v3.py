"""PREPARED real loopback GETs with actual /info negotiation; no response rewriting."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


def load_snapshot(path):
    spec = importlib.util.spec_from_file_location('compat_history_read', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.snapshot


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_BATCH'], required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--workspace-id', required=True)
    parser.add_argument('--operator-cookie-file', type=Path, required=True)
    parser.add_argument('--phase', choices=['s4-old', 's4-current'], required=True)
    args = parser.parse_args()
    assert hashlib.sha256(args.manifest.read_bytes()).hexdigest() == args.manifest_sha256
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    history = Path(manifest['history_helper'])
    assert hashlib.sha256(history.read_bytes()).hexdigest() == manifest['helper_sha256'][str(history)]
    snapshot = load_snapshot(history)
    root, home = args.root.resolve(), args.home.resolve()
    assert root.name.startswith('nexus-hst-compat-') and home.is_relative_to(root)
    assert args.origin.startswith('http://127.0.0.1:')
    cookie = json.loads(args.operator_cookie_file.read_text(encoding='utf-8'))['cookie']
    opener = build_opener(ProxyHandler({}))

    def get(path):
        request = Request(args.origin + path, headers={'X-Nexus-UI':'1','X-Nexus-Operator-Session-Required':'1','Cookie':'nexus_operator_session='+cookie})
        with opener.open(request, timeout=10) as response:
            value = json.load(response)
        return value.get('data', value)

    info = get('/api/v1/info')
    offered = info.get('home_presentation_versions', [])
    if args.phase == 's4-old':
        assert 2 not in offered, 'Old phase must prove real capability absence'
    else:
        assert 2 in offered
    params = {'workspace_id': args.workspace_id}
    if 2 in offered:
        params['presentation_version'] = 2
    before = snapshot(home)
    board = get('/api/v1/home/harness-board?' + urlencode(params))
    results = get('/api/v1/home/results?' + urlencode({'workspace_id': args.workspace_id}))
    assert results['items'], 'Require actual old/current projected result, not two empty ID sets'
    after = snapshot(home)
    assert before == after, 'Projection rewrote protected receipts/hashes/grants/IDs'
    if args.phase == 's4-current':
        copied = json.loads((root / 'control/history-copy.json').read_text(encoding='utf-8'))
        assert copied['old'] == before, 'Current startup/projection changed old protected facts'
        legacy = json.loads((root / 'control/projection-s4-old.json').read_text(encoding='utf-8'))
        assert {row['id'] for row in legacy['results']['items']} == {row['id'] for row in results['items']}
    public = {'phase': args.phase, 'info': info, 'offered_presentation_versions': offered,
        'query_parameters': params, 'board': board, 'results': results,
        'protected_before': before, 'protected_after': after,
        'protected_equal': True, 'source': 'Actual HTTP responses, not patched DTOs'}
    path = root / 'control' / ('projection-' + args.phase + '.json')
    path.write_text(json.dumps(public, indent=2), encoding='utf-8')
    print(json.dumps({'phase': args.phase, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'protected_equal': True, 'offered_v2': 2 in offered}))


if __name__ == '__main__':
    main()
