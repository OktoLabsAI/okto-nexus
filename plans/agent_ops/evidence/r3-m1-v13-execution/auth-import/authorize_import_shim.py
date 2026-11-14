"""Load the exact publication module before the unchanged authorize driver."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys

def load_pinned(name,pin):
    path=Path(pin['path']).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('PIN_CHANGED')
    current=sys.modules.get(name)
    if current is not None:
        if Path(current.__file__).resolve()!=path:raise ValueError('IMPORT_ORIGIN_CHANGED')
        return current
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

def prepare(manifest):
    driver=manifest['original_authorize'];publication=manifest['publication']
    sys.path.insert(0,str(Path(driver['path']).parent))
    load_pinned('publication',publication)
    return load_pinned('authorize_local',driver)

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--manifest-sha256',required=True)
    args,original_args=p.parse_known_args()
    raw=Path(args.manifest).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.manifest_sha256:raise ValueError('SUPPLEMENT_MANIFEST_CHANGED')
    manifest=json.loads(raw)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=manifest['shim']['sha256']:raise ValueError('SHIM_CHANGED')
    module=prepare(manifest)
    parsed=module.parser();parsed.add_argument('phase',choices=['review','apply']);original=parsed.parse_args(original_args)
    context=module.gate(original)
    helper=load_pinned('authorize_import_supplement',manifest['supplement'])
    helper.validate_child(context,manifest,original.phase)
    previous=sys.argv
    try:
        sys.argv=[manifest['original_authorize']['path'],*original_args]
        return module.main_guard(module.main)
    finally:sys.argv=previous

if __name__=='__main__':raise SystemExit(main())
