"""Prepare audited offline verification scripts; no campaign effects."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
O=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5')
def save(name,value):
    p=R/name
    assert not p.exists(),p
    p.write_bytes(value.encode())
for name in ('bind_dependencies_and_qualified_wheels.py','run_preparation_checks.py','qualify_composed_observer.py'):
    s=(O/name).read_text().replace('v10','v11').replace('V10','V11')
    if name=='bind_dependencies_and_qualified_wheels.py':
        s=s.replace('Installed qualification and final review still pending.','Dependency-only target verification pending; no real approval.')
        s=s.replace("sources['installation/timed_install.py']['sha256']", "sources.setdefault('installation/timed_install.py',{'source_path':str(Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/draft/installation/timed_install.py'))})['sha256']")
    if name=='qualify_composed_observer.py':
        s=s.replace("POLICY['revision']==10 and POLICY['carry_in_admissions']==5 and POLICY['carry_in_tokens']==67658", "POLICY['revision']==11 and POLICY['carry_in_admissions']==6 and POLICY['carry_in_tokens']==89473")
        s=s.replace("POLICY['max_new_admissions']==6", "POLICY['max_new_admissions']==5")
        s=s.replace("str(D/'controller/test_work_wrapper.py'),", "str(D/'controller/test_work_wrapper.py'),str(D/'controller/test_reader_cache.py'),str(D/'controller/test_v11_allocation.py'),")
    save(name,s)
save('draft/test_preparation_entries.py',(O/'draft/test_preparation_entries.py').read_text().replace('v10','v11').replace('V10','V11'))
print(json.dumps({'status':'OFFLINE_SCRIPTS_ADAPTED','campaign_effects':0}))
