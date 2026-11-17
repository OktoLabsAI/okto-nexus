"""Synthetic ports and own temporary journals only. Never run a native/provider."""

from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import io

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from safety import Budget, ORDER, POLICY, consent_valid, digest, owned  # noqa: E402
from usage import summarize, snapshot  # noqa: E402

spec = importlib.util.spec_from_file_location("ui042_new_driver", HERE / "driver.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def selection(tmp_path):
    created = datetime.now(timezone.utc) - timedelta(seconds=1)
    plan = {
        "schema": "ui042-campaign-v1",
        "campaign_id": "offline-new-campaign",
        "created_at": created.isoformat(),
        "temporary_parent": str(tmp_path),
        "campaign_root": str(tmp_path / "nexus-ui042-offline-new-campaign"),
        "policy": POLICY,
        "admission_order": list(ORDER),
        "intent_ids": {kind: "new-" + kind for kind in ORDER},
        "package_bound": False,
        "native_bindings_bound": False,
    }
    consent = {
        "schema": "ui042-new-consent-v1",
        "campaign_id": plan["campaign_id"],
        "candidate_sha256": digest(plan),
        "campaign_root": plan["campaign_root"],
        "policy": POLICY,
        "user_authorized_new_campaign": True,
        "allow_current_authenticated_codex_cli": True,
        "allow_current_authenticated_claude_sonnet_cli": True,
        "acknowledges_observed_not_atomic_billing_cap": True,
        "acknowledges_admissions_not_upstream_http_count": True,
        "allow_owned_canonical_force_after_normal_deadline": True,
        "acknowledges_native_cli_may_write_its_own_login_home": True,
        "user_response_reference": "SYNTHETIC_OFFLINE_TEST_NOT_USER_CONSENT",
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    return plan, consent


def test_missing_or_old_consent_refuses_before_factory_root_or_native_read(
    tmp_path, monkeypatch
):
    plan, consent = selection(tmp_path)
    called = []
    monkeypatch.setattr(driver, "sha", lambda path: called.append(path))
    for patch in (
        {"user_authorized_new_campaign": False},
        {"campaign_id": "old"},
        {"candidate_sha256": "old"},
        {"policy": dict(POLICY, observed_limit=200000)},
        {"issued_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()},
        {"allow_owned_canonical_force_after_normal_deadline": False},
    ):
        with pytest.raises(ValueError):
            driver.execute(
                plan,
                consent | patch,
                digest(plan),
                port_factory=lambda value: called.append(value),
            )
    assert called == [] and not Path(plan["campaign_root"]).exists()


def test_valid_consent_still_requires_bound_package_before_any_product_effect(tmp_path):
    plan, consent = selection(tmp_path)
    with pytest.raises(ValueError, match="EXACT_PACKAGE_AND_NATIVE_BINDINGS_REQUIRED"):
        driver.execute(plan, consent, digest(plan))
    assert not Path(plan["campaign_root"]).exists()


def test_six_synthetic_admissions_cleanup_then_complete_no_seventh_or_replay(
    tmp_path, monkeypatch
):
    plan, consent = selection(tmp_path)
    calls = []

    def gate(value, approval, expected):
        consent_valid(value, approval, expected)
        assert not Path(value["campaign_root"]).exists()

    monkeypatch.setattr(driver, "preflight", gate)
    monkeypatch.setattr(
        driver,
        "observe_home_window",
        lambda *args, **kwargs: {"status": "SYNTHETIC_NOT_BROWSER_EVIDENCE"},
    )

    class FakePort:
        def __init__(self, value):
            self.root = Path(value["campaign_root"])

        def start(self):
            calls.append("start")

        def perform(self, kind, account):
            calls.append(kind)
            assert (self.root / "private" / (kind + ".reserved.json")).exists()
            account(kind, 100, True)
            return {"synthetic": True}

        def assert_first_connection_preserved(self):
            calls.append("A-preserved")

        def observer_info(self):
            return {}

        def watched(self):
            pass

        def cleanup(self):
            assert not (self.root / "public/complete.json").exists()
            calls.append("cleanup")
            return {"settlement_confirmed": True, "SYNTHETIC": True}

    driver.execute(plan, consent, digest(plan), port_factory=FakePort)
    assert [item for item in calls if item in ORDER] == list(ORDER)
    assert calls[-1] == "cleanup"
    complete = json.loads(
        (Path(plan["campaign_root"]) / "public/complete.json").read_text()
    )
    assert complete["charged_permanent_provisions"] == 450000
    assert (
        complete["reported_accounting_final"] is False
        and complete["provisions_released"] is False
    )


def test_cleanup_not_asserted_never_creates_complete(tmp_path, monkeypatch):
    plan, consent = selection(tmp_path)
    monkeypatch.setattr(driver, "preflight", lambda *args: None)
    monkeypatch.setattr(
        driver,
        "observe_home_window",
        lambda *args, **kwargs: {"status": "SYNTHETIC_NOT_BROWSER_EVIDENCE"},
    )

    class FakePort:
        def __init__(self, value):
            pass

        def start(self):
            pass

        def perform(self, kind, account):
            account(kind, 1, True)
            return {}

        def assert_first_connection_preserved(self):
            pass

        def observer_info(self):
            return {}

        def watched(self):
            pass

        def cleanup(self):
            return {"physical_exit": True, "settlement_confirmed": False}

    with pytest.raises(ValueError, match="SETTLEMENT_UNKNOWN"):
        driver.execute(plan, consent, digest(plan), port_factory=FakePort)
    assert not (Path(plan["campaign_root"]) / "public/complete.json").exists()


def test_permanent_provision_never_refunds_after_tiny_terminal_usage(tmp_path):
    budget = Budget(tmp_path, {kind: kind for kind in ORDER})
    for index, kind in enumerate(ORDER):
        budget.reserve(kind)
        budget.account(kind, kind, 1, terminal=True)
        assert budget.charged == (index + 1) * 75000
    assert budget.observed == 6
    with pytest.raises(ValueError, match="ADMISSION_LIMIT"):
        budget.reserve("seventh")
    fresh = Budget(tmp_path, {kind: kind for kind in ORDER})
    with pytest.raises(ValueError, match="RECORD_ALREADY_EXISTS"):
        fresh.reserve(ORDER[0])


def test_unknown_blocks_and_excess_usage_never_borrows_another_admission_provision(
    tmp_path,
):
    budget = Budget(tmp_path, {kind: kind for kind in ORDER})
    budget.reserve(ORDER[0])
    with pytest.raises(ValueError, match="PREVIOUS_USAGE_UNKNOWN"):
        budget.reserve(ORDER[1])
    budget.account(ORDER[0], "codex-test", 100000, terminal=True)
    for kind in ORDER[1:5]:
        budget.reserve(kind)
        budget.account(kind, kind, 1, terminal=True)
    assert budget.charged == 400000
    with pytest.raises(ValueError, match="PREVENTIVE"):
        budget.reserve(ORDER[5])


def test_stream_delta_and_per_admission_claude_reports_are_counted_separately(tmp_path):
    budget = Budget(tmp_path, {kind: kind for kind in ORDER})
    for kind, stream, total in (
        (ORDER[0], "setupA", 10),
        (ORDER[1], "setupB", 20),
        (ORDER[2], "codex-work-thread", 100),
        (ORDER[3], "codex-work-thread", 150),
        (ORDER[4], "claude-work#op1", 70),
        (ORDER[5], "claude-work#op2", 30),
    ):
        budget.reserve(kind)
        budget.account(kind, stream, total, terminal=True)
    assert budget.observed == 280 and budget.charged == 450000
    assert budget.records[3]["observed"] == 50
    assert budget.records[5]["observed"] == 30


def test_preventive_stop_during_active_admission_and_no_counter_regression(tmp_path):
    budget = Budget(tmp_path, {kind: kind for kind in ORDER})
    budget.reserve(ORDER[0])
    budget.account(ORDER[0], "stream", 100, terminal=False)
    with pytest.raises(ValueError, match="USAGE_REGRESSION"):
        budget.account(ORDER[0], "stream", 99, terminal=False)
    with pytest.raises(ValueError, match="PREVENTIVE"):
        budget.account(ORDER[0], "stream", 450000, terminal=False)
    assert budget.records[0]["accounting_valid"] is False


def row(sequence, operation="op1", **values):
    return (
        dict(
            sequence=sequence,
            operation=operation,
            phase=None,
            outcome=None,
            thread="thread",
            turn=operation,
            native_session="native-session",
            codex_usage=None,
            claude_models=None,
        )
        | values
    )


def codex(total):
    return json.dumps(
        dict(
            totalTokens=total,
            inputTokens=total - 2,
            outputTokens=2,
            cachedInputTokens=0,
            reasoningOutputTokens=0,
        )
    )


def test_old_codex_usage_cannot_cover_new_continuation_terminal():
    values = [
        row(1, phase="started"),
        row(2, codex_usage=codex(100)),
        row(3, phase="terminal", outcome="success"),
        row(4, "op2", phase="started"),
        row(5, "op2", phase="terminal", outcome="success"),
    ]
    result = summarize("codex_app_server", values)
    assert result["accounting_operations"] == ["op1"] and result[
        "terminal_operations"
    ] == ["op1", "op2"]
    assert result["reported_accounting_final"] is False
    values.insert(4, row(4, "op2", codex_usage=codex(120)))
    result = summarize("codex_app_server", values)
    assert result["total"] == 120 and result["accounting_operations"] == ["op1", "op2"]


def test_codex_buckets_must_be_consistent_not_undercounted():
    value = json.loads(codex(100))
    value["inputTokens"] = 1000
    with pytest.raises(ValueError, match="INCONSISTENT"):
        summarize(
            "codex_app_server",
            [row(1, phase="started"), row(2, codex_usage=json.dumps(value))],
        )


def claude(total):
    return json.dumps(
        {
            "claude-sonnet-4-6": dict(
                inputTokens=total - 3,
                outputTokens=1,
                cacheReadInputTokens=1,
                cacheCreationInputTokens=1,
            )
        }
    )


def test_claude_requires_own_terminal_usage_and_sums_per_admission_not_max_session():
    values = [
        row(1, phase="started"),
        row(2, phase="terminal", outcome="success", claude_models=claude(70)),
        row(3, "op2", phase="started"),
        row(4, "op2", phase="terminal", outcome="success", claude_models=claude(30)),
    ]
    result = summarize("claude_stream", values, selected_model="claude-sonnet-4-6")
    assert (
        result["per_operation_totals"] == {"op1": 70, "op2": 30}
        and result["total"] == 100
    )
    values[-1]["claude_models"] = None
    assert summarize("claude_stream", values, selected_model="claude-sonnet-4-6")[
        "accounting_operations"
    ] == ["op1"]
    values[1]["phase"] = None
    with pytest.raises(ValueError, match="TERMINAL_USAGE"):
        summarize("claude_stream", values, selected_model="claude-sonnet-4-6")


def test_owned_journal_projection_is_readonly_bounded_and_never_returns_text(tmp_path):
    path = tmp_path / "journal.db"
    scope = ("server", "executor", "session", "epoch")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE event_streams(server_id,executor_id,session_id,stream_epoch,next_sequence,compacted_sequence)"
        )
        db.execute(
            "CREATE TABLE events(server_id,executor_id,session_id,stream_epoch,sequence,body)"
        )
        db.execute("INSERT INTO event_streams VALUES(?,?,?,?,4,0)", scope)
        for sequence, payload in (
            (1, {"delivery_phase": "started"}),
            (2, {"tokenUsage": {"total": json.loads(codex(100))}}),
            (3, {"delivery_phase": "terminal", "delivery_outcome": "success"}),
        ):
            payload.update(
                thread_id="thread",
                turn_id="turn",
                output_text="PRIVATE_TRANSCRIPT_NOT_SELECTED",
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    *scope,
                    sequence,
                    json.dumps({"operation_id": "op1", "payload": payload}),
                ),
            )
    before = path.read_bytes()
    result = snapshot(tmp_path, path, "codex_app_server", scope)
    assert result["total"] == 100 and path.read_bytes() == before
    assert "PRIVATE_TRANSCRIPT" not in json.dumps(result)
    with pytest.raises(ValueError, match="STREAM_NOT_YET"):
        snapshot(tmp_path, path, "codex_app_server", scope[:3] + ("other",))
    with sqlite3.connect(path) as db:
        db.execute("UPDATE event_streams SET compacted_sequence=1")
    with pytest.raises(ValueError, match="COVERAGE_GAP"):
        snapshot(tmp_path, path, "codex_app_server", scope)


def test_paths_and_useful_results_refuse_escape_or_wrong_output(tmp_path):
    root = tmp_path / "own"
    root.mkdir()
    with pytest.raises(ValueError, match="OUTSIDE"):
        owned(root, tmp_path / "other")
    operation = {
        "action": "turn.submit",
        "executor_stage": "SUCCEEDED",
        "result": {
            "output_text": json.dumps(
                {
                    "verified_total": "20.00",
                    "surcharge": "2.00",
                    "total_with_surcharge": "22.00",
                }
            )
        },
    }
    assert driver.useful_result("continue", [operation])["surcharge"] == "2.00"
    operation["result"]["output_text"] = '{"verified_total":"wrong"}'
    with pytest.raises(ValueError, match="NO_RETRY"):
        driver.useful_result("continue", [operation])


def test_product_descriptor_ignores_personal_db_metrics_environment(
    tmp_path, monkeypatch
):
    outside = tmp_path / "personal"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"untouched")
    monkeypatch.setenv("OKTO_NEXUS_DB_PATH", str(outside / "personal.db"))
    monkeypatch.setenv("OKTO_NEXUS_METRICS_DIR", str(outside / "metrics"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "DO_NOT_COPY_PERSONAL_KEY")
    root = tmp_path / "own"
    roots = []
    for name in ("codex", "claude"):
        directory = tmp_path / (name + "-bin")
        directory.mkdir()
        roots.append(directory)
    value = {
        "campaign_root": str(root),
        "port": 51234,
        "native": {
            name: {"installation_root": str(path)}
            for name, path in zip(("codex", "claude"), roots)
        },
    }
    port = driver.ProductPort(value)
    assert port.service.adapter.home == root / "home"
    assert port.service.adapter.database == root / "home/nexus.db"
    assert not any(
        key.startswith(("OKTO_", "NEXUS_", "ANTHROPIC_"))
        for key in port.env
        if key != "OKTO_NEXUS_NO_BANNER"
    )
    assert (
        marker.read_bytes() == b"untouched"
        and not (outside / "personal.db").exists()
        and not (outside / "metrics").exists()
    )


def test_child_environment_filters_windows_mixed_case_auth_and_paths():
    source = {
        "OpenAi_Api_Key": "personal",
        "aNtHrOpIc_AuTh_ToKeN": "personal",
        "ClAuDe_CoNfIg_DiR": "personal",
        "CoDeX_HoMe": "personal",
        "oKtO_NeXuS_dB_pAtH": "personal",
        "nExUs_CoNnEcToR_tOkEn": "personal",
        "PyThOnPaTh": "personal",
        "pYtHoNhOmE": "personal",
        "ComSpec": "retained-system-command",
    }
    assert driver.campaign_environment(source) == {"ComSpec": "retained-system-command"}


@pytest.mark.parametrize(
    "receipt_generation,expected",
    [("own-generation", True), ("other-generation", False)],
)
def test_cleanup_fences_normal_stop_and_requires_same_generation_drained_receipt(
    tmp_path, receipt_generation, expected
):
    events = []
    state = {"exited": False}
    home = tmp_path / "home"
    home.mkdir()
    (home / "service-shutdown.json").write_text(
        json.dumps({"generation": receipt_generation, "state": "DRAINED"})
    )
    port = driver.ProductPort.__new__(driver.ProductPort)
    port.home = home
    port.owner = {"generation": "own-generation"}
    port.watched = lambda: events.append("identity-fence")
    port.owner_handle = SimpleNamespace(
        exited=lambda: state["exited"], close=lambda: events.append("handle-closed")
    )
    port.process = SimpleNamespace(wait=lambda timeout: 0)
    port.log = io.StringIO()

    def stop(**kwargs):
        events.append("normal-stop")
        state["exited"] = True
        return {"state": "stopped", "shutdown_outcome": "drained"}

    port.service = SimpleNamespace(stop=stop)
    result = port.cleanup()
    assert events[:2] == ["identity-fence", "normal-stop"]
    assert (
        result["physical_exit"] is True and result["settlement_confirmed"] is expected
    )


def test_private_checkpoint_writes_do_not_collide_between_dispatch_and_observer(
    tmp_path,
):
    import threading

    port = driver.ProductPort.__new__(driver.ProductPort)
    port.root = tmp_path
    (tmp_path / "private").mkdir()
    port.save_lock = threading.Lock()
    errors = []

    def save(index):
        try:
            port.save("same-scope", {"index": index})
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=save, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (
        errors == []
        and len(list((tmp_path / "private/same-scope").glob("*.json"))) == 8
    )


def test_home_observer_deadline_is_finite_and_does_not_accept_another_filename(
    tmp_path,
):
    (tmp_path / "public").mkdir()
    (tmp_path / "public/observer.done-other").write_text('{"campaign_id":"campaign"}')
    clock = [0]
    checks = []

    def sleep(seconds):
        clock[0] += seconds

    value = driver.observe_home_window(
        tmp_path,
        "campaign",
        timeout=2,
        monotonic=lambda: clock[0],
        sleep=sleep,
        alive=lambda: checks.append(clock[0]),
    )
    assert (
        value["status"] == "NOT_RUN"
        and value["productive_calls"] == 0
        and clock[0] == 2
    )
    assert checks == [0, 1, 2]


def test_home_observer_requires_exact_campaign_marker_and_can_end_early(tmp_path):
    (tmp_path / "public").mkdir()
    marker = tmp_path / "public/observer.done"
    marker.write_text('{"campaign_id":"other"}')
    with pytest.raises(ValueError, match="MARKER_SCOPE"):
        driver.observe_home_window(tmp_path, "campaign", timeout=2)
    marker.write_text(
        '{"campaign_id":"campaign","evidence_ref":"owned-browser-proof.json"}'
    )
    value = driver.observe_home_window(
        tmp_path, "campaign", sleep=lambda _: pytest.fail("must end immediately")
    )
    assert (
        value["status"] == "OBSERVER_DONE"
        and value["evidence_ref"] == "owned-browser-proof.json"
    )


def test_connection_snapshot_twice_never_mutates_A_document_work_ids_or_issues_grants():
    calls = []
    document = {
        "server_id": "server",
        "selection": {"agent": "agentA"},
        "result": {"binding": {"binding_id": "bindingA"}},
    }
    work = {
        "format": 1,
        "authorization": {"state": "keep-original"},
        "work": {"client_intent_id": "keep-intent"},
    }
    current = {
        "public_config": {"harness_settings": {"model": "chosen-model"}},
        "connections": [{"binding_id": "bindingA"}],
    }
    grants = [
        {
            "grant_id": "grantA",
            "revision": 1,
            "expires_at": None,
            "max_executions": 20,
            "used_executions": 0,
            "actions": ["open", "send"],
        }
    ]

    def call(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return current
        assert method == "POST" and path.endswith("/connections/authorizations:review")
        assert body["client_request_id"] == "ui042_snapshot_new-campaign_codex"
        return {"current_grants": grants, "has_more_grants": False}

    class Connection:
        def __init__(self, transport, save):
            self.call = transport

        def current(self, agent, binding):
            return self.call(
                "GET",
                "/api/v1/runtime-management/connections/setup/"
                + agent
                + "?binding_id="
                + binding,
            )

    port = driver.ProductPort.__new__(driver.ProductPort)
    port.Connection = Connection
    port.call = call
    port.plan = {"campaign_id": "new-campaign"}
    port.documents = {"codex": document}
    port.work = {"codex": SimpleNamespace(document=work)}
    before = json.dumps([document, work, current, grants], sort_keys=True)
    assert port.connection_snapshot("codex") == port.connection_snapshot("codex")
    assert json.dumps([document, work, current, grants], sort_keys=True) == before
    assert [method for method, _, _ in calls] == ["GET", "POST", "GET", "POST"]
