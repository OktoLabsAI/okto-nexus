"""Connection-scoped known credentials, never a global secret registry.

Native protocol parsing/correlation happens before this boundary. Only safe
diagnostics and normalized output leave it for capture, projection and clients.
"""
from dataclasses import replace
import json
import re

from ....domain.runtime_commands import RuntimeCommandNotSent, RuntimeLaneBusyBeforeWrite
from ....errors import ErrorCode, OktoNexusError
from .event_journal import redact
from .event_buffers import NativeEventOverflow, NativeReplayExpired, NativeSubscriptionLimit
from .framing import FrameLimitExceeded

_TEXT_FIELDS = {"text", "delta", "content", "result", "output", "stdout", "stderr", "raw", "message"}
_SENSITIVE_ENV = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", re.I)


class BackendSecretRedactor:
    version = 2

    def __init__(self, values=()):
        values = {value for value in values if isinstance(value, str) and value}
        if len(values) > 128 or any(len(value) > 16384 for value in values) or sum(map(len, values)) > 65536:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Runtime credential redaction scope exceeds its bounded capacity.", {})
        variants = set(values)
        for value in values:
            variants.update((json.dumps(value, ensure_ascii=False)[1:-1],
                             json.dumps(value, ensure_ascii=True)[1:-1], repr(value)[1:-1]))
        self._pattern = re.compile("|".join(re.escape(value) for value in sorted(variants, key=len, reverse=True))) if variants else None
        self._lookbehind = max(map(len, variants), default=1) - 1

    @classmethod
    def from_environment(cls, profile, environment):
        names = set(profile["secret_refs"]) if profile else set()
        if profile and profile["inherit_ambient"]:
            names.update(name for name in environment if _SENSITIVE_ENV.search(name))
        return cls(environment[name] for name in names if name in environment)

    @property
    def active(self):
        return self._pattern is not None

    def clean(self, value):
        if isinstance(value, dict):
            value = redact(value)
            return {self.clean(key): self.clean(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.clean(item) for item in value]
        if isinstance(value, str):
            value = self._pattern.sub("[REDACTED]", value) if self._pattern else value
            return redact(value)
        return value

    def error(self, error):
        # These local bounded-buffer faults carry no native diagnostic body;
        # their type is part of lifecycle gap/overflow observability.
        if type(error) in {NativeEventOverflow, NativeReplayExpired, FrameLimitExceeded}:
            return type(error)()
        if type(error) is NativeSubscriptionLimit:
            return NativeSubscriptionLimit(self.clean(str(error)))
        # Preserve typed no-write proof; never infer retry safety from wording.
        if type(error) in {RuntimeCommandNotSent, RuntimeLaneBusyBeforeWrite}:
            return type(error)(self.clean(error.message))
        if isinstance(error, OktoNexusError):
            return OktoNexusError(error.code, self.clean(error.message), self.clean(error.details), retryable=error.retryable)
        return OktoNexusError(ErrorCode.INTERNAL_ERROR, self.clean(str(error)),
                             {"exception_type": self.clean(type(error).__name__)})

    def call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise self.error(exc) from None

    def _payload(self, value, *, field=None):
        if isinstance(value, dict):
            return {self.clean(key): self._payload(item, field=key) for key, item in value.items()}
        if isinstance(value, list):
            return [self._payload(item, field=field) for item in value]
        if isinstance(value, str) and field in _TEXT_FIELDS:
            # Otherwise concatenating raw deltas bypasses the bounded stream
            # scrubber. Preserve protocol metadata; safe normalized text is
            # captured in output_text and flushes at the matching terminal.
            return "[NATIVE_TEXT_REDACTED]"
        return self.clean(value)

    def _split(self, text, *, final):
        if final or not self._pattern:
            return self.clean(text), ""
        cut = max(0, len(text) - self._lookbehind)
        for match in self._pattern.finditer(text):
            if match.start() < cut < match.end():
                cut = match.start()
                break
        return self.clean(text[:cut]), text[cut:]

    def events(self, events):
        pending = {}
        try:
            for event in events:
                output = event.output_text
                payload = self.clean(event.payload)
                payload.pop("_nexus_redaction", None)
                if self.active:
                    key = (event.session_id, event.operation_id, event.attempt_id, event.thread_id, event.turn_id)
                    final = event.delivery_phase == "terminal"
                    previous = pending.pop(key, "")
                    if output is not None or previous:
                        text = ("" if event.output_snapshot else previous) + (output or "")
                        output, tail = self._split(text, final=final)
                        if tail:
                            if len(pending) >= 64:
                                raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Runtime redaction stream capacity exceeded.", {})
                            pending[key] = tail
                    payload = self._payload(payload)
                    payload["_nexus_redaction"] = {"version": self.version, "raw_text": "withheld",
                        "pending_output_chars": len(pending.get(key, ""))}
                yield replace(event, payload=payload, output_text=self.clean(output),
                              native_approval=self.clean(event.native_approval))
        except Exception as exc:
            raise self.error(exc) from None
