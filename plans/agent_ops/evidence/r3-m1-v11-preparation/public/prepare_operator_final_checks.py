"""Preserve prior reports and prepare only checks affected by the added executor."""
from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'verify_composed_final_origins.py').read_text().replace("Q=R/'final-composed-origins'","Q=R/'operator-final-origins'").replace('==45','==46').replace('all45','all46')
(R/'verify_operator_final_origins.py').write_bytes(s.encode())
s=(R/'qualify_reviewed_final_gates.py').read_text().replace("Q=R/'reviewed-final-entry-gates'","Q=R/'operator-final-entry-gates'").replace('14 real Python','20 real Python')
needle="assert all(p['base06_installation'][k]==v for k,v in pins.items())"
extra="""
recipe=json.loads(Path(p['execution_bundle']['files']['remote_canonical_recipe']['path']).read_bytes())
assert recipe['format']=='m1-v11-readonly-remote-recipe' and recipe['proposal_revision']==11
assert recipe['limits']['policy']==p['controller_preparation']['policy']
executor=recipe['operator_bootstrap']['executor']
assert executor['key']=='root_driver_operator_bootstrap' and executor['invoke_mode']=='operator_bootstrap' and executor['invoke_selection']==['once']
assert {key:executor[key] for key in ('path','sha256')}==p['execution_bundle']['files'][executor['key']]
assert p['authorization']['standing_user_authorization_received'] is True
assert p['authorization']['new_human_approval_of_hash_required'] is False
assert len(p['execution_bundle']['files'])==46
"""
assert needle in s;s=s.replace(needle,needle+'\n'+extra)
(R/'qualify_operator_final_gates.py').write_bytes(s.encode())
print('Prepared isolated46-pin imports and20 denial cases; prior reports preserved.')
