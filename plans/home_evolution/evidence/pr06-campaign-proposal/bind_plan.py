"""Prepare an inert candidate, then bind ONLY an actual consent receipt to its hash.
No CLI product handlers, services, native process or user config/auth reads here.
"""
from pathlib import Path
import argparse
import base64
from importlib import metadata, import_module
import json
import sys
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).parent))
from driver import sha, publish, POLICY, consent_valid
from usage import require, owned

FINAL_WHEEL_SHA='c41f00cb3d1702df351c2e15ebee8c14c3eb238b67b7631a1604a8d7ec8df190'


def package_snapshot(wheel, qualification, qualification_sha):
    require(sha(wheel)==FINAL_WHEEL_SHA,'FINAL_WHEEL_CHANGED')
    require(sha(qualification)==qualification_sha,'PACKAGE_QUALIFICATION_CHANGED')
    tested=json.loads((Path(__file__).parent/'parser-origins.json').read_text())
    for item in tested['origins']:
        module=import_module(item['module']) # import only; no CLI handler call.
        require(sha(module.__file__)==item['sha256'],'PARSER_CHANGED_REQUALIFY_FOCAL_ONLY')
    prefix=Path(sys.prefix).resolve(); payload=[];versions={}
    for name,expected in [('okto-nexus','0.3.4'),('okto-nexus-connector-core','0.0.14')]:
        dist=metadata.distribution(name);require(dist.version==expected,'PACKAGE_VERSION_CHANGED')
        versions[name]=dist.version
        for entry in dist.files or []:
            if entry.suffix=='.pyc' or entry.hash is None:continue
            target=Path(dist.locate_file(entry)).resolve()
            require(target.is_relative_to(prefix),'INSTALLED_ORIGIN_OUTSIDE_PREFIX')
            digest=sha(target)
            require(entry.hash.mode=='sha256' and base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip('=')==entry.hash.value,
                    'INSTALLED_RECORD_MISMATCH')
            payload.append({'path':str(target),'sha256':digest})
    # Check actual Nexus wheel payload bytes against this prefix, not just RECORD.
    dist=metadata.distribution('okto-nexus')
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith('okto_nexus/'):continue
            target=Path(dist.locate_file(entry.filename)).resolve()
            require(target.is_relative_to(prefix) and target.read_bytes()==archive.read(entry),'FINAL_WHEEL_PAYLOAD_CHANGED')
    require(len(payload)>100,'PAYLOAD_REQUIRED')
    images={}
    for image in {Path(sys.executable),Path(sys.executable).with_name('pythonw.exe'),
                  Path(sys._base_executable),Path(sys._base_executable).with_name('pythonw.exe')}:
        require(image.is_file(),'PYTHON_IMAGE_MISSING');images[str(image.resolve())]=sha(image)
    return {'python':{'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable)},
            'python_images':images,'package':{'installed_payloads_verified':True,'payload_pins':payload,
             'versions':versions,'wheel':{'path':str(Path(wheel).resolve()),'sha256':FINAL_WHEEL_SHA},
             'qualification_path':str(Path(qualification).resolve()),'qualification_sha256':qualification_sha}}


def make_candidate(*, campaign_parent, port, package, codex_root, codex_executable, codex_sha256):
    require(49152<=port<=65535,'HIGH_LOCAL_PORT_REQUIRED')
    native=owned(Path(codex_root),Path(codex_executable))
    require(sha(native)==codex_sha256,'NATIVE_EXECUTABLE_CHANGED')
    from nexus_connector_core.installation import installation_ref
    # Pure canonical path-reference derivation. The Server must subsequently return
    # this exact candidate in fresh runtime-options after consent; this is no inventory claim.
    ref=installation_ref('codex_app_server',str(native.resolve()))
    campaign_id='home-r1-local-codex-'+uuid.uuid4().hex[:12]
    root=Path(campaign_parent).resolve()/campaign_id
    require(not root.exists(),'FRESH_CAMPAIGN_ROOT_REQUIRED')
    pins=[{'path':str(f.resolve()),'sha256':sha(f)} for f in Path(__file__).parent.glob('*.py')]
    pins.append({'path':str((Path(__file__).parent/'parser-origins.json').resolve()),
                 'sha256':sha(Path(__file__).parent/'parser-origins.json')})
    return {'schema_version':2,'artifact_kind':'INERT_TECHNICAL_CANDIDATE','inert_without_bound_authorization':True,
          'technical_ready':True,'campaign_id':campaign_id,'campaign_root':str(root),'port':port,'policy':POLICY,
          **package,'pins':pins,'codex_root':str(Path(codex_root).resolve()),'codex_executable':str(native.resolve()),
          'codex_content_fingerprint':codex_sha256,'codex_candidate_ref':ref,'provider_home':'C:/Users/jpamb/.codex',
          'scope_paths':{name:str(root/name) for name in ('nexus-home','workspace','deliverables','public','private')},
          'request_ids':{'useful':'home-r1-local-useful-02','interrupt':'home-r1-interrupt-01','close':'home-r1-close-01'},
          'setup_intent':'generated once by canonical connect --plan and pinned before any apply; not an invented Server ID',
          'effects':['Create only these campaign directories and synthetic CSV','Install own user Task Scheduler service with login trigger',
                     'Start own Nexus and local application operator bootstrap','One paid local setup test and one paid useful task',
                     'Real native decision only if emitted; presentation toggle only on own browser',
                     'Normal cleanup then necessary canonical force only for current own instance; uninstall own task, preserve data'],
          'ambient_native_configuration':'Existing CLI account, model, MCP and instruction configuration may be inherited. '
              'No isolation or enforcement claim. Capability/effective metadata inspection occurs after consent before paid apply; '
              'no reading auth.json or dumping personal configuration.',
          'own_cleanup_force_within_standing_stop_authority':True}


def authorize_candidate(candidate_path, candidate_sha, *, user_response_reference, acknowledges_delayed_usage_overshoot, output):
    require(sha(candidate_path)==candidate_sha,'CANDIDATE_CHANGED')
    candidate=json.loads(Path(candidate_path).read_text(encoding='utf-8'))
    require(candidate['artifact_kind']=='INERT_TECHNICAL_CANDIDATE' and candidate['policy']==POLICY,'CANDIDATE_INVALID')
    require(isinstance(user_response_reference,str) and user_response_reference and
            acknowledges_delayed_usage_overshoot is True,'ACTUAL_USER_CONSENT_REQUIRED')
    record={'schema_version':1,'candidate_sha256':candidate_sha,'campaign_id':candidate['campaign_id'],
            'campaign_root':candidate['campaign_root'],'policy':POLICY,'user_authorized_paid_campaign':True,
            'user_response_reference':user_response_reference,'acknowledges_delayed_usage_overshoot':True,
            'scope':'Only this candidate, namespace and two-call ledger. No family consent or fresh baseline reuse.'}
    consent_valid(candidate,record,candidate_sha)
    publish(output,record) # Candidate bytes/home/pins/IDs are never rewritten.
    require(sha(candidate_path)==candidate_sha,'CANDIDATE_CHANGED_DURING_AUTH_BIND')
    return record


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='action',required=True)
    create=sub.add_parser('candidate')
    for name in ('output','campaign-parent','wheel','package-qualification','package-qualification-sha256',
                 'codex-root','codex-executable','codex-sha256'):create.add_argument('--'+name,required=True)
    create.add_argument('--port',required=True,type=int)
    auth=sub.add_parser('authorize')
    for name in ('candidate','candidate-sha256','user-response-reference','output'):auth.add_argument('--'+name,required=True)
    auth.add_argument('--acknowledges-delayed-usage-overshoot',action='store_true',required=True)
    a=p.parse_args()
    if a.action=='candidate':
        package=package_snapshot(a.wheel,a.package_qualification,a.package_qualification_sha256)
        candidate=make_candidate(campaign_parent=a.campaign_parent,port=a.port,package=package,
                    codex_root=a.codex_root,codex_executable=a.codex_executable,codex_sha256=a.codex_sha256)
        publish(a.output,candidate)
        print(json.dumps({'candidate_path':str(Path(a.output).resolve()),'candidate_sha256':sha(a.output),
                          'campaign_root_created':False,'provider_calls':0,'authorization_present':False}))
    else:
        record=authorize_candidate(a.candidate,a.candidate_sha256,user_response_reference=a.user_response_reference,
            acknowledges_delayed_usage_overshoot=a.acknowledges_delayed_usage_overshoot,output=a.output)
        print(json.dumps({'authorization_path':str(Path(a.output).resolve()),'authorization_sha256':sha(a.output),
                          'candidate_sha256':record['candidate_sha256'],'candidate_unchanged':True,'provider_calls':0}))


if __name__=='__main__':main()
