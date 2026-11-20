"""Observe stock RPC and SDK literal handling with the pinned Pi build."""

import asyncio
import json
import os
import sys
from hashlib import sha256
from pathlib import Path

from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.pi_extension_resource import reviewed_pi_renderer_build

EXPECTED_BUILD = (
    "sha256:caf8bfad84ea26a7c8eaee06e0cde3dd7e34ef05e00dbebc348dfb3f22de487b"
)
SKILL = "/skill:literal-fixture apply this once"
TEMPLATE = "/literal-template café  "
COMMAND = "/literal-command a synthetic argument"
INPUTS = (SKILL, TEMPLATE, COMMAND)


def prepare(root, release, intercept):
    root.mkdir()
    project = root / "project"
    project.mkdir()
    (project / ".agents" / "skills").mkdir(parents=True)
    (project / ".git").mkdir()
    (project / ".git" / "HEAD").write_text(
        "ref: refs/heads/fixture\n", encoding="ascii"
    )
    profile = root / "profile"
    agent = profile / ".pi" / "agent"
    (agent / "extensions").mkdir(parents=True)
    skill = agent / "skills" / "literal-fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: literal-fixture\ndescription: A test-only skill\n---\n<SKILL_BODY_FIXTURE>\n",
        encoding="utf-8",
    )
    prompts = agent / "prompts"
    prompts.mkdir()
    (prompts / "literal-template.md").write_text(
        "---\ndescription: A test-only prompt\n---\n<TEMPLATE_BODY_FIXTURE> $ARGUMENTS\n",
        encoding="utf-8",
    )
    output = root / "model-inputs.jsonl"
    action = root / "command-executed"
    peer = release / "node_modules/@earendil-works/pi-ai/dist/providers/faux.js"
    assert peer.is_file()
    inputs = json.dumps(INPUTS, ensure_ascii=False)
    handler = (
        """pi.on('input', async (event) => event.source === 'extension' && event.text === inputs[0]
        ? {action:'transform', text:'INPUT_HANDLER_REWROTE_TEXT'} : {action:'continue'});"""
        if intercept
        else ""
    )
    (agent / "extensions/fixture.js").write_text(
        f"""
import {{ fauxProvider, fauxAssistantMessage }} from {json.dumps(peer.as_uri())};
import {{ appendFileSync, writeFileSync }} from 'node:fs';
const inputs = {inputs};
export default (pi) => {{
  const faux = fauxProvider({{provider:'nexus-fixture', api:'nexus-fixture'}});
  pi.registerProvider(faux.provider);
  faux.setResponses(Array.from({{length:5}}, () => (context) => {{
    const last = context.messages.findLast(message => message.role === 'user');
    appendFileSync({json.dumps(str(output))}, JSON.stringify(last?.content) + '\\n');
    return fauxAssistantMessage('Synthetic answer');
  }}));
  pi.registerCommand('literal-command', {{description:'Fixture command', handler:async () => {{
    writeFileSync({json.dumps(str(action))}, 'executed');
  }}}});
  pi.registerCommand('submit-literal-fixture', {{description:'Fixture SDK entry', handler:async (arg) => {{
    const input = inputs[Number(arg.trim())];
    if (typeof input !== 'string') throw new Error('Unknown fixture input');
    pi.sendUserMessage(input, {{expandPromptTemplates:false}});
  }}}});
  {handler}
}};
""",
        encoding="utf-8",
    )
    preload = root / "isolation.mjs"
    preload.write_text(
        """
import net from 'node:net';
const denied = () => { throw new Error('No network in the disposable Pi fixture'); };
net.Socket.prototype.connect = denied;
globalThis.fetch = denied;
""",
        encoding="utf-8",
    )
    scratch = root / "tmp"
    scratch.mkdir()
    base = {
        name: os.environ[name]
        for name in ("SystemRoot", "ComSpec", "WINDIR")
        if name in os.environ
    }
    environment = base | {
        "HOME": str(profile),
        "USERPROFILE": str(profile),
        "PI_CODING_AGENT_DIR": str(agent),
        "TEMP": str(scratch),
        "TMP": str(scratch),
        "APPDATA": str(scratch),
        "LOCALAPPDATA": str(scratch),
        "PATH": str(scratch),
        "PI_OFFLINE": "1",
    }
    options = [
        "--permission",
        f"--allow-fs-read={release}",
        f"--allow-fs-read={root}",
        f"--allow-fs-write={root}",
        f"--import={preload.as_uri()}",
    ]
    return project, environment, options, output, action


async def run_variant(root, node, cli, release, intercept):
    project, environment, options, output, action = prepare(root, release, intercept)
    with (root / "stderr.log").open("wb") as errors:
        process = await asyncio.create_subprocess_exec(
            str(node),
            *options,
            str(cli),
            "--mode",
            "rpc",
            "--no-context-files",
            "--no-approve",
            "--provider",
            "nexus-fixture",
            "--model",
            "faux-1",
            "--api-key",
            "synthetic-fixture-token",
            cwd=project,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=errors,
        )

        async def command(identifier, kind, *, wait_turn=False, **parameters):
            sent = {"id": identifier, "type": kind} | parameters
            process.stdin.write((json.dumps(sent, ensure_ascii=False) + "\n").encode())
            await process.stdin.drain()
            reply = None
            settled = not wait_turn
            async with asyncio.timeout(25):
                while reply is None or not settled:
                    raw = await process.stdout.readline()
                    assert raw, f"{identifier}: Pi stdout closed before receipt"
                    item = json.loads(raw)
                    if item.get("type") == "response" and item.get("id") == identifier:
                        assert item.get("success"), (identifier, item.get("error"))
                        reply = item
                    elif item.get("type") == "agent_settled":
                        settled = True
            return reply

        def texts():
            values = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
            assert all(
                len(value) == 1 and value[0]["type"] == "text" for value in values
            )
            return [value[0]["text"] for value in values]

        try:
            before = await command("before", "get_state")
            if not intercept:
                await command(
                    "stock-skill",
                    "prompt",
                    message=SKILL,
                    expandPromptTemplates=False,
                    wait_turn=True,
                )
                await command(
                    "stock-template",
                    "prompt",
                    message=TEMPLATE,
                    expandPromptTemplates=False,
                    wait_turn=True,
                )
                await command(
                    "stock-command",
                    "prompt",
                    message=COMMAND,
                    expandPromptTemplates=False,
                )
                assert action.read_text() == "executed"
                action.rename(root / "stock-command-executed")
                assert len(texts()) == 2
                assert (
                    "<SKILL_BODY_FIXTURE>" in texts()[0]
                    and "<TEMPLATE_BODY_FIXTURE>" in texts()[1]
                )
            for index in range(1) if intercept else range(len(INPUTS)):
                await command(
                    f"literal-{index}",
                    "prompt",
                    message=f"/submit-literal-fixture {index}",
                    wait_turn=True,
                )
            after = await command("after", "get_state")
            assert before["data"]["sessionId"] == after["data"]["sessionId"]
            assert not action.exists()
            if intercept:
                assert texts() == ["INPUT_HANDLER_REWROTE_TEXT"], texts()
            else:
                assert texts()[2:] == list(INPUTS), texts()
            return {
                "same_session": True,
                "synthetic_model_requests": len(texts()),
                "stock_option_ignored_and_expanded": not intercept,
                "sdk_literal_matches": 0 if intercept else 3,
                "registered_command_not_executed_by_sdk_literal": not intercept,
                "extension_input_can_transform_sdk_literal": intercept,
            }
        finally:
            if process.returncode is None:
                process.stdin.close()
                try:
                    async with asyncio.timeout(8):
                        exit_code = await process.wait()
                        if sys.exc_info()[0] is None:
                            assert exit_code == 0
                except TimeoutError:
                    process.terminate()
                    await process.wait()
                    raise


async def main():
    lab, node, release = map(Path, sys.argv[1:])
    cli = release / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    build = candidate_pi_node_cli(node, cli, explicit=True)
    assert build.version == "0.87.1" and build.build_identity == EXPECTED_BUILD, (
        build.version,
        build.build_identity,
    )
    assert reviewed_pi_renderer_build(
        build.version, sys.platform, build.architecture, build.build_identity
    )
    cases = await asyncio.gather(
        run_variant(lab / "native-expansion", node, cli, release, False),
        run_variant(lab / "interception", node, cli, release, True),
    )
    report = {
        "build": build.version,
        "build_identity": build.build_identity,
        "node_cli_sha256": sha256(cli.read_bytes()).hexdigest(),
        "windows_reviewed_build": True,
        "probe": cases,
        "external_provider_requests": 0,
        "paid_tokens": 0,
    }
    (lab / "proof.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
