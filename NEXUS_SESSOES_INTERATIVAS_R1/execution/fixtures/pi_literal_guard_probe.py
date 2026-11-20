"""Exercise a fixture-only literal-input guard through the reviewed Pi host."""

import asyncio
import json
import sys
from pathlib import Path

from nexus_connector_core.pi_extension_resource import pi_hosted_rpc_path
from pi_literal_probe import INPUTS, SKILL, prepare


async def verify(root, node, release, intercept):
    project, env, options, output, action = prepare(root, release, intercept)
    host = pi_hosted_rpc_path()
    cli = release / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    launcher = root / "host-observer.mjs"
    launcher.write_text(
        f"""
import {{runHostedPiRpc}} from {json.dumps(host.as_uri())};
const [,,cli,...args] = process.argv;
await runHostedPiRpc(cli, args, async (owner) => {{
  const session = owner.session;
  const prompt = session.prompt.bind(session);
  session.prompt = async (value, settings) => {{
    if (typeof value === 'string') return prompt(value, settings);
    if (!value || settings?.source !== 'rpc' || value.kind !== 'literal_fixture' ||
        Object.keys(value).length !== 2 || typeof value.text !== 'string' || !value.text) {{
      throw new Error('Literal request malformed');
    }}
    if (session._extensionRunner.hasHandlers('input') || session.isStreaming) {{
      throw new Error('Literal input unavailable');
    }}
    return prompt(value.text, {{...settings, expandPromptTemplates:false}});
  }};
}});
""",
        encoding="utf-8",
    )
    options.insert(-1, f"--allow-fs-read={host.parent}")
    with (root / "stderr.log").open("wb") as errors:
        proc = await asyncio.create_subprocess_exec(
            str(node),
            *options,
            str(launcher),
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
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=errors,
        )

        async def ask(key, kind, *, value=None, accepted=True, turn=False):
            request = {"id": key, "type": kind}
            if value is not None:
                request["message"] = value
            proc.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode())
            await proc.stdin.drain()
            response = None
            completed = not turn
            async with asyncio.timeout(25):
                while response is None or not completed:
                    raw = await proc.stdout.readline()
                    assert raw, "Pi host exited before the requested state"
                    item = json.loads(raw)
                    if item.get("type") == "response" and item.get("id") == key:
                        assert item["success"] is accepted, item
                        response = item
                    if item.get("type") == "agent_settled":
                        completed = True
            return response

        try:
            start = await ask("start", "get_state")
            rejected = await ask(
                "malformed",
                "prompt",
                value={"kind": "literal_fixture", "text": []},
                accepted=False,
            )
            assert (
                rejected["error"] == "Literal request malformed" and not output.exists()
            )
            if intercept:
                denied = await ask(
                    "guard",
                    "prompt",
                    value={"kind": "literal_fixture", "text": SKILL},
                    accepted=False,
                )
                assert (
                    denied["error"] == "Literal input unavailable"
                    and not output.exists()
                )
            else:
                for index, text in enumerate(INPUTS):
                    await ask(
                        f"input-{index}",
                        "prompt",
                        value={"kind": "literal_fixture", "text": text},
                        turn=True,
                    )
                before = [
                    json.loads(line)[0]["text"]
                    for line in output.read_text(encoding="utf-8").splitlines()
                ]
                assert before == list(INPUTS), before
                assert not action.exists()
            await ask(
                "ordinary", "prompt", value="Regular prompt still works.", turn=True
            )
            end = await ask("end", "get_state")
            assert start["data"]["sessionId"] == end["data"]["sessionId"]
            assert not action.exists()
            observed = [
                json.loads(line)[0]["text"]
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
            assert observed == (
                ["Regular prompt still works."]
                if intercept
                else [*INPUTS, "Regular prompt still works."]
            )
            return {
                "input_extensions_present": intercept,
                "ordinary_prompt_unchanged": True,
                "exact_literal_count": 0 if intercept else 3,
                "malformed_refused_before_turn": True,
                "guard_refused_before_turn": intercept,
                "same_session": True,
            }
        finally:
            if proc.returncode is None:
                proc.stdin.close()
                try:
                    async with asyncio.timeout(8):
                        code = await proc.wait()
                        if sys.exc_info()[0] is None:
                            assert code == 0
                except TimeoutError:
                    proc.terminate()
                    await proc.wait()
                    raise


async def main():
    root, node, release = map(Path, sys.argv[1:])
    reports = await asyncio.gather(
        *(
            verify(root / name, node, release, flag)
            for name, flag in [
                ("exact-reviewed-owner", False),
                ("extensions-present", True),
            ]
        )
    )
    report = {
        "guarded_host_fixture": True,
        "cases": reports,
        "provider_requests": 0,
        "paid_tokens": 0,
    }
    (root / "guard.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
