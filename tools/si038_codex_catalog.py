"""Read the campaign engine's account presence and model catalog without opening a thread."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ENGINE_SHA256 = "ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f"
MODEL_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}")


class CatalogError(RuntimeError):
    """A bounded observation did not produce a usable catalog."""


async def observe(command, workspace, env):
    startup = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    child = await asyncio.create_subprocess_exec(
        *command, cwd=workspace, env=env, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=1024 * 1024, **startup,
    )
    request_id = 0

    async def request(method, params, *, notification=False):
        nonlocal request_id
        message = {"method": method, "params": params}
        if not notification:
            request_id += 1
            message["id"] = request_id
        child.stdin.write(json.dumps(message).encode() + b"\n")
        await child.stdin.drain()
        if notification:
            return None
        for _ in range(64):
            line = await child.stdout.readline()
            if not line:
                break
            response = json.loads(line)
            if not isinstance(response, dict):
                break
            if "method" in response:
                if "id" in response:
                    raise CatalogError("The engine requested an action during catalog discovery.")
                continue
            if type(response.get("id")) is int and response["id"] == request_id:
                if "error" not in response and isinstance(response.get("result"), dict):
                    return response["result"]
                break
        raise CatalogError(f"The engine did not confirm {method}.")

    async def read_models():
        models, defaults, seen_cursors = [], [], set()
        params = {"limit": 50, "includeHidden": False}
        for _ in range(5):
            page = await request("model/list", params)
            rows = page.get("data")
            if not isinstance(rows, list) or len(rows) > params["limit"] or "nextCursor" not in page:
                break
            for row in rows:
                name = row.get("model") if isinstance(row, dict) else None
                if (not isinstance(name, str) or MODEL_ID.fullmatch(name) is None or
                        name in models or type(row.get("isDefault")) is not bool):
                    raise CatalogError("Malformed model catalog.")
                models.append(name)
                if row["isDefault"]:
                    defaults.append(name)
            cursor = page["nextCursor"]
            if cursor is None and models:
                return models, defaults
            if not isinstance(cursor, str) or not 1 <= len(cursor) <= 4096 or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            params["cursor"] = cursor
        raise CatalogError("The engine did not provide a complete model catalog.")

    try:
        async with asyncio.timeout(20):
            await request("initialize", {"clientInfo": {"name": "nexus-campaign-catalog", "version": "1"}})
            await request("initialized", {}, notification=True)
            result = await request("account/read", {"refreshToken": False})
            if type(result.get("requiresOpenaiAuth")) is not bool or "account" not in result:
                raise CatalogError("Malformed account observation.")
            account = result["account"]
            if account is not None and (not isinstance(account, dict) or
                                        account.get("type") not in ("apiKey", "chatgpt", "amazonBedrock")):
                raise CatalogError("Malformed account observation.")
            models, defaults = await read_models()
            report = {"provider_session_present": account is not None, "models": models, "defaults": defaults}
        child.stdin.close()
        await asyncio.wait_for(child.wait(), 5)
        if child.returncode != 0:
            raise CatalogError("The engine exited unsuccessfully.")
        return report
    finally:
        if child.returncode is None:
            try:
                child.kill()
            except ProcessLookupError:
                pass
            await asyncio.wait_for(child.communicate(), 5)


def isolated_catalog(engine, auth_snapshot):
    with engine.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ENGINE_SHA256:
            raise CatalogError("The executable differs from the reviewed campaign engine.")
    with TemporaryDirectory(prefix="nexus-si038-catalog-") as directory, socket.socket() as closed:
        if os.name == "nt":
            closed.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        closed.bind(("127.0.0.1", 0))
        rejected = f"http://127.0.0.1:{closed.getsockname()[1]}"
        root = Path(directory)
        profile, work = root / "profile", root / "work"
        for path in (profile, work, root / "appdata", root / "localappdata", root / "tmp"):
            path.mkdir()
        env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ}
        env.update(CODEX_HOME=str(profile), USERPROFILE=str(root), HOME=str(root),
                   APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"),
                   TMP=str(root / "tmp"), TEMP=str(root / "tmp"), TMPDIR=str(root / "tmp"), PATH="",
                   CODEX_REFRESH_TOKEN_URL_OVERRIDE=rejected, CODEX_REVOKE_TOKEN_URL_OVERRIDE=rejected)
        (profile / "config.toml").write_text(
            'cli_auth_credentials_store = "file"\ncheck_for_update_on_startup = false\n'
            '[analytics]\nenabled = false\n', encoding="utf-8",
        )
        if auth_snapshot is None:
            env.update(HTTP_PROXY=rejected, HTTPS_PROXY=rejected, ALL_PROXY=rejected)
        else:
            shutil.copyfile(auth_snapshot, profile / "auth.json")
        return asyncio.run(observe([str(engine.resolve()), "app-server"], work, env))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path, help="The reviewed Codex 0.157.0 executable")
    parser.add_argument("--auth-snapshot", type=Path, help="An authorized Codex file-auth snapshot")
    args = parser.parse_args()
    try:
        report = isolated_catalog(args.engine, args.auth_snapshot)
    except CatalogError as error:
        parser.exit(1, f"{error}\n")
    except (OSError, ValueError, TimeoutError):
        parser.exit(1, "Catalog observation failed.\n")
    print(json.dumps({"engine_sha256": ENGINE_SHA256, **report}, indent=2))


if __name__ == "__main__":
    main()
