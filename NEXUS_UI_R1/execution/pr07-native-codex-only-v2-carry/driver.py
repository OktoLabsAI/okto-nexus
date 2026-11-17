"""Executable UI042 controller. All product/native effects follow NEW consent.

No old campaign controller, consent, account or root is imported. Offline tests
inject a port; the real port uses installed canonical Nexus application APIs.
"""

from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import sysconfig
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety import (
    Budget,
    ORDER,
    POLICY,
    consent_valid,
    digest,
    owned,
    publish,
    read,
    require,
    sha,
)
from usage import snapshot


def campaign_environment(source):
    return {
        key: value
        for key, value in source.items()
        if key.upper() not in ("PYTHONPATH", "PYTHONHOME")
        and not key.upper().startswith(
            ("OPENAI_", "ANTHROPIC_", "CLAUDE_", "CODEX_", "OKTO_", "NEXUS_")
        )
    }


def observe_home_window(
    root,
    campaign_id,
    *,
    timeout=180,
    monotonic=time.monotonic,
    sleep=time.sleep,
    alive=lambda: None,
):
    """A finite passive browser handoff; a marker is evidence reference, not authority."""
    require(0 <= timeout <= 180, "OBSERVER_WINDOW_BOUND")
    marker = owned(root, Path(root) / "public" / "observer.done")
    deadline = monotonic() + timeout
    while True:
        alive()
        if marker.is_file():
            value = read(marker)
            require(
                value.get("campaign_id") == campaign_id, "OBSERVER_MARKER_SCOPE_CHANGED"
            )
            return {
                "status": "OBSERVER_DONE",
                "campaign_id": campaign_id,
                "evidence_ref": value.get("evidence_ref"),
                "productive_calls": 0,
            }
        if monotonic() >= deadline:
            return {
                "status": "NOT_RUN",
                "reason": "OBSERVER_WINDOW_EXPIRED",
                "productive_calls": 0,
            }
        sleep(min(1, max(0, deadline - monotonic())))


def work_journal_path(home, executor_id, session_id):
    key = hashlib.sha256((executor_id + "\0" + session_id).encode("ascii")).hexdigest()
    return Path(home) / "core-runtime" / ("session-" + key + ".db")


def verify_carry(plan):
    import sqlite3

    carry = plan["carry"]
    require(
        carry["charged_tokens"] == 75000
        and carry["reserved_slots"] == 1
        and carry["observed_tokens"] == 0
        and carry["maximum_new_slots"] == len(ORDER) == 5
        and carry["maximum_global_slots"] == 6,
        "EXACT_CARRY_REQUIRED",
    )
    for pin in carry["proof_pins"]:
        require(sha(pin["path"]) == pin["sha256"], "CARRY_PROOF_CHANGED")
    oldroot = Path(carry["previous_root"])
    require(
        oldroot.parent.resolve() == Path(plan["temporary_parent"]).resolve()
        and oldroot != Path(plan["campaign_root"]),
        "CARRY_ROOT_INVALID",
    )
    require(
        len(list((oldroot / "private").glob("*.reserved.json"))) == 1,
        "CARRY_RESERVATIONS_CHANGED",
    )
    oldcleanup = read(oldroot / "public/cleanup.json")
    shutdown = read(oldroot / "home/service-shutdown.json")
    require(
        oldcleanup.get("settlement_confirmed") is True
        and oldcleanup.get("physical_exit") is True
        and shutdown.get("state") == "DRAINED",
        "CARRY_SETTLEMENT_REQUIRED",
    )
    require(
        not list((oldroot / "home/connection-tests").glob("*/journal.db")),
        "CARRY_NATIVE_TEST_FOUND",
    )
    with sqlite3.connect(
        (oldroot / "home/nexus.db").as_uri() + "?mode=ro", uri=True
    ) as db:
        db.execute("PRAGMA query_only=ON")
        for table in (
            "execution_operations",
            "execution_sessions",
            "runtime_execution_grants",
            "execution_bindings",
            "connection_setup_commits",
            "execution_realizations",
            "execution_local_realizations",
        ):
            require(
                db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0,
                "CARRY_PREVIOUS_EFFECTS_FOUND",
            )
        require(
            db.execute(
                "SELECT COUNT(*) FROM agents WHERE agent_id LIKE 'ui042-%'"
            ).fetchone()[0]
            == 0,
            "CARRY_PREVIOUS_IDENTITY_FOUND",
        )


def inventory_gate(
    load,
    *,
    executor_id,
    binding,
    monotonic=time.monotonic,
    sleep=time.sleep,
    timeout=120,
    alive=lambda: None,
):
    require(0 < timeout <= 120, "INVENTORY_GATE_DEADLINE")
    deadline = monotonic() + timeout
    while True:
        alive()
        try:
            value = load()
            require(value["executor_id"] == executor_id, "INVENTORY_EXECUTOR_CHANGED")
            rows = [
                row
                for row in value["options"]
                if row["adapter_id"] == binding["adapter_id"]
                and row["candidate_ref"] == binding["candidate_ref"]
            ]
            available = [
                row
                for row in value["availability"]["availability"]
                if row["adapter_id"] == binding["adapter_id"]
                and row["candidate_ref"] == binding["candidate_ref"]
            ]
            if (
                value["adapter_freshness"].get(binding["adapter_id"]) == "FRESH"
                and len(rows) == len(available) == 1
                and rows[0]["can_configure"]
            ):
                require(
                    available[0].get("version") == binding.get("version"),
                    "INVENTORY_VERSION_CHANGED",
                )
                require(
                    isinstance(value.get("inventory_revision"), str)
                    and value["inventory_revision"],
                    "INVENTORY_REVISION_REQUIRED",
                )
                return {
                    "executor_id": executor_id,
                    "candidate_ref": binding["candidate_ref"],
                    "adapter_id": binding["adapter_id"],
                    "version": available[0].get("version"),
                    "inventory_revision": value["inventory_revision"],
                    "adapter_freshness": "FRESH",
                }
        except Exception as error:
            if getattr(error, "code", None) not in ("NOT_FOUND", "SERVER_UNREACHABLE"):
                raise
        require(monotonic() < deadline, "INVENTORY_NOT_READY_BEFORE_RESERVATION")
        sleep(min(0.5, max(0, deadline - monotonic())))


def preflight(plan, consent, plan_sha):
    consent_valid(
        plan, consent, plan_sha
    )  # Before product imports, mkdir or native access.
    require(
        plan["policy"] == POLICY and plan["admission_order"] == list(ORDER),
        "POLICY_CHANGED",
    )
    require(plan["schema"] == "ui042-codex-only-carry-campaign-v2", "PLAN_SCHEMA")
    root = Path(plan["campaign_root"])
    require(
        root.is_absolute()
        and root.parent.resolve() == Path(plan["temporary_parent"]).resolve()
        and root.name == "nexus-ui042-codex-only-carry-" + plan["campaign_id"],
        "NEW_OWN_ROOT_REQUIRED",
    )
    require(not root.exists(), "FRESH_ROOT_REQUIRED_NO_REPLAY")
    require(
        plan.get("package_bound") is True and plan.get("native_bindings_bound") is True,
        "EXACT_PACKAGE_AND_NATIVE_BINDINGS_REQUIRED",
    )
    require(
        set(plan["native"]) == {"codex_a", "codex_b"}, "ONLY_TWO_CODEX_BINDINGS_ALLOWED"
    )
    require(
        all(
            binding["adapter_id"] == "codex_app_server"
            and binding["model_id"] == "gpt-5.3-codex"
            for binding in plan["native"].values()
        ),
        "ONLY_EXACT_CODEX_MODEL_ALLOWED",
    )
    verify_carry(plan)
    require(
        Path(sys.executable).resolve() == Path(plan["python"]["path"]).resolve()
        and sha(sys.executable) == plan["python"]["sha256"],
        "INSTALLED_PYTHON_CHANGED",
    )
    for pin in plan["package_pins"]:
        require(sha(pin["path"]) == pin["sha256"], "PACKAGE_PIN_CHANGED")
    purelib = Path(sysconfig.get_path("purelib")).resolve()
    for wheel in plan["wheels"]:
        with zipfile.ZipFile(wheel["path"]) as archive:
            for item in archive.infolist():
                if not item.is_dir() and item.filename.startswith(
                    wheel["module"] + "/"
                ):
                    installed = (purelib / item.filename).resolve()
                    require(
                        installed.is_relative_to(purelib)
                        and installed.read_bytes() == archive.read(item),
                        "INSTALLED_WHEEL_BYTES_CHANGED",
                    )
    require(len(plan["installed_payloads"]) >= 708, "INSTALLED_PAYLOAD_PROOF_REQUIRED")
    require(
        len({pin["path"] for pin in plan["installed_payloads"]})
        == len(plan["installed_payloads"]),
        "DUPLICATE_PAYLOAD_PROOF",
    )
    for pin in plan["driver_pins"]:
        require(sha(pin["path"]) == pin["sha256"], "DRIVER_CHANGED")
    for pin in plan["installed_payloads"]:
        target = Path(pin["path"]).resolve()
        require(
            target.is_relative_to(Path(sys.prefix).resolve())
            and sha(target) == pin["sha256"],
            "INSTALLED_PAYLOAD_CHANGED",
        )
    for client in ("codex_a", "codex_b"):
        binding = plan["native"][client]
        require(
            binding["account"] == "currently_authenticated_cli"
            and isinstance(binding.get("candidate_ref"), str)
            and binding["candidate_ref"]
            and Path(binding["executable"]).is_absolute()
            and sha(binding["executable"]) == binding["executable_sha256"],
            "EXACT_NATIVE_BINDING_REQUIRED",
        )
        require(
            isinstance(binding.get("provider_home"), str)
            and Path(binding["provider_home"]).is_absolute(),
            "EXPLICIT_PROVIDER_HOME_REQUIRED_NO_AUTH_FILE_READ",
        )
        require(
            isinstance(binding.get("model_id"), str) and binding["model_id"],
            "EXACT_MODEL_REQUIRED",
        )
        from nexus_connector_core.discovery import candidate
        from nexus_connector_core.installation import effective_installation_ref

        actual = candidate(
            binding["adapter_id"],
            binding["executable"],
            explicit=True,
            trusted_roots=(Path(binding["installation_root"]),),
        )
        require(
            effective_installation_ref(actual) == binding["candidate_ref"]
            and actual.fingerprint == binding["fingerprint"]
            and actual.build_identity == binding["build_identity"],
            "NATIVE_CANDIDATE_PATH_BYTES_OR_BUILD_CHANGED",
        )


def useful_result(phase, operations):
    turns = [item for item in operations if item["action"] == "turn.submit"]
    require(
        len(turns) == 1 and turns[0].get("executor_stage") == "SUCCEEDED",
        "EXACT_RESULT_REQUIRED",
    )
    text = (turns[0].get("result") or {}).get("output_text")
    require(isinstance(text, str) and len(text) <= 8192, "USEFUL_RESULT_UNKNOWN")
    value = json.loads(text)
    expected = (
        {
            "row_count": 4,
            "total": "20.00",
            "totals_by_category": {
                "hosting": "14.75",
                "software": "8.25",
                "refund": "-3.00",
            },
        }
        if phase == "work"
        else {
            "verified_total": "20.00",
            "surcharge": "2.00",
            "total_with_surcharge": "22.00",
        }
    )
    require(value == expected, "USEFUL_RESULT_ORACLE_MISMATCH_NO_RETRY")
    return value


def execute(plan, consent, plan_sha, *, port_factory=None):
    preflight(plan, consent, plan_sha)
    root = Path(plan["campaign_root"])
    # No operation before this point can open the product, provider or service.
    root.mkdir(exist_ok=False)
    for name in ("home", "project", "private", "public"):
        owned(root, root / name).mkdir()
    ledger = Budget(
        root / "private",
        plan["intent_ids"],
        carry=plan.get("carry", {}).get("charged_tokens", 0),
    )
    publish(
        root / "private" / "selection.json",
        {
            "plan_sha256": plan_sha,
            "campaign_id": plan["campaign_id"],
            "consent_sha256": digest(consent),
            "no_replay": True,
        },
    )
    port = (port_factory or ProductPort)(plan)
    try:
        port.start()
        port.wait_inventory()
        for kind in ORDER:
            client, phase = kind.split(".")
            ledger.reserve(
                kind
            )  # First setup is provisioned too, before native effects.
            result = port.perform(
                kind,
                lambda stream, total, terminal: ledger.account(
                    kind, stream, total, terminal=terminal
                ),
            )
            require(ledger.records[-1]["accounting_valid"], "CORRELATED_USAGE_UNKNOWN")
            publish(
                root / "public" / (kind + ".json"),
                result | {"campaign_observed_tokens": ledger.observed},
            )
            if kind == "codex_b.setup":
                port.assert_first_connection_preserved()
        info = port.observer_info()
        publish(
            root / "public" / "observer-ready.json",
            {
                "campaign_id": plan["campaign_id"],
                "timeout_seconds": 180,
                "no_new_productive_calls": True,
                **info,
            },
        )
        observation = observe_home_window(root, plan["campaign_id"], alive=port.watched)
        publish(root / "public" / "home-observation.json", observation)
    except BaseException as error:
        publish(
            root / "public" / "blocked.json",
            {
                "error_type": type(error).__name__,
                "reason": str(error)
                if isinstance(error, ValueError)
                else "CANONICAL_OPERATION_UNCONFIRMED",
                "admissions_closed": True,
                "replay_allowed": False,
                "reserved_admissions": len(ledger.records),
                "historical_reserved_admissions": plan.get("carry", {}).get(
                    "reserved_slots", 0
                ),
            },
        )
        raise
    finally:
        receipt = port.cleanup()
        publish(root / "public" / "cleanup.json", receipt)
    require(receipt.get("settlement_confirmed") is True, "CLEANUP_SETTLEMENT_UNKNOWN")
    publish(
        root / "public" / "complete.json",
        {
            "admissions": len(ledger.records),
            "global_reserved_admissions": len(ledger.records)
            + plan.get("carry", {}).get("reserved_slots", 0),
            "observed_tokens": ledger.observed,
            "charged_permanent_provisions": ledger.charged,
            "reported_accounting_final": False,
            "provisions_released": False,
            "ui_and_remote_qualification": "SEPARATE_REAL_EVIDENCE_REQUIRED",
            "home_observation": observation,
        },
    )
    return {
        "campaign_id": plan["campaign_id"],
        "root": str(root),
        "status": "COMPLETED",
    }


class ProductPort:
    """Actual installed facade, real HTTP, foreground owner; no provider SDK bypass."""

    def __init__(self, plan):
        from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
        from okto_nexus.application.terminal_connection import TerminalConnection
        from okto_nexus.application.terminal_work import TerminalWork
        from okto_nexus.config import load_config
        from okto_nexus.bootstrap.local_discovery import LocalDiscoveryConfiguration
        from okto_nexus.adapters.outbound.service_manager.context import (
            execution_context,
        )
        from okto_nexus.adapters.outbound.service_manager.local import (
            LocalServerLifecycle,
        )
        from okto_nexus.application.service_lifecycle import ServiceLifecycle

        self.Connection, self.Work = TerminalConnection, TerminalWork
        self.plan, self.root = plan, Path(plan["campaign_root"])
        self.home, self.project = self.root / "home", self.root / "project"
        self.call = LocalOperatorHTTP(host="127.0.0.1", port=plan["port"], timeout=5)
        self.common = [
            "--home",
            str(self.home),
            "--db-path",
            str(self.home / "nexus.db"),
            "--metrics-dir",
            str(self.home / "metrics"),
            "--metrics-mode",
            "disabled",
            "--embedding-mode",
            "off",
            "--host",
            "127.0.0.1",
            "--port",
            str(plan["port"]),
        ]
        self.env = campaign_environment(os.environ)
        self.env["OKTO_NEXUS_NO_BANNER"] = "1"
        roots = tuple(
            Path(plan["native"][client]["installation_root"])
            for client in ("codex_a", "codex_b")
        )
        config = load_config(
            {},
            [
                "--home",
                str(self.home),
                "--db-path",
                str(self.home / "nexus.db"),
                "--metrics-dir",
                str(self.home / "metrics"),
                "--metrics-mode",
                "disabled",
                "--embedding-mode",
                "off",
            ],
        )
        context = execution_context(
            config,
            host="127.0.0.1",
            port=plan["port"],
            project_root=str(self.project),
            log_level="warning",
            discovery=LocalDiscoveryConfiguration(roots),
            env=self.env,
        )
        self.service = ServiceLifecycle(
            LocalServerLifecycle(
                home=self.home,
                database=config.db_path,
                host="127.0.0.1",
                port=plan["port"],
                context=context,
            ),
            monotonic=time.monotonic,
            sleep=time.sleep,
        )
        self.process = self.owner = self.owner_handle = None
        self.documents, self.work, self.journals = {}, {}, {}
        self.work_anchors = {}
        self.save_lock = threading.Lock()
        self.first_snapshot = None

    def save(self, name, value):
        # Private checkpoints may contain reviewed prompts/settings, never keys.
        with self.save_lock:
            directory = self.root / "private" / name
            directory.mkdir(exist_ok=True)
            publish(
                directory
                / (str(len(list(directory.glob("*.json")))).zfill(5) + ".json"),
                value,
            )

    def start(self):
        command = [
            sys.executable,
            "-I",
            "-m",
            "okto_nexus.adapters.inbound.cli.main",
            "serve",
            *self.common,
            "--project-root",
            str(self.project),
            "--embedding-mode",
            "off",
        ]
        for client in ("codex_a", "codex_b"):
            command += [
                "--harness-root",
                self.plan["native"][client]["installation_root"],
            ]
        # No login/config/auth-file read or credential copy is performed here.
        # Core obtains the explicitly approved provider_home only after consent.
        self.log = (self.root / "private" / "server.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            command,
            cwd=self.project,
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            require(self.process.poll() is None, "OWN_SERVER_EXITED")
            value = self.service.inspect(timeout=2)
            if value.get("ready_for_queries"):
                from own_process import Process

                self.owner = {
                    key: value[key] for key in ("instance_id", "pid", "generation")
                }
                self.owner_handle = Process(self.owner["pid"])
                require(
                    self.owner_handle.image in self.plan["python_images"]
                    and sha(self.owner_handle.image)
                    == self.plan["python_images"][self.owner_handle.image],
                    "OWN_SERVER_IMAGE_CHANGED",
                )
                return
            time.sleep(0.25)
        raise ValueError("OWN_SERVER_READINESS_DEADLINE")

    def wait_inventory(self):
        from urllib.parse import quote, urlencode

        me = self.call("GET", "/api/v1/runtime-management/connections/me")
        hosts, cursor = [], None
        for _ in range(10):
            value = self.call(
                "GET",
                "/api/v1/runtime-management/agents/"
                + quote(me["agent_id"], safe="")
                + "/executors?"
                + urlencode(
                    {"limit": 100, **({"after_executor_id": cursor} if cursor else {})}
                ),
            )
            hosts.extend(row for row in value["items"] if row["kind"] == "embedded")
            if not value["has_more"]:
                break
            following = value["next_executor_id"]
            require(
                following and following != cursor, "INVENTORY_EXECUTOR_PAGING_CHANGED"
            )
            cursor = following
        else:
            raise ValueError("INVENTORY_EXECUTOR_PAGING_BOUND")
        require(len(hosts) == 1, "EXACT_EMBEDDED_EXECUTOR_REQUIRED")
        executor = hosts[0]["executor_id"]
        result = inventory_gate(
            lambda: self.call(
                "GET",
                "/api/v1/runtime-management/agents/"
                + quote(me["agent_id"], safe="")
                + "/runtime-options?"
                + urlencode({"executor_id": executor}),
            ),
            executor_id=executor,
            binding=self.plan["native"]["codex_a"],
            alive=self.watched,
        )
        self.save(
            "inventory-ready-before-reservation",
            dict(result, server_id=me["server_id"], model_or_test_admissions=0),
        )

    def watched(self):
        require(
            self.owner_handle is not None and not self.owner_handle.exited(),
            "OWN_OWNER_EXITED",
        )
        value = self.service.inspect(timeout=2)
        require(
            all(value.get(key) == self.owner[key] for key in self.owner),
            "OWN_OWNER_CHANGED",
        )

    def review(self, client):
        native = self.plan["native"][client]
        selection = {
            "agent": self.plan["agent_ids"][client],
            "create_agent": True,
            "client": "codex",
            "candidate_ref": native["candidate_ref"],
            "project": str(self.project),
            "provider_home": native["provider_home"],
            "label": "UI042 isolated project",
            "display_name": "UI042 " + client,
            "setup_intent_id": self.plan["intent_ids"][client + ".setup"],
        }
        if client == "codex_b":
            selection["workspace_id"] = self.documents["codex_a"]["result"]["binding"][
                "workspace_id"
            ]
        flow = self.Connection(
            self.call, lambda value: self.save(client + "-connection", value)
        )
        document = flow.review(selection)
        require(document["state"] == "review", "NEW_REVIEW_REQUIRED")
        options = flow.options(document["request"])
        matching = [
            item
            for item in options["options"]
            if item["candidate_ref"] == native["candidate_ref"]
            and item["adapter_id"] == native["adapter_id"]
        ]
        require(
            len(matching) == 1 and matching[0]["can_configure"],
            "CANONICAL_INSTALLATION_CHANGED",
        )
        catalog = matching[0].get("harness_configuration", {})
        fields = [
            item
            for item in catalog.get("parameters", [])
            if item.get("name") == "model"
        ]
        require(
            len(fields) == 1 and fields[0].get("core_applies") is True,
            "CANONICAL_MODEL_PARAMETER_NOT_SUPPORTED",
        )
        require(
            native["model_id"] == "gpt-5.3-codex"
            and native["adapter_id"] == "codex_app_server"
            and fields[0].get("native_parameter") == "model",
            "EXACT_DOCUMENTED_CODEX_MODEL_REQUIRED",
        )
        # No invented CLI --model flag; modify the ordinary, reviewed setup
        # configuration. Server test/Finish still validate its canonical schema.
        for key in ("request", "review_request"):
            document[key]["configuration"]["harness_settings"] = {
                "model": native["model_id"]
            }
        reviewed = {
            key: document[key]
            for key in ("server_id", "selection", "version_check_required", "effects")
        }
        for key in ("identity_creation", "preset_review"):
            if key in document:
                reviewed[key] = document[key]
        reviewed["request"] = document["review_request"]
        from okto_nexus.application.terminal_connection import document_revision

        document["review_revision"] = document_revision(reviewed)
        self.save(client + "-review", document)
        return flow, document

    def perform(self, kind, account):
        self.watched()
        client, phase = kind.split(".")
        native = self.plan["native"][client]
        before = (
            set((self.home / "connection-tests").glob("*/journal.db"))
            if phase == "setup"
            else set()
        )
        if phase == "setup":
            flow, document = self.review(client)

            def action():
                return flow.apply(
                    document, approval=document["review_revision"], timeout=300
                )
        else:
            flow = self.work[client]
            session = None if phase == "work" else flow.document.get("session_id")
            require(
                phase == "work" or isinstance(session, str) and session,
                "EXACT_SESSION_REQUIRED",
            )
            if phase == "continue":
                anchor = self.work_anchors[client]
                observed = flow.observe()
                require(
                    observed["session"]["scope"] == anchor["scope"]
                    and observed["events"]["stream_epoch"] == anchor["scope_tuple"][3],
                    "CONTINUATION_SCOPE_OR_EPOCH_CHANGED_BEFORE_ADMISSION",
                )
                before_usage = snapshot(
                    self.root,
                    anchor["path"],
                    native["adapter_id"],
                    anchor["scope_tuple"],
                    selected_model=native["model_id"],
                )
                require(
                    before_usage["native_identities"] == anchor["native_identities"],
                    "CONTINUATION_NATIVE_ID_CHANGED_BEFORE_ADMISSION",
                )

            def action():
                return flow.submit(
                    self.plan["prompts"][phase],
                    action="send",
                    new_session=phase == "work",
                    session_id=session,
                    client_intent_id=self.plan["intent_ids"][kind],
                )

        box, done = {}, threading.Event()

        def dispatch():
            try:
                box["value"] = action()
            except BaseException as error:
                box["error"] = error
            finally:
                done.set()

        worker = threading.Thread(target=dispatch, daemon=True)
        self.dispatch_worker = worker
        worker.start()
        deadline, unknown_since = time.monotonic() + 360, time.monotonic()
        last_usage_sequence = 0
        while time.monotonic() < deadline:
            self.watched()
            if done.is_set() and "error" in box:
                raise box["error"]
            terminal = False
            try:
                if phase == "setup":
                    paths = (
                        set((self.home / "connection-tests").glob("*/journal.db"))
                        - before
                    )
                    require(len(paths) == 1, "SETUP_JOURNAL_NOT_YET_UNIQUE")
                    path = next(iter(paths))
                    scope = ("connection-test", "local", "session", "epoch")
                    expected = {"turn"}
                    terminal = done.is_set()
                else:
                    require(
                        flow.document.get("session_id"),
                        "PAID_OPERATION_NOT_YET_CORRELATED",
                    )
                    require(
                        flow.document.get("work", {}).get("client_intent_id")
                        == self.plan["intent_ids"][kind],
                        "PAID_OPERATION_NOT_YET_CORRELATED",
                    )
                    # No explicit session argument: the facade then reads the
                    # original saved intent receipt and its exact operations.
                    value = flow.observe()
                    require(
                        value["state"] != "needs_input",
                        "HUMAN_DECISION_REQUIRED_NO_AUTO_APPROVAL",
                    )
                    scope_value = value["session"]["scope"]
                    if phase == "continue":
                        require(
                            scope_value["session_id"] == session,
                            "CONTINUATION_SESSION_CHANGED",
                        )
                    epoch = value["events"].get("stream_epoch")
                    require(epoch, "STREAM_NOT_YET_AVAILABLE")
                    path = work_journal_path(
                        self.home, scope_value["executor_id"], scope_value["session_id"]
                    )
                    scope = (
                        scope_value["server_id"],
                        scope_value["executor_id"],
                        scope_value["session_id"],
                        epoch,
                    )
                    expected = {
                        item["operation_id"]
                        for item in value["operations"]
                        if item["action"] == "turn.submit"
                    }
                    require(expected, "PAID_OPERATION_NOT_YET_CORRELATED")
                    terminal = done.is_set() and value["state"] in (
                        "completed",
                        "failed",
                        "blocked",
                    )
                usage = snapshot(
                    self.root,
                    path,
                    native["adapter_id"],
                    scope,
                    selected_model=native["model_id"],
                )
                if phase == "continue":
                    require(
                        scope_value == anchor["scope"]
                        and scope == anchor["scope_tuple"]
                        and usage["native_identities"] == anchor["native_identities"],
                        "CONTINUATION_NATIVE_CONTEXT_CHANGED",
                    )
                accounting_valid = expected <= set(
                    usage["accounting_operations"]
                ) and expected <= set(usage["terminal_operations"])
                account(str(path), usage["total"], terminal and accounting_valid)
                current_usage_sequence = max(
                    (
                        usage["usage_sequence_by_operation"].get(item, 0)
                        for item in expected
                    ),
                    default=0,
                )
                if current_usage_sequence > last_usage_sequence:
                    unknown_since = time.monotonic()
                    last_usage_sequence = current_usage_sequence
                if terminal and accounting_valid:
                    break
            except ValueError as error:
                if str(error) not in {
                    "SETUP_JOURNAL_NOT_YET_UNIQUE",
                    "JOURNAL_NOT_YET_AVAILABLE",
                    "STREAM_NOT_YET_AVAILABLE",
                    "PAID_OPERATION_NOT_YET_CORRELATED",
                }:
                    raise
            require(
                time.monotonic() - unknown_since < 30,
                "USAGE_OBSERVATION_UNKNOWN_DEADLINE",
            )
            time.sleep(0.5)
        else:
            raise ValueError("ADMISSION_OBSERVATION_DEADLINE")
        if phase == "setup":
            require(
                box["value"].get("state") == "configured"
                and document.get("state") == "done",
                "CANONICAL_FINISH_REQUIRED",
            )
            self.documents[client] = document
            self.work[client] = self.Work(
                self.call, lambda value: self.save(client + "-work", value), document
            )
            if client == "codex_a":
                self.first_snapshot = self.connection_snapshot("codex_a")
            return {
                "state": "configured",
                "binding_id": box["value"]["binding_id"],
                "workspace_id": box["value"]["workspace_id"],
                "test_and_finish_confirmed": True,
            }
        require(value["state"] == "completed", "USEFUL_WORK_NOT_COMPLETED")
        verified = useful_result(phase, value["operations"])
        publish(self.project / (client + "-" + phase + ".json"), verified)
        if phase == "work":
            self.work_anchors[client] = {
                "scope": scope_value,
                "scope_tuple": scope,
                "path": path,
                "native_identities": usage["native_identities"],
            }
        return {
            "state": value["state"],
            "session_id": scope_value["session_id"],
            "operation_ids": sorted(expected),
            "same_session_continuation": phase == "continue",
            "useful_result_verified": True,
        }

    def connection_snapshot(self, client):
        document = self.documents[client]
        flow = self.Connection(self.call, lambda value: None)
        binding = document["result"]["binding"]["binding_id"]
        current = flow.current(document["selection"]["agent"], binding)
        # No GET grants endpoint exists in this contract. The canonical review
        # handler uses a read-only UoW; call it directly with a stable ID, without
        # TerminalWork.authorization_review(), uuid generation or checkpoint save.
        grant = self.call(
            "POST",
            "/api/v1/runtime-management/connections/authorizations:review",
            {
                "binding_id": binding,
                "client_request_id": "ui042_snapshot_"
                + self.plan["campaign_id"]
                + "_"
                + client,
                "minutes": 60,
                "max_executions": 20,
            },
        )
        require(not grant.get("has_more_grants"), "COMPLETE_GRANT_SNAPSHOT_REQUIRED")
        return {
            "local_document": digest(document),
            "canonical_configuration": digest(
                {
                    key: current.get(key)
                    for key in (
                        "public_config",
                        "public_config_hash",
                        "endpoint_revision",
                        "baseline",
                        "connections",
                        "project_preset",
                        "mcp_preset",
                        "authorization",
                    )
                }
            ),
            "grant_ids_and_revisions": [
                {
                    key: item.get(key)
                    for key in (
                        "grant_id",
                        "revision",
                        "expires_at",
                        "max_executions",
                        "used_executions",
                        "actions",
                    )
                }
                for item in grant["current_grants"]
            ],
        }

    def observer_info(self):
        return {
            "origin": self.call.base,
            "server_id": self.documents["codex_a"]["server_id"],
            "workspace_id": self.documents["codex_a"]["result"]["binding"][
                "workspace_id"
            ],
            "sessions": {
                client: self.work[client].document["session_id"]
                for client in ("codex_a", "codex_b")
            },
            "authentication": "Canonical loopback local operator of this own Server; no provider token.",
        }

    def assert_first_connection_preserved(self):
        require(
            self.connection_snapshot("codex_a") == self.first_snapshot,
            "FIRST_CONNECTION_CHANGED",
        )
        a, b = (
            self.documents["codex_a"]["result"]["binding"],
            self.documents["codex_b"]["result"]["binding"],
        )
        require(
            a["workspace_id"] == b["workspace_id"]
            and a["binding_id"] != b["binding_id"]
            and a["agent_id"] != b["agent_id"],
            "DISTINCT_CONNECTIONS_SAME_CANONICAL_WORKSPACE_REQUIRED",
        )

    def cleanup(self):
        if self.process is None:
            return {
                "service_started": False,
                "native_admissions_replayed": False,
                "settlement_confirmed": True,
            }
        self.watched()  # Normal stop is generation-fenced too, before any effect.
        normal = self.service.stop(timeout=15)
        forced = False
        if self.owner_handle is not None and not self.owner_handle.exited():
            # Broad consent names this owned campaign's canonical containment;
            # no PID-specific user reapproval loop. Identity is revalidated first.
            self.watched()
            normal = self.service.stop(
                timeout=10, force=True, expected_generation=self.owner["generation"]
            )
            forced = True
        code = self.process.wait(timeout=15)
        exited = self.owner_handle is None or self.owner_handle.exited()
        if self.owner_handle:
            self.owner_handle.close()
        self.log.close()
        require(exited, "OWN_NATIVE_OWNER_EXIT_NOT_CONFIRMED")
        worker = getattr(self, "dispatch_worker", None)
        if worker:
            worker.join(timeout=6)
        worker_exited = worker is None or not worker.is_alive()
        # Physical Server exit alone is NOT proof that native descendants settled.
        shutdown = read(self.home / "service-shutdown.json")
        settled = (
            worker_exited
            and normal.get("state") == "stopped"
            and normal.get("shutdown_outcome") == "drained"
            and shutdown.get("state") == "DRAINED"
            and shutdown.get("generation") == self.owner["generation"]
        )
        return {
            "physical_exit": True,
            "launcher_exit_code": code,
            "canonical_force_used": forced,
            "canonical_state": normal.get("state"),
            "data_preserved": True,
            "no_windows_session_event": True,
            "dispatch_worker_exited": worker_exited,
            "settlement_confirmed": settled,
            "canonical_shutdown_outcome": normal.get("shutdown_outcome"),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("dry-run", "execute"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--consent", type=Path)
    parser.add_argument("--expected-consent-sha256")
    args = parser.parse_args()
    require(sha(args.plan) == args.expected_plan_sha256, "PLAN_CHANGED")
    plan = read(args.plan)
    if args.action == "dry-run":
        print(
            json.dumps(
                {
                    "campaign_id": plan["campaign_id"],
                    "policy": plan["policy"],
                    "order": plan["admission_order"],
                    "effects_started": False,
                    "provider_called": False,
                    "package_bound": plan.get("package_bound"),
                    "native_bindings_bound": plan.get("native_bindings_bound"),
                },
                indent=2,
            )
        )
        return 0
    require(
        args.consent is not None and args.expected_consent_sha256 is not None,
        "NEW_CAMPAIGN_CONSENT_REQUIRED",
    )
    require(sha(args.consent) == args.expected_consent_sha256, "CONSENT_CHANGED")
    print(
        json.dumps(
            execute(plan, read(args.consent), args.expected_plan_sha256), indent=2
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as failure:
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "reason": str(failure),
                    "no_automatic_replay": True,
                }
            )
        )
        raise SystemExit(2) from None
