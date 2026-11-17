"""New UI042 campaign guards. No product imports, credentials or effects at import."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os

POLICY = {
    "max_admissions": 6,
    "observed_limit": 500000,
    "preventive": 450000,
    "reserve": 50000,
    "provision_per_admission": 75000,
    "accounting": "observed_plus_permanent_per_admission_v1",
    "provision_refund": False,
    "codex_final_usage_claim": False,
    "codex_scope": "cumulative_thread_delta_per_exact_session",
}
ORDER = (
    "codex_a.setup",
    "codex_b.setup",
    "codex_a.work",
    "codex_a.continue",
    "codex_b.work",
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 4 * 1048576, "DOCUMENT_LIMIT")
    return json.loads(raw)


def owned(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    require(path.is_relative_to(root), "OUTSIDE_CAMPAIGN")
    for part in (path, *path.parents):
        if part.exists():
            state = part.lstat()
            require(
                not part.is_symlink()
                and not getattr(state, "st_file_attributes", 0) & 0x400,
                "REPARSE_PATH_REFUSED",
            )
    require(path.resolve().is_relative_to(root.resolve()), "OUTSIDE_CAMPAIGN")
    return path


def publish(path, value):
    path = Path(path)
    # Final and partial files are both exclusive. A crashed write never becomes
    # an empty ledger that admits replacement work on a later invocation.
    temporary = path.with_suffix(path.suffix + ".writing")
    require(not path.exists(), "RECORD_ALREADY_EXISTS")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.rename(path)


def consent_valid(plan, consent, plan_sha):
    require(
        consent.get("schema") == "ui042-codex-only-carry-consent-v2"
        and consent.get("campaign_id") == plan["campaign_id"]
        and consent.get("candidate_sha256") == plan_sha
        and consent.get("campaign_root") == plan["campaign_root"]
        and consent.get("policy") == POLICY
        and consent.get("user_authorized_new_campaign") is True
        and consent.get("allow_current_authenticated_codex_cli") is True
        and consent.get("disallow_claude") is True
        and consent.get("acknowledges_observed_not_atomic_billing_cap") is True
        and consent.get("acknowledges_admissions_not_upstream_http_count") is True
        and consent.get("allow_owned_canonical_force_after_normal_deadline") is True
        and consent.get("acknowledges_native_cli_may_write_its_own_login_home") is True
        and isinstance(consent.get("user_response_reference"), str)
        and bool(consent["user_response_reference"]),
        "NEW_CAMPAIGN_CONSENT_REQUIRED",
    )
    issued = datetime.fromisoformat(consent["issued_at"].replace("Z", "+00:00"))
    created = datetime.fromisoformat(plan["created_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    require(
        created <= issued <= now and (now - issued).total_seconds() <= 86400,
        "NEW_CONSENT_EXPIRED_OR_PREDATES_PROPOSAL",
    )


class Budget:
    """Append-only reservation ledger; unknown admission is never refunded/replayed."""

    def __init__(self, root, ids, *, carry=0):
        self.root, self.ids = Path(root), ids
        self.records = []
        self.carry = carry
        self.stream_totals = {}

    @property
    def observed(self):
        return sum(self.stream_totals.values())

    @property
    def charged(self):
        return self.carry + sum(
            max(POLICY["provision_per_admission"], item["observed"])
            for item in self.records
        )

    def reserve(self, kind):
        require(len(self.records) < len(ORDER), "ADMISSION_LIMIT")
        require(kind == ORDER[len(self.records)], "ADMISSION_ORDER_CHANGED")
        require(
            all(item["accounting_valid"] for item in self.records),
            "PREVIOUS_USAGE_UNKNOWN",
        )
        require(
            self.observed < POLICY["observed_limit"]
            and self.charged + POLICY["provision_per_admission"] <= POLICY["preventive"]
            and self.charged + POLICY["provision_per_admission"] + POLICY["reserve"]
            <= POLICY["observed_limit"],
            "PREVENTIVE_BUDGET_REACHED",
        )
        record = {
            "kind": kind,
            "intent_id": self.ids[kind],
            "accounting_valid": False,
            "observed": 0,
            "provision": POLICY["provision_per_admission"],
            "provision_released": False,
            "observed_before": self.observed,
        }
        publish(self.root / (kind + ".reserved.json"), record)
        self.records.append(record)
        return record

    def account(self, kind, stream, total, *, terminal):
        require(
            self.records and self.records[-1]["kind"] == kind,
            "ORIGINAL_RESERVATION_REQUIRED",
        )
        require(
            type(total) is int and total >= self.stream_totals.get(stream, 0),
            "USAGE_REGRESSION",
        )
        record = self.records[-1]
        if "stream" not in record:
            record.update(stream=stream, stream_base=self.stream_totals.get(stream, 0))
        require(record["stream"] == stream, "ADMISSION_STREAM_CHANGED")
        record["observed"] = max(record["observed"], total - record["stream_base"])
        self.stream_totals[stream] = total
        require(self.observed < POLICY["observed_limit"], "OBSERVED_BUDGET_STOP")
        require(
            self.observed < POLICY["preventive"]
            and self.charged <= POLICY["preventive"],
            "PREVENTIVE_BUDGET_REACHED",
        )
        if terminal:
            record["accounting_valid"] = True
            publish(
                self.root / (kind + ".accounted.json"),
                {
                    "stream": stream,
                    "stream_observed_total": total,
                    "campaign_observed_total": self.observed,
                    "charged_permanent_provisions": self.charged,
                    "provision_released": False,
                    "reported_accounting_final": False,
                    "execution_terminal_and_correlated_usage_seen": True,
                },
            )
