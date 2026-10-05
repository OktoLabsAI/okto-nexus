"""Raw wire-trace capture against the REAL claude binary, bypassing the
connector entirely (direct subprocess), to get authoritative captured bytes
for INT-02/03/04 and RES-C1/C2 citation.

Spawns: claude -p --output-format stream-json --input-format stream-json
        --verbose --include-partial-messages
(the exact argv claude_code_stream.py's _DEFAULT_ARGV uses).

Logs every stdout line and every stdin write with monotonic + wall-clock
timestamps, to prove:
 - zero client-initiated requests between the prompt write and the
   turn's completion (INT-04 no-polling proof)
 - the exact native event shapes/ordering the fake script must mirror
   (RES-C1)
 - interrupt/control_request ordering against a real in-flight turn
   (RES-C2 / INT-06)
"""
import json
import subprocess
import threading
import time

t_start = time.monotonic()

def ts():
    return f"{time.monotonic() - t_start:8.4f}s"

log_lines = []

def log(direction, text):
    line = f"[{ts()}] {direction} {text}"
    log_lines.append(line)
    print(line, flush=True)

argv = ["claude", "-p", "--output-format", "stream-json", "--input-format", "stream-json",
        "--verbose", "--include-partial-messages"]
log("SPAWN", " ".join(argv))

proc = subprocess.Popen(
    argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, bufsize=1, encoding="utf-8", errors="replace",
)

stderr_lines = []


def drain_stderr():
    for line in proc.stderr:
        stderr_lines.append(line.rstrip("\n"))


threading.Thread(target=drain_stderr, daemon=True).start()

def write_line(obj):
    line = json.dumps(obj)
    log("WRITE", line)
    proc.stdin.write(line + "\n")
    proc.stdin.flush()

# --- Turn 1: trivial prompt ---
write_line({"type": "user", "message": {"role": "user", "content": "reply with the single word: ok"}})

session_id_seen = None
saw_generating = False
interrupt_sent = False
turn1_done = False

deadline = time.monotonic() + 40
while time.monotonic() < deadline and not turn1_done:
    raw = proc.stdout.readline()
    if raw == "":
        log("EOF", "stdout closed unexpectedly during turn 1")
        break
    raw = raw.rstrip("\n")
    if not raw:
        continue
    log("READ", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if obj.get("type") == "system" and obj.get("subtype") == "init":
        session_id_seen = obj.get("session_id")
    if obj.get("type") == "result":
        turn1_done = True

log("MARK", f"turn1 complete, session_id={session_id_seen}")

# --- Turn 2: verify session persists WITHIN this same process ---
write_line({"type": "user", "message": {"role": "user", "content": "reply with the single word: still-alive"}})
turn2_done = False
turn2_session_id = None
deadline = time.monotonic() + 40
while time.monotonic() < deadline and not turn2_done:
    raw = proc.stdout.readline()
    if raw == "":
        log("EOF", "stdout closed unexpectedly during turn 2")
        break
    raw = raw.rstrip("\n")
    if not raw:
        continue
    log("READ", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if obj.get("type") == "system" and obj.get("subtype") == "init":
        turn2_session_id = obj.get("session_id")
    if obj.get("type") == "result":
        turn2_done = True

log("MARK", f"turn2 complete, session_id={turn2_session_id}, same_as_turn1={turn2_session_id == session_id_seen}")

# --- Turn 3: interrupt-ordering capture (RES-C2/INT-06) ---
write_line({"type": "user", "message": {"role": "user", "content": "Write the numbers 1 to 40, one per line, nothing else. Do not stop early."}})
generating = False
turn3_done = False
deadline = time.monotonic() + 40
while time.monotonic() < deadline and not turn3_done:
    raw = proc.stdout.readline()
    if raw == "":
        log("EOF", "stdout closed unexpectedly during turn 3")
        break
    raw = raw.rstrip("\n")
    if not raw:
        continue
    log("READ", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if not generating and obj.get("type") == "stream_event":
        etype = (obj.get("event") or {}).get("type")
        if etype in ("message_start", "content_block_start"):
            generating = True
            write_line({"type": "control_request", "request_id": "raw-capture-interrupt-1",
                        "request": {"subtype": "interrupt"}})
    if obj.get("type") == "result":
        turn3_done = True

log("MARK", "turn3 (interrupted) complete")

# --- Turn 4: an ORDINARY turn after the interrupt, to isolate whether the
# exit-code anomaly below is specific to closing IMMEDIATELY after an
# interrupted result, or a broader post-interrupt process state issue. ---
write_line({"type": "user", "message": {"role": "user", "content": "reply with the single word: revived"}})
turn4_done = False
deadline = time.monotonic() + 40
while time.monotonic() < deadline and not turn4_done:
    raw = proc.stdout.readline()
    if raw == "":
        log("EOF", "stdout closed unexpectedly during turn 4")
        break
    raw = raw.rstrip("\n")
    if not raw:
        continue
    log("READ", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if obj.get("type") == "result":
        turn4_done = True
log("MARK", "turn4 (post-interrupt, ordinary) complete")

# --- end: close stdin, observe clean exit ---
write_line_ts = time.monotonic()
log("WRITE", "<close stdin>")
proc.stdin.close()
try:
    exit_code = proc.wait(timeout=15)
except subprocess.TimeoutExpired:
    exit_code = None
    proc.kill()
log("MARK", f"process exit_code={exit_code}")

time.sleep(1.5)  # let stderr drain thread catch up
log("STDERR_TAIL", repr(stderr_lines))

out_path = "EV-CC-003-stream-json-raw_capture.log"
with open(out_path, "w") as f:
    f.write("\n".join(log_lines) + "\n")
print(f"\nFull log written to {out_path}")
