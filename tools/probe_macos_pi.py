"""Collect installed-Core evidence for the exact Pi build on Intel macOS."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time

from nexus_connector_core.discovery import candidate_pi_node_cli, fingerprint
from nexus_connector_core.native.adapter_types import HarnessCommand
from nexus_connector_core.native.adapters.pi import PiRpcConnector
from nexus_connector_core.native.process import observe_owned_process, snapshot_owned_process_birth
from nexus_connector_core.native.process.recovery import recover_owned_container
from nexus_connector_core.pi_extension_resource import reviewed_pi_renderer_build


SANDBOX = ("/usr/bin/sandbox-exec", "-p", "(version 1) (allow default) (deny network*)")
PROMPT = "Review the fixture shipment"
ANSWER = "The fixture shipment arrived"


def eventually(read):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if value := read():
            return value
        time.sleep(0.05)
    raise AssertionError("Expected Pi event was not observed")


def verify_network_denied(node, env, cwd):
    # The listener makes refusal distinguishable from an unused loopback port.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        probe = """
const socket = require('node:net').connect(Number(process.argv[1]), '127.0.0.1');
socket.on('connect', () => process.exit(2));
socket.on('error', error => process.exit(['EPERM', 'EACCES'].includes(error.code) ? 0 : 3));
"""
        subprocess.run((*SANDBOX, str(node), "-e", probe, str(port)), env=env, cwd=cwd,
                       check=True, timeout=10)


def prepare_fixture(work, release):
    agent = work / "profile/agent"
    extensions = agent / "extensions"
    extensions.mkdir(parents=True)
    project = work / "project"
    project.mkdir()
    entered, signal = work / "provider-entered", work / "release-response"
    faux = release / "node_modules/@earendil-works/pi-ai/dist/providers/faux.js"
    source = f"""
import {{ fauxProvider, fauxAssistantMessage }} from {json.dumps(faux.as_uri())};
import {{ access, writeFile }} from 'node:fs/promises';
import {{ setTimeout }} from 'node:timers/promises';
export default pi => {{
    const fixture = fauxProvider({{provider: 'nexus-fixture', api: 'nexus-fixture'}});
    pi.registerProvider(fixture.provider);
    fixture.setResponses([async () => {{
        await writeFile({json.dumps(str(entered))}, '');
        for (let i = 0; i < 2400; i++) {{
            try {{
                await access({json.dumps(str(signal))});
                return fauxAssistantMessage({json.dumps(ANSWER)});
            }} catch (error) {{
                if (error.code !== 'ENOENT') throw error;
            }}
            await setTimeout(25);
        }}
        throw new Error('Fixture response was not released');
    }}]);
}};
"""
    (extensions / "fixture.js").write_text(source, encoding="utf-8")
    env = dict(HOME=str(agent.parent), TMPDIR=str(work), PATH="/usr/bin:/bin",
               XDG_CONFIG_HOME=str(agent.parent), PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE="1")
    return project, agent, entered, signal, env


def verify_history(agent):
    history, = agent.rglob("*.jsonl")
    messages = []
    for line in history.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") != "message" or event["message"]["role"] not in {"user", "assistant"}:
            continue
        message = event["message"]
        text = "".join(part["text"] for part in message["content"] if part["type"] == "text")
        messages.append((message["role"], text))
    assert messages == [("user", PROMPT), ("assistant", ANSWER)]


def exercise(node, release, work):
    assert sys.platform == "darwin" and platform.machine() == "x86_64" and os.getuid() != 0
    cli = release / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    candidate = candidate_pi_node_cli(node, cli, explicit=True)
    assert (candidate.version, candidate.architecture) == ("0.87.1", "x86_64")
    project, agent, entered, signal, env = prepare_fixture(work, release)
    verify_network_denied(node, env, project)
    executable = (*SANDBOX, candidate.executable, candidate.launch_script)
    connector = PiRpcConnector(command=(*executable, "--mode", "rpc"), version_command=(*executable, "--version"),
                               cwd=str(project), env=env,
                               extra_args=("--no-context-files", "--provider", "nexus-fixture", "--model", "faux-1",
                                           "--api-key", "isolated-fixture-key"))
    try:
        session = connector.start(owning_agent_id="fixture")
        owner = connector._transport._proc
        assert type(owner).__name__ == "OwnedDarwinPopen"
        birth = snapshot_owned_process_birth(owner)
        assert birth is not None
        connector.send(session, HarnessCommand(session.session_id, "send_turn", {"text": PROMPT},
                                                 operation_id="macos-turn", attempt_id="macos-attempt", owner_epoch=1))
        eventually(entered.is_file)
        reader = connector.events()
        try:
            assert next(reader).session_id == session.session_id
            assert len(connector._subscribers) == 1
        finally:
            reader.close()
        assert not connector._subscribers and owner.poll() is None
        signal.touch()

        def settled():
            with connector._history_lock:
                events = list(connector._event_history)
                return events if any(e.native_event == "agent_settled" for e in events) else None

        events = eventually(settled)
        assert not connector._subscribers
        assert {event.session_id for event in events} == {session.session_id}
        assert sum(event.native_event == "agent_settled" for event in events) == 1
        assert [outcome for event in events if (outcome := connector.delivery_outcome(event)) is not None] == ["success"]
        assert "".join(chunk[0] for event in events if (chunk := connector.delivery_output(event))) == ANSWER
        assert connector._transport._proc is owner and owner.poll() is None
        verify_history(agent)
    finally:
        signal.touch()
        close_result = connector.close()
    stopped = observe_owned_process(owner)
    assert stopped["stop_observed"] and stopped["exit_code"] is not None
    assert recover_owned_container(birth, stop=False, timeout_seconds=2) == "STOPPED"
    return dict(
        macos=platform.mac_ver()[0], architecture=candidate.architecture, python=platform.python_version(),
        core_version=importlib.metadata.version("okto-nexus-connector-core"),
        node_digest=fingerprint(node), pi_version=candidate.version, build_identity=candidate.build_identity,
        hosted_renderer_reviewed=reviewed_pi_renderer_build(candidate.version, sys.platform,
                                                            candidate.architecture, candidate.build_identity),
        network_block_verified=True, process_owner=type(owner).__name__, provider="synthetic",
        reader_detached_before_result=True, same_process_and_session=True, exact_history=True,
        close_result=close_result, stop_evidence="STOPPED",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nexus-pi-macos-") as directory:
        result = exercise(args.node.resolve(strict=True), args.release.resolve(strict=True), Path(directory).resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
