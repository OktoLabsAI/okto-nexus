"""Stop an isolated owner at the real owned-process registration boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

from okto_nexus.application.runtime_lifecycle import RuntimeLifecycle
from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process


def main():
    ready, cut = Path(sys.argv[1]), sys.argv[2]
    native_source = '''import json,os,subprocess,sys,time
grand = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=(os.name == "posix"), creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
print(json.dumps({"native_pid":os.getpid(),"grand_pid":grand.pid}),flush=True)
time.sleep(30)
'''

    class PausedRegistration(RuntimeLifecycle):
        def register(self, stop):
            process = stop.__self__
            family = json.loads(process.stdout.readline())
            if cut == "after_registration":
                super().register(stop)
            assert len(self._stops) == (1 if cut == "after_registration" else 0)
            marker = {**family, "owned_pid": process.pid, "owner_pid": os.getpid(),
                "registered": len(self._stops), "cut": cut}
            temporary = ready.with_suffix(".tmp")
            temporary.write_text(json.dumps(marker), encoding="utf-8")
            temporary.replace(ready)
            sys.stdin.read()  # Parent kills this owner before native handshake.

    with PausedRegistration().activate():
        spawn_owned_process([sys.executable, "-u", "-c", native_source], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            env={k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}})


if __name__ == "__main__":
    main()
