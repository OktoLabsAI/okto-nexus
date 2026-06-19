"""Outbound tokenizer adapters (spec: workspace visibility + analytics).

The CONCRETE side of the :class:`okto_nexus.application.ports.Tokenizer` port.
Token counting is the analytics view's notion of message "size" (TOKENS, not
bytes - owner decision 2026-06-19). tiktoken is an EXTERNAL, heavy dependency,
so - exactly like the embedding stack - it lives HERE (an outbound adapter)
behind a lazy import and ships only under the ``serve`` extra:

* :class:`ApproxTokenizer` - zero-dependency, deterministic heuristic. Always
  importable; the fallback when tiktoken is absent (e.g. the stdio core, which
  never registers the analytics route anyway). Approximate, never exact.
* :class:`TiktokenTokenizer` - tiktoken ``o200k_base`` (the GPT-4o family),
  loaded FULLY OFFLINE from a vendored BPE blob (no network). The exact counter
  the analytics route uses on the serve build.

:func:`resolve_tokenizer` is the composition-root factory: it returns the real
tiktoken tokenizer when the dependency imports, else degrades to the heuristic
(``exact=False``). The heavy import (``tiktoken``) is performed LAZILY inside
:meth:`TiktokenTokenizer._ensure_encoding`, so importing THIS module never
pulls tiktoken in - preserving the stdio "dependency-light" invariant
(AC9 / rule br_7000ed45): ``import okto_nexus`` core path stays tiktoken-free.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from ....application.ports import Tokenizer

#: tiktoken encoding id: ``o200k_base`` is the GPT-4o family encoding - the best
#: current estimate of how a modern LLM tokenises coordination text (decision
#: D9). ``cl100k_base`` (GPT-4/3.5) is the historical alternative.
O200K_BASE = "o200k_base"

#: The official public URL tiktoken derives the ``o200k_base`` blob from. We do
#: NOT fetch it at runtime; the constant exists only to derive the cache-key
#: filename below, so the vendored blob is named exactly what tiktoken expects.
_O200K_BASE_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)

#: Directory holding the vendored BPE blob (shipped as package-data). Pointing
#: ``TIKTOKEN_CACHE_DIR`` here makes ``get_encoding`` resolve from disk with
#: ZERO network access.
_ENCODINGS_DIR = Path(__file__).resolve().parent / "_encodings"

#: tiktoken's on-disk cache key is the SHA1 hex digest of the blob URL; the
#: vendored file MUST be named exactly this for the offline lookup to hit.
_CACHE_KEY = hashlib.sha1(_O200K_BASE_URL.encode()).hexdigest()

#: Upper bound on the per-``message_id`` token cache (process-lifetime). Bounded
#: so a long-running serve never grows it without limit; eviction is FIFO
#: (oldest inserted first) - messages are immutable so any entry is as good as
#: any other to drop (TR5 / TOKEN_CACHE_MAX).
TOKEN_CACHE_MAX = 100_000

#: Heuristic divisor for the dependency-free fallback (~4 chars/token is the
#: common rule of thumb for English-ish text). Only used when tiktoken is absent.
_APPROX_CHARS_PER_TOKEN = 4

#: Word/punctuation splitter for the heuristic's lower bound.
_APPROX_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class _TokenCache:
    """Bounded, thread-safe ``message_id -> token count`` memo (FIFO eviction)."""

    def __init__(self, maxsize: int = TOKEN_CACHE_MAX) -> None:
        self._maxsize = int(maxsize)
        self._data: "OrderedDict[str, int]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, message_id: str) -> int | None:
        with self._lock:
            return self._data.get(message_id)

    def put(self, message_id: str, count: int) -> None:
        with self._lock:
            if message_id in self._data:
                return
            self._data[message_id] = count
            if len(self._data) > self._maxsize:
                # FIFO: drop the oldest inserted entry.
                self._data.popitem(last=False)


class ApproxTokenizer:
    """Dependency-free, deterministic token-count heuristic (never exact).

    The fallback used only when tiktoken is unavailable. It is NOT used by the
    analytics route on a real serve build (that always resolves the tiktoken
    tokenizer); it exists so the port is always satisfiable and the application
    layer never has to special-case "no tokenizer". The count is the max of a
    char-based estimate and a word/punctuation token count - a stable, ordering-
    preserving stand-in, explicitly approximate.
    """

    encoding = "approx-chars-v1"

    def __init__(self, maxsize: int = TOKEN_CACHE_MAX) -> None:
        self._cache = _TokenCache(maxsize)

    def count(self, text: str | None) -> int:
        if not text:
            return 0
        char_estimate = (len(text) + _APPROX_CHARS_PER_TOKEN - 1) // _APPROX_CHARS_PER_TOKEN
        word_estimate = len(_APPROX_TOKEN_RE.findall(text))
        return max(char_estimate, word_estimate)

    def count_for_message(self, message_id: str, body: str | None) -> int:
        cached = self._cache.get(message_id)
        if cached is not None:
            return cached
        value = self.count(body)
        self._cache.put(message_id, value)
        return value


class TiktokenTokenizer:
    """Exact token count via tiktoken ``o200k_base``, loaded OFFLINE.

    The encoding (and tiktoken itself) is imported LAZILY on the first
    :meth:`count`, never at construction - so wiring this tokenizer is cheap and
    importing this module never requires the extra. Before loading,
    ``TIKTOKEN_CACHE_DIR`` is pointed at the vendored blob directory so
    ``get_encoding`` resolves from disk with no network access (D9 / AC6).
    Per-message counts are memoised by ``message_id`` (messages are immutable).
    """

    encoding = O200K_BASE

    def __init__(self, maxsize: int = TOKEN_CACHE_MAX) -> None:
        self._enc = None  # lazy singleton
        self._lock = threading.Lock()
        self._cache = _TokenCache(maxsize)

    def _ensure_encoding(self):
        # Double-checked locking: serve worker threads can race the first count.
        if self._enc is None:
            with self._lock:
                if self._enc is None:
                    # Point tiktoken at the vendored blob BEFORE importing it, so
                    # the encoding loads from disk (offline). We only SET the var
                    # when the vendored blob is actually present, to avoid
                    # masking a working ambient cache in unusual deployments.
                    if (_ENCODINGS_DIR / _CACHE_KEY).is_file():
                        os.environ.setdefault(
                            "TIKTOKEN_CACHE_DIR", str(_ENCODINGS_DIR)
                        )
                    import tiktoken  # lazy: serve extra only

                    self._enc = tiktoken.get_encoding(O200K_BASE)
        return self._enc

    def count(self, text: str | None) -> int:
        if not text:
            return 0
        enc = self._ensure_encoding()
        # disallowed_special=() : never raise on special-token-looking text in a
        # user message body; count every piece as ordinary tokens.
        return len(enc.encode(text, disallowed_special=()))

    def count_for_message(self, message_id: str, body: str | None) -> int:
        cached = self._cache.get(message_id)
        if cached is not None:
            return cached
        value = self.count(body)
        self._cache.put(message_id, value)
        return value


@dataclass(frozen=True)
class TokenizerResolution:
    """The wired tokenizer capability for the current build.

    ``exact`` is True only when the real tiktoken tokenizer loaded; when the
    dependency is absent the resolution degrades to :class:`ApproxTokenizer`
    (``exact=False``, ``degraded=True``) so the analytics still renders a
    consistent, if approximate, "size" axis on a tiktoken-less host.
    """

    tokenizer: Tokenizer
    exact: bool
    degraded: bool


def resolve_tokenizer(maxsize: int = TOKEN_CACHE_MAX) -> TokenizerResolution:
    """Return the best available tokenizer, preferring exact tiktoken.

    Probes ``tiktoken`` (without loading the heavy encoding): present -> the
    exact ``o200k_base`` tokenizer; absent -> the dependency-free heuristic
    (``exact=False``, ``degraded=True``). Never raises - the analytics view must
    always have SOME size metric.
    """
    try:
        import tiktoken  # noqa: F401 - availability probe only
    except ImportError:
        return TokenizerResolution(
            tokenizer=ApproxTokenizer(maxsize), exact=False, degraded=True
        )
    return TokenizerResolution(
        tokenizer=TiktokenTokenizer(maxsize), exact=True, degraded=False
    )
