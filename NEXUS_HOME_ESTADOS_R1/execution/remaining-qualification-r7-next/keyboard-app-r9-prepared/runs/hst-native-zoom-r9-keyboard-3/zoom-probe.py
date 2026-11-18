"""Finite own HTTP calibration page, not Nexus and not an authoritative DTO."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import sys
import hashlib
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

HTML=b'<!doctype html><html lang="en"><meta charset="utf-8"><title>Own zoom calibration</title><body><h1>Own native zoom calibration</h1><p>Static local page. No CSS, scripts, accounts, application data or network resources.</p></body></html>'
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--window',required=True,choices=['ROOT_NATIVE_ZOOM_BROWSER_GUARD']);a=p.parse_args()
    root=a.root.resolve();assert root.name.startswith('nexus-hst-browser-')
    allocation=json.loads((root/'runtime-ready.json').read_text());assert Path(allocation['root']).resolve()==root and allocation['source_commit']=='f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            path=urlsplit(self.path).path;status=200 if path=='/probe' else 404
            body=HTML if status==200 else b'Not found';requests.append(dict(method=self.command,path=path,status=status))
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):self.send_response(405);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    ready=dict(pid=os.getpid(),root=str(root),worker=str(Path(__file__).resolve()),worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),prefix=sys.prefix,executable=sys.executable,base_executable=sys._base_executable,origin='http://127.0.0.1:'+str(server.server_port),scope='Static geometry calibration only; no Nexus import/process',duration_seconds=90)
    path=root/'control/zoom-probe-ready.json';assert not path.exists();path.write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(ready),flush=True)
    end=time.monotonic()+90
    try:
        while time.monotonic()<end and not(root/'control/zoom-probe-stop').exists():time.sleep(.1)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        (root/'control/zoom-probe-final.json').write_text(json.dumps(dict(requests=requests,server_thread_alive=thread.is_alive(),nexus_started=False),indent=2)+'\n')
if __name__=='__main__':main()
