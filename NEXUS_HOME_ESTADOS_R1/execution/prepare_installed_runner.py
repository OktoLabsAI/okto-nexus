"""Prepare only; never imports the application or launches test processes."""
from pathlib import Path

here = Path(__file__).resolve().parent
repo = here.parents[1]
target = here/'package-hst/installed_regression.py'
assert not target.exists(), 'Preserve an already-reviewed runner.'
s = (repo/'NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/installed_regression.py').read_text(encoding='utf-8')
s = s.replace('qc36', 'hst').replace('0.3.6', '0.3.7')
s = s.replace("    package=Path(json.loads", "    builder.source_ready()\n    package=Path(json.loads")
s = s.replace("    prefix=package/'venv'", "    assert ready['version']=='0.3.7' and ready['prefix_frozen'] is True\n    assert ready['source_commit']==builder.source_ready()['source_commit']\n    prefix=package/'venv'\n    assert Path(ready['python']).resolve()==(prefix/'Scripts/python.exe').resolve()")
s = s.replace("        assert len(result)==1028  # QC36 wheel has 733 Nexus files, including quick_connect_render.py.", "        assert len(result)==ready['payload_files'], (len(result),ready['payload_files'])")
s = s.replace("'-v','--tb=short','-x',", "'-v','--tb=short','-o','faulthandler_timeout=0',")
s = s.replace("        directory=root/name.lower();directory.mkdir();env[name]=str(directory)", "        directory=root/name.lower();env[name]=str(directory)\n        assert not directory.exists(), 'Provider-home precondition must remain nonexistent.'")
s = s.replace("    known={}\n", "    known={}\n    forced=False\n")
s = s.replace("                interrupted=time.monotonic()", "                interrupted=time.monotonic()\n                process.send_signal(signal.CTRL_BREAK_EVENT)\n                record['signals'].append(dict(kind='CTRL_BREAK_EVENT',pid=process.pid,scope='owned new process group; allows fixture canonical teardown'))")
s = s.replace("            time.sleep(.25)", """            if interrupted is not None and time.monotonic()-interrupted>30:
                # Every target was observed as a descendant of this exact launched process.
                # Recheck birth and image before containment; preserve all state on timeout.
                for info in reversed(list(known.values())):
                    try:
                        owned=psutil.Process(info['pid'])
                        if owned.create_time()!=info['birth'] or owned.exe()!=info['exe']:
                            continue
                        owned.kill()
                        record['signals'].append(dict(kind='OWNED_TIMEOUT_KILL',**info))
                        forced=True
                    except psutil.NoSuchProcess:
                        pass
                break
            time.sleep(.25)""")
s = s.replace("    after=payload()", """    remaining=[]
    for info in known.values():
        try:
            owned=psutil.Process(info['pid'])
            if owned.create_time()==info['birth'] and owned.exe()==info['exe']:
                remaining.append(info)
        except psutil.NoSuchProcess:
            pass
    record.update(timed_out=interrupted is not None,forced=forced,remaining_known_processes=remaining,
        observation_limit='250ms descendant polling does not enumerate every short-lived child; no claim that it does.')
    after=payload()""")
s = s.replace("raise SystemExit(record['exit_code'] or bool(record['payload_drift'] or record['source_drift']))", "raise SystemExit(record['exit_code'] or bool(record['payload_drift'] or record['source_drift'] or interrupted is not None or remaining))")
target.write_text(s,encoding='utf-8')
print(target)
