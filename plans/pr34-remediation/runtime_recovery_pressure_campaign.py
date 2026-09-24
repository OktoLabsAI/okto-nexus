"""Repeated production crash/recovery cycles with measured bounded CPU pressure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from runtime_crash_pressure_campaign import PIN, LOAD, REPO, load_snapshot, resources
import test_runtime_relay_process_restart as scenarios


def campaign(cycles, output):
    assert 4 <= cycles <= 8
    result = {"status": "RUNNING", "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],cwd=REPO,text=True).strip(),
        "campaign_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_sha256": hashlib.sha256(Path(__file__).with_name("runtime_crash_pressure_campaign.py").read_bytes()).hexdigest(),
        "scenario_sha256": hashlib.sha256(Path(scenarios.__file__).read_bytes()).hexdigest(),
        "platform": sys.platform, "readiness_timeout_seconds": 60, "load_safety_deadline_seconds": 900, "warmup_cycles": 2, "measured_cycles": cycles, "samples": [],
        "limitations": ["Owned synthetic Codex protocol peer; no provider/model", "Two bounded workers pinned with each owner to one allowed CPU",
            "Each cycle crashes and recovers the same store; fresh store between cycles", "Application clock offset600s exercises expired-owner recovery; host clock unchanged",
            "Python dependencies load before CPU pin; application main/bootstrap, traffic, crash, recovery and teardown run pinned under load",
            "Not a comparative throughput/latency benchmark; not proof about arbitrary hosts or native providers"]}
    original_owner, original_popen = scenarios.Owner, subprocess.Popen
    instances, owner_samples, recovered_peer_stops = [], [], []
    def pinned_popen(args, *positional, **kwargs):
        if isinstance(args, list) and len(args) > 1 and Path(args[1]).name == "runtime_relay_process_fixture.py":
            prefix = ("import runpy,sys,faulthandler\nfaulthandler.dump_traceback_later(30,repeat=True)\n"
                "script=sys.argv.pop(1);sys.argv[0]=script;loaded=runpy.run_path(script,run_name='fixture_loaded')\n"
                "from okto_nexus.adapters.inbound.mcp.server import _load_fastmcp\n_load_fastmcp()\n")
            args = [args[0], "-c", prefix + PIN + "\nloaded['main']()", *args[1:]]
        return original_popen(args, *positional, **kwargs)

    class MeasuredOwner(original_owner):
        def __init__(self, *args, **kwargs):
            self.pressure_cut = args[2] if len(args) > 2 else kwargs["cut"]
            try:
                super().__init__(*args, ready_timeout=60, **kwargs)
            except BaseException:
                result["owner_failure_log_tail"] = self.log_path.read_text(encoding="utf-8")[-8000:]
                raise
            instances.append(self)
            sample = resources(self.ready["owner_pid"])
            assert len(sample["affinity"]) == 1
            owner_samples.append(sample)

        def close(self):
            witnesses = []
            try:
                if self.pressure_cut == "none" and hasattr(self, "ready") and self.process.poll() is None:
                    for path in self.home.glob(f"native-{self.ready['owner_pid']}-*.jsonl"):
                        for line in path.read_text(encoding="utf-8").splitlines():
                            row = json.loads(line)
                            if "fixture_pid" in row:
                                witnesses.append(scenarios.PeerWitness(row["fixture_pid"]))
            finally:
                try:
                    super().close()
                    for witness in witnesses:
                        witness.assert_stopped()
                    if self.pressure_cut == "none":
                        recovered_peer_stops.append(len(witnesses))
                finally:
                    for witness in witnesses:
                        witness.close()

    with tempfile.TemporaryDirectory(prefix="okto-recovery-pressure-") as directory:
        root = Path(directory)
        script = root / "load.py"
        script.write_text(LOAD.replace("deadline=began+300", "deadline=began+900"),encoding="utf-8")
        env = {k:v for k,v in os.environ.items() if k.upper() in {"PATH","SYSTEMROOT","WINDIR","TEMP","TMP"}}
        env.update(HOME=str(root),USERPROFILE=str(root),PYTHONIOENCODING="utf-8")
        workers=[]
        worker_logs=[]
        try:
            for index in range(2):
                log=(root/f"load-{index}.log").open("w",encoding="utf-8")
                worker_logs.append(log)
                workers.append(original_popen([sys.executable,str(script),str(root),f"load-{index}"],env=env,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            deadline=time.monotonic()+10
            while not all((root/f"load-{i}.json").exists() for i in range(2)):
                assert time.monotonic()<deadline and all(p.poll() is None for p in workers)
                time.sleep(.02)
            (root/"active").touch()
            time.sleep(.3)
            scenarios.Owner=MeasuredOwner
            subprocess.Popen=pinned_popen
            for index in range(cycles+2):
                assert all(p.poll() is None for p in workers)
                before=load_snapshot(root)
                directory=root/f"cycle-{index}"
                directory.mkdir()
                cut,exit_code=("journal_terminal",73) if index%2==0 else ("accepted_child",75)
                began=time.monotonic()
                scenarios.test_whole_owner_crash_preserves_relay_lineage_and_never_replays_ambiguous_child(
                    directory,cut,exit_code,600)
                elapsed=time.monotonic()-began
                assert len(instances)==2 and all(p.process.poll() is not None for p in instances)
                after=load_snapshot(root)
                span=max(b["wall_seconds"]-a["wall_seconds"] for a,b in zip(before,after))
                cpu=sum(b["cpu_seconds"]-a["cpu_seconds"] for a,b in zip(before,after))
                assert span>0 and cpu/span>.25, (before,after)
                assert all(b["iterations"]>a["iterations"] for a,b in zip(before,after))
                assert all(s["affinity"]==[after[0]["affinity"]] for s in owner_samples)
                assert len({r["affinity"] for r in after})==1
                sample={"cycle":index,"cut":cut,"seconds":elapsed,"owners_started_and_stopped":len(instances),
                    "owner_resources":list(owner_samples),"cpu_load_fraction":cpu/span,"load_cpu_seconds":cpu,"load_wall_seconds":span,
                    "load_iterations_delta":sum(b["iterations"]-a["iterations"] for a,b in zip(before,after)),
                    "recovered_peer_stops":sum(recovered_peer_stops),
                    "same_operation_recovered":True,"ambiguous_native_write_replayed":False,"wire_effects_match_operations":True}
                assert sum(recovered_peer_stops) == (1 if cut == "journal_terminal" else 0)
                instances.clear()
                owner_samples.clear()
                recovered_peer_stops.clear()
                sample["campaign_after_cleanup"]=resources()
                if index==1:
                    result["baseline"]=sample["campaign_after_cleanup"]
                if index>=2:
                    result["samples"].append(sample)
                print(json.dumps({"cycle":index,"cut":cut,"seconds":elapsed,"cpu_load_fraction":cpu/span}),flush=True)
            baseline=result["baseline"]
            result["limits"]={"rss_bytes":baseline["rss_bytes"]+16*1024*1024,
                "handles_or_fds":baseline["handles_or_fds"]+8,"python_threads":baseline["python_threads"]+2}
            assert all(s["campaign_after_cleanup"][k]<=v for s in result["samples"] for k,v in result["limits"].items())
            result["status"]="PASS"
        except BaseException as exc:
            result["status"]="FAIL"
            result["failure_type"]=type(exc).__name__
            raise
        finally:
            scenarios.Owner=original_owner
            subprocess.Popen=original_popen
            (root/"stop").touch()
            for process in workers:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            result["load_workers_reaped"]=all(p.poll() is not None for p in workers)
            result["load_worker_exit_codes"]=[p.returncode for p in workers]
            for log in worker_logs:
                log.close()
            result["load_worker_errors"]=[(root/f"load-{index}.log").read_text(encoding="utf-8")[-4000:] for index in range(len(worker_logs))]
            output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--cycles",type=int,default=6)
    args=parser.parse_args()
    result=campaign(args.cycles,args.output)
    print(json.dumps({"status":result["status"],"measured_cycles":result["measured_cycles"]}),flush=True)


if __name__=="__main__":
    main()
