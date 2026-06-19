"""Tokenizer adapter (workspace-analytics "size" = TOKENS): exact tiktoken
o200k_base counting, OFFLINE loading from the vendored blob, per-message cache,
and the dependency-free approximate fallback.

Scenario coverage (spec bf6e06dc):
* S6/AC5 - token count equals tiktoken o200k_base over ASCII / long / emoji corpora
* S7/AC6 - tokenisation loads 100% offline (vendored blob named by the SHA1(url)
  cache key); a fresh process with the network blocked still counts correctly
* BR1 - NULL/empty body counts 0 tokens
* TR5 - per-message_id memoisation (immutable messages never re-tokenised)
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from okto_nexus.adapters.outbound.tokenizer import (
    O200K_BASE,
    TOKEN_CACHE_MAX,
    ApproxTokenizer,
    TiktokenTokenizer,
    TokenizerResolution,
    _CACHE_KEY,
    _ENCODINGS_DIR,
    _O200K_BASE_URL,
    resolve_tokenizer,
)

tiktoken = pytest.importorskip("tiktoken")

# Three deliberately different corpora: pure ASCII, a long repetitive blob, and
# unicode + emoji (where a char/byte count diverges hardest from token count).
CORPORA = {
    "ascii": "the quick brown fox jumps over the lazy dog. " * 3,
    "long": "coordination handoff retry parked dead-letter inbox backlog " * 40,
    "emoji": "café ☕ — orquestração 🌍 valid<>clean 🤖 tokens≈peso 你好世界",
}


# --------------------------------------------------------------------------- #
# S6 / AC5 - exact equality with tiktoken o200k_base
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", list(CORPORA))
def test_count_matches_tiktoken_direct(name):
    body = CORPORA[name]
    enc = tiktoken.get_encoding(O200K_BASE)
    expected = len(enc.encode(body, disallowed_special=()))
    assert TiktokenTokenizer().count(body) == expected
    # Sanity: tokens are NOT just bytes or chars (the whole point of the metric).
    assert expected != len(body)


def test_encoding_is_o200k_base():
    assert TiktokenTokenizer().encoding == "o200k_base"
    assert O200K_BASE == "o200k_base"


# --------------------------------------------------------------------------- #
# BR1 - empty / None body counts 0 tokens
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tok", [TiktokenTokenizer(), ApproxTokenizer()])
@pytest.mark.parametrize("empty", [None, ""])
def test_empty_body_is_zero_tokens(tok, empty):
    assert tok.count(empty) == 0
    assert tok.count_for_message("m-empty", empty) == 0


# --------------------------------------------------------------------------- #
# TR5 - per-message_id memoisation (immutable messages)
# --------------------------------------------------------------------------- #
def test_count_for_message_is_memoised_by_id():
    tok = TiktokenTokenizer()
    first = tok.count_for_message("m1", "hello world from an agent")
    # Same id, DIFFERENT body -> the cached count for m1 is returned, proving the
    # body is not re-tokenised (messages are immutable, so id is the key).
    again = tok.count_for_message("m1", "a completely different and longer body here")
    assert again == first
    # A new id tokenises afresh.
    other = tok.count_for_message("m2", "a completely different and longer body here")
    assert other != first


def test_cache_default_is_bounded():
    assert TOKEN_CACHE_MAX == 100_000


def test_cache_evicts_oldest_when_full():
    # A tiny cache proves the FIFO eviction branch: after inserting 3 ids into a
    # size-2 cache, the oldest (m0) is dropped while the two newest survive.
    from okto_nexus.adapters.outbound.tokenizer import _TokenCache

    cache = _TokenCache(maxsize=2)
    cache.put("m0", 10)
    cache.put("m1", 20)
    cache.put("m2", 30)  # overflow -> evicts m0
    assert cache.get("m0") is None
    assert cache.get("m1") == 20
    assert cache.get("m2") == 30


# --------------------------------------------------------------------------- #
# Approx fallback - dependency-free, deterministic, never negative
# --------------------------------------------------------------------------- #
def test_approx_tokenizer_is_deterministic_and_positive():
    tok = ApproxTokenizer()
    a = tok.count(CORPORA["emoji"])
    b = tok.count(CORPORA["emoji"])
    assert a == b > 0
    assert tok.encoding == "approx-chars-v1"


def test_resolve_prefers_exact_when_tiktoken_present():
    res = resolve_tokenizer()
    assert isinstance(res, TokenizerResolution)
    assert res.exact is True
    assert res.degraded is False
    assert res.tokenizer.encoding == "o200k_base"


# --------------------------------------------------------------------------- #
# S7 / AC6 - the vendored blob + a genuine OFFLINE load (network blocked)
# --------------------------------------------------------------------------- #
def test_vendored_blob_present_and_named_by_cache_key():
    # tiktoken's on-disk cache filename is sha1(url); the vendored blob MUST be
    # named exactly that for the offline lookup to hit.
    import hashlib

    assert _CACHE_KEY == hashlib.sha1(_O200K_BASE_URL.encode()).hexdigest()
    blob = _ENCODINGS_DIR / _CACHE_KEY
    assert blob.is_file(), f"vendored o200k_base blob missing at {blob}"
    assert blob.stat().st_size > 1_000_000  # the real ranks file is ~3.6 MB


def test_tokenisation_works_offline_in_fresh_process():
    """A fresh interpreter with ALL sockets blocked still counts correctly.

    Proves the adapter loads o200k_base from the vendored blob with zero
    network access: if the blob were missing/misnamed, tiktoken would try to
    download it and the blocked socket would raise.
    """
    enc = tiktoken.get_encoding(O200K_BASE)
    sample = "offline token counting must not touch the network 🌐"
    expected = len(enc.encode(sample, disallowed_special=()))

    script = textwrap.dedent(
        f"""
        # Import the network stack FIRST (ssl subclasses socket, so patching
        # socket.socket itself would break the import), then hard-block every
        # outbound connection: DNS resolution, raw connects and urllib all raise.
        import socket
        import urllib.request
        def _no_net(*a, **k):
            raise OSError("network disabled for offline test")
        socket.getaddrinfo = _no_net      # type: ignore[assignment]
        socket.create_connection = _no_net  # type: ignore[assignment]
        urllib.request.urlopen = _no_net  # type: ignore[assignment]

        from okto_nexus.adapters.outbound.tokenizer import TiktokenTokenizer
        tok = TiktokenTokenizer()
        print(tok.count({sample!r}))
        """
    )
    # The child must be able to import okto_nexus; point PYTHONPATH at the src
    # root (the parent of the installed/checked-out package directory).
    import okto_nexus

    src_root = os.path.dirname(os.path.dirname(os.path.abspath(okto_nexus.__file__)))
    child_env = {**os.environ, "PYTHONPATH": src_root}
    # Don't let an ambient TIKTOKEN_CACHE_DIR pre-seed the child; the adapter
    # must point itself at the vendored blob.
    child_env.pop("TIKTOKEN_CACHE_DIR", None)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=child_env,
    )
    assert proc.returncode == 0, f"offline load failed:\n{proc.stderr}"
    assert int(proc.stdout.strip()) == expected
