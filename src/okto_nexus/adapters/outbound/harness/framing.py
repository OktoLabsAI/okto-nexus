"""Bound allocations before decoding native JSONL, including missing newlines."""
from typing import Iterator, TextIO


# A Python Unicode character occupies at most four bytes. TextIOWrapper's
# decoder buffer is bounded independently; no complete unbounded line is read.
MAX_FRAME_CHARS = 262_144
STDERR_CHUNK_CHARS = 4096


class FrameLimitExceeded(ValueError):
    def __init__(self):
        super().__init__(f"frame_limit_exceeded: maximum {MAX_FRAME_CHARS} characters")


def protocol_lines(stream: TextIO) -> Iterator[str]:
    while True:
        line = stream.readline(MAX_FRAME_CHARS + 1)
        if not line:
            return
        if len(line.rstrip("\n")) > MAX_FRAME_CHARS:
            # Do not retain the rejected content in a diagnostic or resume
            # parsing halfway through it. The caller must close the transport.
            raise FrameLimitExceeded()
        yield line


def stderr_chunks(stream: TextIO) -> Iterator[str]:
    # stderr is prose, not framed protocol: retain a bounded tail of chunks,
    # including long lines, while continuing to drain the pipe.
    while True:
        chunk = stream.readline(STDERR_CHUNK_CHARS)
        if not chunk:
            return
        yield chunk
