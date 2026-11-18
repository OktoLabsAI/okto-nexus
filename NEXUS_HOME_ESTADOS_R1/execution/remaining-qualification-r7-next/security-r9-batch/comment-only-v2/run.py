"""Approved comment-only template counterpart over the unchanged R9 driver."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
BASE_MANIFEST='a4709ef7f680c8fb61e9ac53ba005dfdd5885c0eb12e44cce69ad20ba2a6a43d'
OLD_COMMENT='  // __CONFIG__ is substituted only in an own Temp copy, never in this source.'
NEW_COMMENT='  // Configuration is substituted only in an own Temp copy, never in this source.'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(gate_path):
    gate=json.loads(gate_path.read_text())
    manifest=json.loads((HERE/'manifest.json').read_text())
    assert gate.get('approved') is True and gate.get('approved_by')=='root' and gate['case']=='S1'
    assert gate['manifest_sha256']==sha(BASE/'prepared-manifest.json')==BASE_MANIFEST
    assert gate['comment_variant_manifest_sha256']==sha(HERE/'manifest.json')
    assert gate['effective_template_sha256']==sha(HERE/'s1-passive.js')
    for name,pin in manifest['input_pins'].items():
        assert sha(BASE/name)==pin,name
    original=(BASE/'s1-passive.js').read_bytes()
    expected=original.replace(OLD_COMMENT.encode(),NEW_COMMENT.encode(),1)
    assert original.count(OLD_COMMENT.encode())==1
    assert (HERE/'s1-passive.js').read_bytes()==expected
    assert (HERE/'s1-passive.js').read_text().count('__CONFIG__')==1
    assert (BASE/'s1-revocation.js').read_text().count('__CONFIG__')==1
    return {'gate_sha256':sha(gate_path),'variant_manifest_sha256':sha(HERE/'manifest.json'),
            'base_manifest_sha256':BASE_MANIFEST,'effective_template_sha256':sha(HERE/'s1-passive.js')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gate',type=Path,required=True)
    args=parser.parse_args()
    before=validate(args.gate)  # Before delegation/allocation.
    spec=importlib.util.spec_from_file_location('unchanged_r9_security_driver',BASE/'run.py')
    driver=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    original_read=Path.read_text
    original_write=driver.write
    allocation=[]
    def read_template(path,*arguments,**keywords):
        text=original_read(path,*arguments,**keywords)
        if Path(path).resolve()==(BASE/'s1-passive.js').resolve():
            assert text.count(OLD_COMMENT)==1
            effective=text.replace(OLD_COMMENT,NEW_COMMENT,1)
            assert effective==original_read(HERE/'s1-passive.js',*arguments,**keywords)
            return effective
        return text
    def record(path,value):
        original_write(path,value)
        if path.name=='security-guard-before.json':
            allocation.append(path.parent)
            original_write(path.parent/'comment-variant-before.json',before)
    driver.write=record
    result=None
    try:
        # This affects only the exact host template read. The application is a
        # separate installed child process; no product/DTO/read is substituted.
        with patch.object(Path,'read_text',read_template):
            result=driver.main()
    finally:
        driver.write=original_write
        if allocation:
            root=allocation[0]
            try:
                after=validate(args.gate)
                unchanged=after==before
            except BaseException as error:
                after={'error_type':type(error).__name__}
                unchanged=False
            original_write(root/'comment-variant-after.json',dict(before=before,after=after,unchanged=unchanged))
            if not unchanged:
                result=1
    return result if result is not None else 1


if __name__=='__main__':
    raise SystemExit(main())
