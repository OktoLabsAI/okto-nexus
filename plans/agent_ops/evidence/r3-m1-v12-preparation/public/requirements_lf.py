"""Pure preparation only: render exactly three pinned offline requirements as LF bytes."""
from pathlib import PureWindowsPath
import re

PACKAGES = ("okto_nexus", "okto_nexus_connector", "nexus_connector_core")


def render_requirements(pins: dict) -> bytes:
    if type(pins) is not dict or set(pins) != set(PACKAGES):
        raise ValueError("THREE_PACKAGE_PINS_REQUIRED")
    lines = []
    for name in PACKAGES:
        item = pins[name]
        if type(item) is not dict or set(item) != {"wheel", "sha256"}:
            raise ValueError("PIN_NOT_FINAL")
        wheel, digest = item["wheel"], item["sha256"]
        if type(wheel) is not str or any(c in wheel for c in "\r\n\x00"):
            raise ValueError("PIN_NOT_FINAL")
        path = PureWindowsPath(wheel)
        if not path.is_absolute() or path.suffix != ".whl" or ".." in path.parts:
            raise ValueError("WHEEL_PATH_INVALID")
        if type(digest) is not str or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("PIN_NOT_FINAL")
        lines.append(path.as_uri() + " --hash=sha256:" + digest)
    result = ("\n".join(lines) + "\n").encode("utf-8")
    assert b"\r" not in result and result.count(b"\n") == 3
    return result


def write_new_requirements(path, pins: dict) -> None:
    """Exclusive create; caller must verify wheel bytes before treating this as a pin."""
    data = render_requirements(pins)
    with path.open("xb") as stream:
        stream.write(data)
    if path.read_bytes() != data:
        raise ValueError("REQUIREMENTS_BYTES_CHANGED")
