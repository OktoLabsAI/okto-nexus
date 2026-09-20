"""INT-08 repro: a non-JSON stdin line against the real ``claude`` binary,
verifying the module docstring's documented fatal-exit(1) claim."""

import subprocess

argv = ["claude", "-p", "--output-format", "stream-json", "--input-format", "stream-json",
        "--verbose", "--include-partial-messages"]
proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1, encoding="utf-8", errors="replace")
proc.stdin.write("not valid json at all\n")
proc.stdin.flush()
proc.stdin.close()
try:
    code = proc.wait(timeout=15)
except subprocess.TimeoutExpired:
    code = None
    proc.kill()
stdout = proc.stdout.read()
stderr = proc.stderr.read()
print("exit_code:", code)
print("stdout:", repr(stdout))
print("stderr:", repr(stderr))
