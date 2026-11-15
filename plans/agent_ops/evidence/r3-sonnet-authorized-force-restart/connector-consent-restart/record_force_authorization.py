from pathlib import Path
import hashlib, json, datetime, os
root = Path(__file__).resolve().parent
proposal = root / 'force-proposal.json'
expected = 'c35871e2af447c3532cb51dbc223bdb07a31807242c2abbe7187a88a7bea5a7e'
assert hashlib.sha256(proposal.read_bytes()).hexdigest() == expected
p = json.loads(proposal.read_bytes())
value = {
    'status': 'SPECIFIC_CONNECTOR_FORCE_AUTHORIZED',
    'proposal_sha256': expected,
    'target': p['target'],
    'max_canonical_force_calls': 1,
    'force_authorized': True,
    'user_message_reference': 'User message autorizado on 2026-11-15, directly after request for one canonical forced stop of Connector PID 36068 generation 8b35799e3ae1c6c3feec7cce45ee5162.',
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'observation_note': 'Original bounded observers expired before this reply; physical identity must be revalidated and fresh query/synchronize handles retained before the same authorized action. No extra force call authorized.'
}
target = root / 'force-authorization.json'
with target.open('x', encoding='utf-8') as f:
    json.dump(value, f, ensure_ascii=False, indent=2)
    f.write('\n'); f.flush(); os.fsync(f.fileno())
print(json.dumps({'authorization_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
