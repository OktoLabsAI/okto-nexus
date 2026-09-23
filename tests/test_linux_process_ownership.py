"""Standalone stdlib Linux ownership checks; no provider, store or credentials.

Can run directly with python -m unittest; full Nexus requires Python >=3.11.
"""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from okto_nexus.adapters.outbound.harness.linux_process_guardian import pidfd_open, pidfd_send_signal


@unittest.skipUnless(sys.platform == "linux", "NOT_RUN: Linux pidfd test")
class LinuxOwnershipTests(unittest.TestCase):
    def test_native_stream_eof_is_independent_of_process_exit(self):
        import threading
        from okto_nexus.adapters.outbound.harness.linux_process import OwnedLinuxPopen
        process = OwnedLinuxPopen([sys.executable, "-u", "-c",
            "import os,time;print('ready',flush=True);os.close(1);time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={"PATH": os.defpath})
        observed = threading.Event()
        reader = threading.Thread(target=lambda: (process.stdout.read(), observed.set()), daemon=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            reader.start()
            self.assertTrue(observed.wait(3), "guardian masks the native stream EOF")
            self.assertIsNone(process.poll())
            self.assertFalse(process.tree_stopped)
        finally:
            process.kill()
            process.wait(timeout=5)
            reader.join(3)
            process.stdout.close()
            process.stderr.close()

    def test_pidfd_without_python_wrappers_uses_kernel_identity(self):
        from unittest.mock import patch
        if os.uname().machine != "x86_64":
            self.skipTest("Raw pidfd syscall ABI is only qualified on x86-64")
        with patch.object(os, "pidfd_open", None, create=True), patch.object(signal, "pidfd_send_signal", None, create=True):
            descriptor = pidfd_open(os.getpid())
            try:
                self.assertFalse(os.get_inheritable(descriptor))
                pidfd_send_signal(descriptor, 0)
            finally:
                os.close(descriptor)

    def test_capacity_is_held_until_observed_cleanup(self):
        import threading
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from okto_nexus.adapters.outbound.harness.linux_process import OwnedLinuxPopen
        with patch.object(OwnedLinuxPopen, "_slots", threading.BoundedSemaphore(1)):
            process = OwnedLinuxPopen([sys.executable, "-c", "import time;time.sleep(60)"],
                                     env={"PATH": os.defpath})
            try:
                with self.assertRaisesRegex(RuntimeError, "capacity"):
                    OwnedLinuxPopen([sys.executable, "-c", "pass"])
            finally:
                process.kill()
                process.wait(timeout=5)
            replacement = OwnedLinuxPopen([sys.executable, "-c", "pass"], env={"PATH": os.defpath})
            self.assertEqual(replacement.wait(timeout=5), 0)
            self.assertTrue(replacement.tree_stopped)

    def test_terminate_preserves_native_graceful_exit_status(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process
        process = spawn_owned_process([sys.executable, "-u", "-c",
            "import signal,sys,time;signal.signal(signal.SIGTERM,lambda *_:sys.exit(23));print('ready',flush=True);time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={"PATH": os.defpath})
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            process.terminate()
            self.assertEqual(process.wait(timeout=5), 23)
            self.assertTrue(process.tree_stopped)
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_normal_leader_exit_reaps_escaped_child_without_touching_bystander(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process
        code = ("import subprocess,sys,json,os\n"
            "extra=[]\n"
            "for fd in range(3,64):\n"
            " try: os.fstat(fd);extra.append(fd)\n"
            " except OSError: pass\n"
            "grand=subprocess.Popen([sys.executable,'-u','-c',\"import os,time;os.setsid();print('ready',flush=True);time.sleep(60)\"],stdout=subprocess.PIPE,text=True)\n"
            "assert grand.stdout.readline().strip()=='ready'\n"
            "print(json.dumps([grand.pid,extra]),flush=True)\ninput()\n")
        bystander = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"], env={"PATH": os.defpath})
        process = spawn_owned_process([sys.executable, "-u", "-c", code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env={"PATH": os.defpath})
        descriptor = None
        try:
            pid, extra = json.loads(process.stdout.readline())
            self.assertEqual(extra, [], "native peer inherited guardian control/proof handles")
            descriptor = pidfd_open(pid)
            process.stdin.write("done\n")
            process.stdin.flush()
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertTrue(process.tree_stopped)
            with selectors.DefaultSelector() as dead:
                dead.register(descriptor, selectors.EVENT_READ)
                self.assertTrue(dead.select(2))
            self.assertIsNone(bystander.poll())
        finally:
            if descriptor is not None:
                try:
                    pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.close(descriptor)
            process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
            bystander.kill()
            bystander.wait(timeout=5)

    def test_observed_stop_requires_tree_cleanup_proof(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process, observe_owned_process
        for guardian_crash in (False, True):
            with self.subTest(guardian_crash=guardian_crash):
                process = spawn_owned_process([sys.executable, "-u", "-c",
                    "import os,time;print(os.getpid(),flush=True);time.sleep(60)"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env={"PATH": os.defpath})
                descriptor = pidfd_open(int(process.stdout.readline().strip()))
                try:
                    if guardian_crash:
                        # Our direct unreaped child cannot have a recycled PID.
                        os.kill(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait(timeout=5)
                    self.assertEqual(observe_owned_process(process)["stop_observed"], not guardian_crash)
                    if not guardian_crash:
                        with selectors.DefaultSelector() as dead:
                            dead.register(descriptor, selectors.EVENT_READ)
                            self.assertTrue(dead.select(2))
                    process.kill()
                    self.assertEqual(process.tree_stopped, not guardian_crash)
                finally:
                    try:
                        pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(descriptor)
                    process.kill()
                    process.wait(timeout=5)
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        pipe.close()

    def test_partial_descriptor_failure_does_not_leak(self):
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from okto_nexus.adapters.outbound.harness.linux_process import OwnedLinuxPopen
        before = len(list(Path("/proc/self/fd").iterdir()))
        with patch("os.pipe", side_effect=OSError("fixture FD pressure")):
            with self.assertRaises(OSError):
                OwnedLinuxPopen([sys.executable, "-c", "pass"])
        self.assertEqual(before, len(list(Path("/proc/self/fd").iterdir())))

    def test_owner_sigkill_reaps_escaped_grandchild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / "child.py"
            child.write_text("import subprocess,sys,os,time,json\n"
                "grand=subprocess.Popen([sys.executable,'-u','-c',\"import os,time;os.setsid();print('ready',flush=True);time.sleep(60)\"],stdout=subprocess.PIPE,text=True)\n"
                "assert grand.stdout.readline().strip()=='ready'\n"
                "print(json.dumps([os.getpid(),grand.pid]),flush=True)\ntime.sleep(60)\n")
            owner = root / "owner.py"
            owner.write_text("import subprocess,sys,time,os\n"
                "from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process\n"
                "p=spawn_owned_process([sys.executable,'-u',sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'PATH':os.defpath})\n"
                "print(p.stdout.readline(),flush=True)\ntime.sleep(60)\n")
            env = {"PATH": os.defpath, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
            process = subprocess.Popen([sys.executable, "-u", str(owner), str(child)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            descriptors = []
            try:
                with selectors.DefaultSelector() as ready:
                    ready.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(ready.select(8), "owner failed to start disposable tree")
                line = process.stdout.readline().strip()
                self.assertTrue(line, process.stderr.read() if process.poll() is not None else "empty process line")
                pids = json.loads(line)
                descriptors = [pidfd_open(pid) for pid in pids]
                process.kill()
                process.wait(timeout=5)
                for descriptor in descriptors:
                    with selectors.DefaultSelector() as dead:
                        dead.register(descriptor, selectors.EVENT_READ)
                        self.assertTrue(dead.select(5), "owner death left an owned descendant alive")
            finally:
                for descriptor in descriptors:
                    try:
                        pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(descriptor)
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
