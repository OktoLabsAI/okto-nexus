from pathlib import Path
import hashlib
import json
import datetime
import os

root = Path(__file__).resolve().parent
plan_path = root / 'rotation-plan.json'
expected = '5e9b827c0141d95c9b6d88cf7fec47344325449a1d85a25b43f989256e92e2c2'
assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == expected
plan = json.loads(plan_path.read_bytes())
target = Path(plan['authorization_receipt'])
assert target == root / 'public' / 'rotation-specific-authorization.json'
value = {
    'status': 'SPECIFIC_EXCEPTION_AUTHORIZED',
    'rotation_plan_sha256': expected,
    'agent_id': plan['agent_id'],
    'revoke_lost_epoch': 1,
    'plaintext_file_path': plan['plaintext_file_path'],
    'user_authorization_reference': 'User message 2026-11-15: autorizado, in direct response to explicit lost agent key revocation and unencrypted Windows ACL-restricted storage proposal.',
    'user_text': 'autorizado',
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'sonnet_token_limit': 200000,
    'os_event_window': 'NOT_YET_SCHEDULED',
    'force_service_stop_authorized': False,
}
with target.open('x', encoding='utf-8') as output:
    json.dump(value, output, ensure_ascii=False, indent=2)
    output.write('\n')
    output.flush()
    os.fsync(output.fileno())
print(json.dumps({'authorization_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'status': value['status']}))
