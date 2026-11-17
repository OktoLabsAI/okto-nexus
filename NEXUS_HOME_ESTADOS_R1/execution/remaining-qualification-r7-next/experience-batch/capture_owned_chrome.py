"""Read argv only for the actual own-profile Chrome during the authorized cut."""
import argparse
import json
from pathlib import Path
import tempfile
import time
import psutil

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--window',required=True,choices=['ROOT_R9_FOCUS_OPEN']);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')and root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    config=json.loads((root/'runtime-ready.json').read_text());assert config['source_commit']=='f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
    marker=str(root/'browser-profile').lower();records=[];end=time.monotonic()+35
    while time.monotonic()<end and not records:
        for process in psutil.process_iter(['pid','create_time','exe','cmdline']):
            try:
                row=process.info;argv=row['cmdline']or[]
                if marker not in ' '.join(argv).lower():continue
                if Path(row['exe']or'').name.lower()!='chrome.exe':continue
                assert not any('--api-key'in arg.lower()or'?api_key='in arg.lower()for arg in argv)
                records.append(dict(pid=row['pid'],birth=row['create_time'],exe=row['exe'],argv=argv,ownership='Actual argv contains exact own browser-profile path'))
            except(psutil.NoSuchProcess,psutil.AccessDenied):pass
        if not records:time.sleep(.1)
    result=dict(status='CAPTURED_ACTUAL_OWN_CHROME'if records else'NOT_OBSERVED',records=records,limits=['No environment read','No other browser/profile inspected','No process launch or termination performed by this observer','Only exact-profile argv matches are captured; not a complete child-tree inventory'])
    output=root/'chrome-process-capture.json';assert not output.exists();output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],path=str(output),processes=len(records))))
if __name__=='__main__':main()
