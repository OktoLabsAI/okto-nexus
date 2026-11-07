"""Small, publish-only client for external observation protocol revision 1.

The caller durably owns source/instance identity, generation, sequence and the
complete report before calling publish. Retrying is an explicit caller decision:
resend that same report after an uncertain result, never invent a new sequence.
This helper does not register, renew, schedule, infer activity or start work.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import ipaddress
import json
import math
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .domain.observation_tokens import is_well_formed_observation_token
from .domain.observations import ObservationReport, parse_report, report_hash
from .errors import OktoNexusError


PUBLISH_PATH = "/v1/observations/activity"
MAX_REPORT_BYTES = 4096
MAX_BATCH_REPORTS = 100
MAX_RESPONSE_BYTES = 128 * 1024
MAX_TIMEOUT_SECONDS = 30
MAX_RETRY_AFTER_SECONDS = 3600
_RECEIPT_KEYS = frozenset({"observed_instance_id", "generation", "sequence", "report_hash",
                           "received_at", "valid_until", "replayed"})
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z")
_REFUSALS = {
    401: ("AUTH_FAILED", "The observation credential was refused."),
    403: ("PERMISSION_DENIED", "Observation publication is not authorized."),
    409: ("CONFLICT", "The observation binding or sequence conflicts, or publication is disabled."),
    413: ("CONTENT_TOO_LARGE", "The observation request exceeds the Server limit."),
    422: ("VALIDATION_ERROR", "The Server refused the observation report."),
    429: ("QUOTA_EXCEEDED", "The observation publication budget is exhausted."),
}


class ObservationClientError(Exception):
    """Sanitized failure; outcome_unknown means publication may have committed.

    retry_after_seconds is advisory, bounded delta-seconds, never an instruction
    to retry automatically. Neither exception text nor args contain remote data.
    """

    def __init__(self, code, message, *, status=None, outcome_unknown=False, retry_after_seconds=None):
        self.code = code
        self.status = status
        self.outcome_unknown = outcome_unknown
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"{code}: {message}")


def normalize_server_origin(value):
    """Validate and normalize an origin without contacting it or using a token."""
    try:
        if (type(value) is not str or not value or "\\" in value or "?" in value or "#" in value
                or any(ord(char) < 33 or ord(char) == 127 for char in value)):
            raise ValueError
        parts = urlsplit(value)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.path not in ("", "/") or parts.netloc.endswith(":")):
            raise ValueError
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = ipaddress.IPv6Address(host).compressed
        elif (len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                        for label in host.rstrip(".").split("."))):
            raise ValueError
        if "%" in host or parts.port == 0:
            raise ValueError
        if parts.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError
        authority = f"[{host}]" if ":" in host else host
        if parts.port and parts.port != (443 if parts.scheme == "https" else 80):
            authority += ":" + str(parts.port)
        return parts.scheme + "://" + authority
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise ObservationClientError("SERVER_ORIGIN_INVALID",
            "Use an HTTPS origin without credentials, path, query or fragment; HTTP is limited to loopback.") from None


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _prepare(payload):
    try:
        if type(payload) is list:
            values, batch = payload, True
        elif type(payload) is dict and "reports" in payload:
            if set(payload) != {"reports"} or type(payload["reports"]) is not list:
                raise ValueError
            values, batch = payload["reports"], True
        elif type(payload) is dict:
            values, batch = [payload], False
        else:
            raise ValueError
        if not 1 <= len(values) <= MAX_BATCH_REPORTS:
            raise ValueError
        reports = []
        for value in values:
            if len(_json_bytes(value)) > MAX_REPORT_BYTES:
                raise ValueError
            report = parse_report(value)
            if len(_json_bytes(report.to_dict())) > MAX_REPORT_BYTES:
                raise ValueError
            reports.append(report)
        if len({report.observed_instance_id for report in reports}) != len(reports):
            raise ValueError
        canonical = [report.to_dict() for report in reports]
        return reports, _json_bytes({"reports": canonical} if batch else canonical[0])
    except (ValueError, TypeError, UnicodeError, RecursionError, OktoNexusError):
        raise ObservationClientError("REPORT_INVALID",
            "Provide one complete observation or up to 100 distinct-instance reports, each within 4 KiB.") from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError


def _decode(content):
    return json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_invalid_constant)


def _receipt_time(value):
    if type(value) is not str or not _UTC.fullmatch(value):
        raise ValueError
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _receipts(content, reports: list[ObservationReport]):
    value = _decode(content)
    if (type(value) is not dict or set(value) != {"ok", "data"} or value["ok"] is not True
            or type(value["data"]) is not dict or set(value["data"]) != {"receipts"}):
        raise ValueError
    receipts = value["data"]["receipts"]
    if type(receipts) is not list or len(receipts) != len(reports):
        raise ValueError
    validated = []
    for receipt, report in zip(receipts, reports, strict=True):
        if (type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS
                or type(receipt["observed_instance_id"]) is not str
                or receipt["observed_instance_id"] != report.observed_instance_id
                or type(receipt["generation"]) is not int or receipt["generation"] != report.generation
                or type(receipt["sequence"]) is not int or receipt["sequence"] != report.sequence
                or type(receipt["report_hash"]) is not str or receipt["report_hash"] != report_hash(report)
                or type(receipt["replayed"]) is not bool):
            raise ValueError
        received, until = (_receipt_time(receipt[key]) for key in ("received_at", "valid_until"))
        observed = datetime.fromisoformat(report.observed_at.replace("Z", "+00:00"))
        ttl = timedelta(seconds=report.valid_for_seconds)
        if until <= received or until != min(received + ttl, observed + ttl):
            raise ValueError
        # Project closed metadata only. Do not return a raw remote envelope.
        validated.append({key: receipt[key] for key in sorted(_RECEIPT_KEYS)})
    return {"receipts": validated}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def _retry_after(headers):
    value = headers.get("Retry-After", "")
    if type(value) is not str or not value.isascii() or not value.isdecimal():
        return None
    return MAX_RETRY_AFTER_SECONDS if len(value) > 4 else min(int(value), MAX_RETRY_AFTER_SECONDS)


def _read(response, deadline):
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise ValueError
    if response.headers.get_content_type() != "application/json":
        raise ValueError
    content = bytearray()
    while len(content) <= MAX_RESPONSE_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        # HTTPResponse.read1 performs at most one buffered/raw read. Shrink the
        # socket timeout for each read so a trickled body cannot renew the wait.
        http_response = response.fp if isinstance(response, HTTPError) else response
        if http_response.fp is None:
            if http_response.length not in (None, 0):
                raise ValueError
            return bytes(content)
        sock = http_response.fp.raw._sock
        sock.settimeout(remaining)
        chunk = response.read1(min(16384, MAX_RESPONSE_BYTES + 1 - len(content)))
        if not chunk:
            if http_response.length not in (None, 0):
                raise ValueError
            return bytes(content)
        content.extend(chunk)
    raise ValueError


class ObservationClient:
    """Publish with one origin-bound POST, without proxies, cookies or retries.

    timeout is a finite socket timeout in (0, 30] seconds, also bounding body
    collection against the call's monotonic deadline. No expiry is inferred from
    the local clock: an expired replay receipt remains valid historical evidence.
    """

    __slots__ = ("_origin", "_token", "_timeout")

    def __init__(self, server_origin, *, token, timeout=15):
        self._origin = normalize_server_origin(server_origin)
        if not is_well_formed_observation_token(token):
            raise ObservationClientError("TOKEN_INVALID", "Use an observation publish credential.")
        if (type(timeout) not in (int, float) or not 0 < timeout <= MAX_TIMEOUT_SECONDS
                or not math.isfinite(timeout)):
            raise ObservationClientError("TIMEOUT_INVALID", "Use a finite timeout greater than zero and at most 30 seconds.")
        self._token, self._timeout = token, float(timeout)

    def __repr__(self):
        return "ObservationClient()"

    def publish(self, payload):
        """Return validated receipts. Caller owns durable payload and explicit retry."""
        reports, body = _prepare(payload)
        request = Request(self._origin + PUBLISH_PATH, data=body, method="POST", headers={
            "Authorization": "Bearer " + self._token, "Content-Type": "application/json",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        deadline = time.monotonic() + self._timeout
        try:
            with opener.open(request, timeout=self._timeout) as response:
                if response.status != 200:
                    raise ValueError
                content = _read(response, deadline)
                return _receipts(content, reports)
        except HTTPError as error:
            status, retry = error.code, _retry_after(error.headers)
            try:
                if status in _REFUSALS:
                    code, message = _REFUSALS[status]
                    failure = ObservationClientError(code, message, status=status,
                        retry_after_seconds=retry if status == 429 else None)
                elif status == 503:
                    try:
                        value = _decode(_read(error, deadline))
                        busy = (type(value) is dict and set(value) == {"ok", "error"} and value.get("ok") is False
                                and type(value.get("error")) is dict
                                and {"code", "message"} <= value["error"].keys()
                                and not value["error"].keys() - {"code", "message", "details"}
                                and type(value["error"].get("message")) is str
                                and value["error"].get("code") == "OBSERVATION_BUSY")
                    except Exception:
                        busy = False
                    failure = ObservationClientError("OBSERVATION_BUSY" if busy else "OBSERVATION_UNAVAILABLE",
                        "Observation publication is temporarily unavailable.", status=status,
                        outcome_unknown=not busy, retry_after_seconds=retry)
                else:
                    failure = ObservationClientError("REDIRECT_REFUSED" if 300 <= status < 400 else "HTTP_ERROR",
                        "The Server returned an unsupported publication response.",
                        status=status, outcome_unknown=True)
            finally:
                try:
                    error.close()
                except Exception:
                    pass
            raise failure from None
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError, AttributeError):
            raise ObservationClientError("RESPONSE_INVALID", "The publication receipt could not be validated.",
                                         outcome_unknown=True) from None
        except Exception:
            raise ObservationClientError("TRANSPORT_ERROR", "The publication response was not received completely.",
                                         outcome_unknown=True) from None
