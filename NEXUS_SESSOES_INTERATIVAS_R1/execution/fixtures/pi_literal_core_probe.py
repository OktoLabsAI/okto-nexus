"""Submit explicit text through the installed Core and its owned Pi RPC process."""

import asyncio
import json
import sys
import time
from pathlib import Path

from nexus_connector_core import (
    CloseOperation,
    CoreError,
    ExecutionContext,
    LaunchIntent,
    OpenOperation,
    OperationKey,
    SessionKey,
    ShutdownPolicy,
    TurnOperation,
    create_runtime,
)
from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.pi_extension_resource import pi_hosted_rpc_path
from pi_literal_probe import EXPECTED_BUILD, INPUTS, prepare

root, node, release = (Path(arg).resolve(strict=True) for arg in sys.argv[1:])


async def exercise(case, candidate, hook):
    project, env, flags, output, action = prepare(case, release, hook == "input")
    if hook == "context":
        extension = Path(env["PI_CODING_AGENT_DIR"]) / "extensions/transform-context.js"
        extension.write_text(
            f"""export default (pi) => {{
  pi.on("context", (event) => ({{
    messages: event.messages.map(message => message.role === "user" ? {{
      ...message, content: message.content.map(item => item.text === {json.dumps(INPUTS[0])} ?
        {{...item, text: "CONTEXT_TRANSFORMED_LITERAL"}} : item),
    }} : message),
  }}));
}};""",
            encoding="utf-8",
        )
    preload = case / "isolation.mjs"
    with preload.open("a", encoding="utf-8") as file:
        file.write(
            "\nprocess.argv.push('--no-context-files','--no-approve','--provider','nexus-fixture',"
            "'--model','faux-1','--api-key','synthetic-fixture-token');\n"
        )
    flags.insert(-1, f"--allow-fs-read={pi_hosted_rpc_path().parent}")
    env["NODE_OPTIONS"] = " ".join(
        f'"{flag}"' if " " in flag else flag for flag in flags
    )
    journal = SQLiteJournal(case / "core.db")

    async def environment(prepared):
        assert Path(prepared.cwd) == project
        return env

    runtime = create_runtime(
        journal=journal,
        environment=environment,
        candidates={"pi_rpc": candidate},
        workspace_roots={"ws": str(project)},
        pi_hosted_rpc=True,
        max_lease_seconds=350,
    )
    context = ExecutionContext(
        "srv",
        "exe",
        "bind",
        "agent",
        "ws",
        1,
        1,
        1,
        time.monotonic() + 300,
        frozenset({"runtime.open", "turn.submit", "turn.interrupt", "runtime.close"}),
    )
    session = "pi-literal"
    key = SessionKey("srv", "exe", session)

    async def terminal(operation):
        async with asyncio.timeout(30):
            while True:
                report = await journal.get_receipt(
                    OperationKey("srv", "exe", operation)
                )
                if report is not None and report.stage in {
                    "SUCCEEDED",
                    "FAILED",
                    "OUTCOME_UNKNOWN",
                }:
                    return report
                await asyncio.sleep(0.05)

    try:
        prepared = await runtime.prepare(LaunchIntent("agent", "ws", "pi_rpc"), context)
        opened = await runtime.open(
            OpenOperation("opening", session, "stream", prepared), context
        )
        assert opened.stage == "SUBMITTED", opened
        before = await runtime.process_birth(key)
        assert (
            before
            and (await runtime.observe_process_birth(key)).state == "MATCHING_LIVE"
        )
        if hook is not None:
            receipt = await runtime.submit(
                TurnOperation("blocked", session, INPUTS[0], literal=True), context
            )
            assert (
                receipt.stage == "FAILED"
                and receipt.error_code == "CAPABILITY_UNSUPPORTED"
            ), receipt
            assert not receipt.retry_safe and not output.exists()
            assert (
                await runtime.submit(
                    TurnOperation("blocked", session, INPUTS[0], literal=True), context
                )
                == receipt
            )
        else:
            for i, text in enumerate(INPUTS):
                effect = f"literal-{i}"
                receipt = await runtime.submit(
                    TurnOperation(effect, session, text, literal=True), context
                )
                assert receipt.stage == "ACCEPTED", receipt
                completed = await terminal(effect)
                assert completed.stage == "SUCCEEDED", completed
                assert (
                    await runtime.submit(
                        TurnOperation(effect, session, text, literal=True), context
                    )
                    == completed
                )
                try:
                    await runtime.submit(TurnOperation(effect, session, text), context)
                except CoreError as exc:
                    assert exc.code == "OPERATION_CONFLICT"
                else:
                    raise AssertionError("Changing literal intent reused its receipt")
        normal = "Ordinary prompt after the literal submissions."
        observed = await runtime.submit(
            TurnOperation("ordinary", session, normal), context
        )
        assert observed.stage == "ACCEPTED"
        assert (await terminal("ordinary")).stage == "SUCCEEDED"
        assert not action.exists()
        texts = [
            json.loads(line)[0]["text"]
            for line in output.read_text(encoding="utf-8").splitlines()
        ]
        assert texts == ([normal] if hook is not None else [*INPUTS, normal]), texts
        assert await runtime.process_birth(key) == before
        closed = await runtime.close(CloseOperation("closing", session), context)
        assert closed.stage == "SUBMITTED", closed
        assert (await runtime.observe_process_birth(key)).state in {
            "NOT_RUNNING",
            "NOT_OBSERVED",
        }
        return {
            "intercepting_hook": hook,
            "literal_requests_observed": len(texts) - 1,
            "guard_refusal": hook is not None,
            "same_process_all_turns": True,
            "canonical_close_and_exit": True,
            "ordinary_prompt": True,
            "repeated_intent_used_receipt": True,
            "external_provider_calls": 0,
        }
    finally:
        await runtime.shutdown(ShutdownPolicy(1, 1))
        journal.close()


async def main():
    cli = release / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    candidate = candidate_pi_node_cli(node, cli, explicit=True)
    assert candidate.build_identity == EXPECTED_BUILD
    reports = []
    for name, hook in [
        ("clear-profile", None),
        ("input-handler", "input"),
        ("context-handler", "context"),
    ]:
        reports.append(await exercise(root / name, candidate, hook))
    (root / "report.json").write_text(
        json.dumps(reports, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
