"""Materialize only the passive program for the specifically approved Codex run."""
import argparse
import hashlib
import json
from pathlib import Path

CAMPAIGN = 'dd47c48b74b44711bfb140b542ccbfcc'
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui042-codex-only-carry-' + CAMPAIGN)
ORIGIN = 'http://127.0.0.1:58107'
CANDIDATE_SHA = 'cc8888f6b09376cb575a184c1e46886e6f5175176f9169f043ac36944b5fbccf'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-execution-signal', required=True,
                        choices=['approved-and-observer-ready'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    candidate = repo / 'NEXUS_UI_R1/execution/pr07-native-codex-only-v2-carry/candidate-final.json'
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert ROOT.is_dir() and not ROOT.is_symlink()
    ready = json.loads((ROOT / 'public/observer-ready.json').read_text(encoding='utf8'))
    assert ready['campaign_id'] == CAMPAIGN and ready['origin'] == ORIGIN
    assert ready['no_new_productive_calls'] is True and ready['timeout_seconds'] == 180
    assert set(ready['sessions']) == {'codex_a', 'codex_b'}
    sessions = {}
    for client in ('codex_a', 'codex_b'):
        work = json.loads((ROOT / 'public' / (client + '.work.json')).read_text(encoding='utf8'))
        assert work['state'] == 'completed' and work['useful_result_verified'] is True
        assert work['session_id'] == ready['sessions'][client]
        sessions[client] = work['session_id']
    assert sessions['codex_a'] != sessions['codex_b']
    config = {'campaign_id': CAMPAIGN, 'origin': ORIGIN,
              'workspace_id': ready['workspace_id'], 'server_id': ready['server_id'],
              'sessions': sessions}
    template = Path(__file__).with_name('real_home_observer.template.js').read_text(encoding='utf8')
    template = template.replace("for(const client of ['codex','claude'])", 'for(const client of Object.keys(cfg.sessions))')
    assert "['codex','claude']" not in template
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assert not args.output.exists(), 'Preserve prior observer programs'
    args.output.write_text(template.replace('/* OBSERVER_CONFIG */null', json.dumps(config)), encoding='utf8')
    print(json.dumps({'prepared': str(args.output), 'campaign_id': CAMPAIGN,
                      'network_started': False, 'marker_written': False}))


if __name__ == '__main__':
    main()
