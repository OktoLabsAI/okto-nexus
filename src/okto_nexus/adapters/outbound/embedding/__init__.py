"""Outbound embedding-provider adapters (spec: Frente 3 - embeddings).

The CONCRETE side of the :class:`EmbeddingProvider` port. The embedding model
is an EXTERNAL service to the domain, so every import that pulls in a heavy ML
stack lives HERE (an outbound adapter), never in ``domain``/``application``:

* :class:`StubEmbeddingProvider` - zero-dependency, deterministic (SHA256 ->
  384 floats). Always importable; used in CI and whenever the optional extra is
  absent or ``embedding_mode=stub``.
* :class:`SentenceTransformerProvider` - ``all-MiniLM-L6-v2`` (384 dims) loaded
  lazily as a process singleton, under the ``okto-nexus[embeddings]`` extra.

:func:`resolve_embedding_provider` is the composition-root factory that maps the
``embedding_mode`` knob to a provider plus the two derived flags the wiring
needs (``search_enabled``, ``degraded``). Heavy imports (``sentence_transformers``)
are performed LAZILY so importing this module never requires the extra.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Sequence

from ....application.ports import EmbeddingProvider
from ....config import (
    EMBEDDING_MODE_LOCAL,
    EMBEDDING_MODE_OFF,
    EMBEDDING_MODE_STUB,
    EMBEDDING_MODES,
)
from ....errors import ErrorCode, OktoNexusError

#: Fixed embedding dimensionality across BOTH providers (all-MiniLM-L6-v2 emits
#: 384; the stub matches so vectors are interchangeable shape-wise). The vector
#: store skips any stored row whose ``dim`` differs from the query's, so a model
#: swap never corrupts a ranking (rule br_04f0e599).
EMBEDDING_DIM = 384

#: Sentence-transformers model id for ``embedding_mode=local`` (parity with the
#: Okto Pulse embedding stack; decision D-EMB-2).
LOCAL_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#: Provenance string persisted alongside every stub-generated vector.
STUB_MODEL_NAME = "stub-sha256-v1"

#: 32-byte SHA256 digest -> 8 little-endian uint32 -> 8 floats per round.
_BYTES_PER_FLOAT = 4
_FLOATS_PER_HASH = hashlib.sha256().digest_size // _BYTES_PER_FLOAT
_UINT32_MAX = 0xFFFFFFFF


class StubEmbeddingProvider:
    """Deterministic, dependency-free embedding (SHA256 -> ``dim`` floats).

    The same text ALWAYS maps to the same vector (rule: stub is deterministic),
    so search results are reproducible in tests without a real model. Values are
    spread over ``[-1, 1]``; cosine normalises magnitude, so the raw spread is
    fine for ranking. Not semantic - it is a stand-in that exercises the whole
    generate -> persist -> cosine-rank pipeline end to end at zero cost.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = int(dim)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return STUB_MODEL_NAME

    def encode(self, text: str) -> list[float]:
        vector: list[float] = []
        counter = 0
        material = text if isinstance(text, str) else str(text)
        while len(vector) < self._dim:
            digest = hashlib.sha256(
                f"{counter}\x00{material}".encode("utf-8")
            ).digest()
            for offset in range(0, len(digest), _BYTES_PER_FLOAT):
                if len(vector) >= self._dim:
                    break
                raw = int.from_bytes(
                    digest[offset : offset + _BYTES_PER_FLOAT], "big"
                )
                vector.append((raw / _UINT32_MAX) * 2.0 - 1.0)
            counter += 1
        return vector

    def encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.encode(text) for text in texts]


class SentenceTransformerProvider:
    """``all-MiniLM-L6-v2`` embedding, lazily loaded as a process singleton.

    The model (and its torch dependency) is imported and instantiated only on
    the FIRST :meth:`encode`/:meth:`encode_batch`, never at construction - so
    wiring this provider is cheap and an absent extra surfaces as an
    ``ImportError`` at resolve time (handled by the factory), not on import.
    """

    def __init__(self, model_name: str = LOCAL_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None  # lazy singleton
        self._lock = threading.Lock()  # one load even under concurrent threads

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM

    @property
    def model(self) -> str:
        return self._model_name

    def _ensure_model(self):
        # Double-checked locking: the serve warm-up thread and request threads
        # (generation/search run in anyio worker threads) can race the first
        # encode; without the lock that builds the heavy model twice.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import (  # lazy: extra
                        SentenceTransformer,
                    )

                    self._model = SentenceTransformer(self._model_name)
        return self._model

    def encode(self, text: str) -> list[float]:
        model = self._ensure_model()
        # show_progress_bar=False: a server must never paint a tqdm bar to the
        # console on every encode (generation/search/warm-up).
        vector = model.encode([text], show_progress_bar=False)[0]
        return [float(component) for component in vector]

    def encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._ensure_model()
        rows = model.encode(list(texts), show_progress_bar=False)
        return [[float(component) for component in row] for row in rows]


@dataclass(frozen=True)
class EmbeddingResolution:
    """The wired embedding capability for one ``embedding_mode`` value.

    ``provider`` is ``None`` only when generation is disabled (``mode=off``).
    ``search_enabled`` gates /messages/search (False -> the route answers
    EMBEDDINGS_UNAVAILABLE). ``degraded`` is True when ``local`` was requested
    but the extra is missing, so generation silently fell back to the stub while
    search stays disabled (the operator wanted a real model that is absent).
    """

    mode: str
    provider: EmbeddingProvider | None
    search_enabled: bool
    degraded: bool


def resolve_embedding_provider(mode: str) -> EmbeddingResolution:
    """Map ``embedding_mode`` to a provider + the derived capability flags.

    ``off`` -> no provider, search disabled. ``stub`` -> stub provider, search
    enabled. ``local`` -> the sentence-transformers provider when the extra
    imports; if it does not, generation degrades to the stub and search is
    disabled (``degraded=True``). An unknown mode raises ``CONFIG_ERROR``
    (defensive: ``load_config`` already validates the enum).
    """
    if mode == EMBEDDING_MODE_OFF:
        return EmbeddingResolution(
            mode=mode, provider=None, search_enabled=False, degraded=False
        )
    if mode == EMBEDDING_MODE_STUB:
        return EmbeddingResolution(
            mode=mode,
            provider=StubEmbeddingProvider(),
            search_enabled=True,
            degraded=False,
        )
    if mode == EMBEDDING_MODE_LOCAL:
        try:
            import sentence_transformers  # noqa: F401 - availability probe
        except ImportError:
            # Extra absent: keep generating (best-effort) with the stub so new
            # messages still get SOME vector, but disable semantic search - the
            # operator configured a real model that is not installed.
            return EmbeddingResolution(
                mode=mode,
                provider=StubEmbeddingProvider(),
                search_enabled=False,
                degraded=True,
            )
        return EmbeddingResolution(
            mode=mode,
            provider=SentenceTransformerProvider(),
            search_enabled=True,
            degraded=False,
        )
    raise OktoNexusError(
        ErrorCode.CONFIG_ERROR,
        f"Unknown embedding_mode {mode!r}; expected one of "
        f"{', '.join(EMBEDDING_MODES)}.",
        {"embedding_mode": mode},
    )
