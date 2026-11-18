"""R7 domain equivalence against R6 ordering and discarded-page composition.

Pure complete-relation fixtures; no SQLite, native ingress, provider or browser
proof is implied. The oracle deliberately preserves the preceding algorithm.
"""

from copy import deepcopy
from dataclasses import fields, replace
from datetime import timedelta

import pytest

from okto_nexus.domain import home_entry_pages as pages
from okto_nexus.domain import home_harness_board as harness
from okto_nexus.domain.attention import canonical, digest, instant
from okto_nexus.domain.home_entries import SessionContext
from okto_nexus.errors import OktoNexusError
from tests.home_states.test_operational_status import NOW, facts, question
from tests.home_states.test_revision_equivalence import sample


def previous_revision(relations, check_budget):
    """R6 shallow relation material, including eager JSON tie-break keys."""
    contexts, row_keys = {}, {}

    def context_value(context):
        if context is None:
            return None
        identifier = id(context)
        if identifier not in contexts:
            contexts[identifier] = (context, {f.name: getattr(context, f.name) for f in fields(context)})
        return contexts[identifier][1]

    def row_key(row):
        identifier = id(row)
        if identifier not in row_keys:
            row_keys[identifier] = (row, canonical(row))
        return row_keys[identifier][1]

    values = []
    for entry in sorted(relations.entries, key=lambda item: item.id):
        check_budget()
        value = {f.name: getattr(entry, f.name) for f in fields(entry)}
        value["connection"] = context_value(entry.connection)
        value["sessions"] = tuple(context_value(s) for s in entry.sessions)
        value["registered_connections"] = tuple(context_value(c) for c in entry.registered_connections)
        for name, key in (("operations", "operation_id"), ("attention", "attention_id"),
                          ("results", "id"), ("external", "observed_instance_id")):
            value[name] = sorted(value[name], key=lambda row, key=key: (row[key], row_key(row)))
        values.append(value)
    result = digest({
        "entries": values,
        "server_attention": sorted(relations.server_attention, key=lambda row: row["attention_id"]),
        "source_status": relations.source_status,
        "connection_count": relations.connection_count,
        "connections": None if relations.connections is None else sorted(
            (context_value(c) for c in relations.connections), key=row_key),
    })
    check_budget()
    return result


def previous_metadata(relations, *, scope, server_id, now, partition="groups", group_id=None,
                      entry_id=None, check_budget=lambda: None, presentation_version=1):
    """R6 envelope/refresh calculation, independent of the extracted helper."""
    revision = previous_revision(relations, check_budget)
    if presentation_version == 2:
        revision = digest([2, revision])
    tracking_unknown, old_unknown, unseen = False, False, set()
    refresh = instant(now) + timedelta(seconds=15)
    for entry in relations.entries:
        check_budget()
        for occurrence in entry.attention:
            check_budget()
            change = occurrence.get("next_change_at")
            if change and instant(now) < instant(change):
                refresh = min(refresh, instant(change))
        for observation in entry.external:
            check_budget()
            report = observation.get("last_report")
            if report and observation["freshness"] == "current" and instant(now) < instant(report["valid_until"]):
                refresh = min(refresh, instant(report["valid_until"]))
        for result in entry.results:
            check_budget()
            if result["view_state"] == "unseen":
                unseen.add(result["id"])
            elif result["view_state"] == "not_tracked":
                tracking_unknown = True
                if result["created_at"] is None or instant(result["created_at"]) < instant(now) - timedelta(hours=24):
                    old_unknown = True
    exact = relations.total_is_exact and not (scope["include_recent_results"] and old_unknown)
    for occurrence in relations.server_attention:
        check_budget()
        change = occurrence.get("next_change_at")
        if change and instant(now) < instant(change):
            refresh = min(refresh, instant(change))
    ready = relations.source_status.get("attention") == "ready"
    active_server = sum(o["active"] for o in relations.server_attention)
    value = {
        "version": 1, "scope": scope, "server_id": server_id, "generated_at": now,
        "snapshot_id": revision, "revision": revision, "partition": partition,
        "group_id": group_id, "entry_id": entry_id, "status": "ready" if exact else "partial",
        "source_status": relations.source_status, "items": [], "total": 0 if exact else None,
        "total_is_exact": exact, "has_more": False,
        "inventory": {"connections": {"value": relations.connection_count,
            "total_is_exact": relations.connection_count is not None, "unit": "connections"}},
        "coverage": {"result_tracking": "unknown" if not ready else "partial" if tracking_unknown else "ready"},
        "next_cursor": None,
        "as_of": now, "next_refresh_at": refresh.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "server_attention": {
            "status": "ready" if ready else "unavailable",
            "items": [o for o in relations.server_attention if o["active"]][:3] if partition == "groups" else [],
            "total": active_server if ready else None, "total_is_exact": ready, "has_more": active_server > 3,
        },
        "summary": {"unseen_results": {"value": None if tracking_unknown or not ready else len(unseen),
            "total_is_exact": not tracking_unknown and ready, "unit": "results"}},
    }
    if presentation_version == 2:
        value.update(presentation_version=2, presentation_versions=[1, 2])
    return value


@pytest.mark.parametrize("variant", ["unique", "duplicate_unicode_aliases", "unknown_connections"])
def test_revision_canonical_bytes_stable_order_and_budget_calls_match_r6(monkeypatch, variant):
    rel = sample()
    if variant == "unique":
        for entry in rel.entries:
            entry.operations = [{"operation_id": f"op-{i}", "value": ["雪", None, 1.25]} for i in range(25)]
            entry.results = [{"id": f"result-{i}", "value": i} for i in range(25)]
    elif variant == "unknown_connections":
        rel.connections = rel.connection_count = None
    before = deepcopy(rel)
    old_calls, calls, serialized = [], [], []
    expected = previous_revision(rel, lambda: old_calls.append(1))

    def capture(value):
        serialized.append(canonical(value))
        return digest(value)

    monkeypatch.setattr(pages, "digest", capture)
    assert pages.revision(rel, lambda: calls.append(1)) == expected
    assert len(serialized) == 1 and calls == old_calls and rel == before
    # Input reversals must not perturb the stable canonical tie-break order.
    rel.entries.reverse()
    for entry in rel.entries:
        for name in ("operations", "attention", "results", "external"):
            getattr(entry, name).reverse()
    assert pages.revision(rel, lambda: None) == expected
    assert serialized[-1] == serialized[0]


def test_unique_ids_do_not_serialize_sort_keys_and_alias_ties_serialize_once(monkeypatch):
    rel = sample()
    rel.entries = rel.entries[:1]
    rel.connections = None
    entry = rel.entries[0]
    for name, key in (("operations", "operation_id"), ("attention", "attention_id"),
                      ("results", "id"), ("external", "observed_instance_id")):
        setattr(entry, name, [{key: f"unique-{i}", "nested": ["雪", i]} for i in range(25)])
    calls = []

    def capture(row):
        calls.append(row)
        return canonical(row)

    monkeypatch.setattr(pages, "canonical", capture)
    assert pages.revision(rel, lambda: None) == previous_revision(rel, lambda: None)
    assert calls == []
    shared = {"id": "same", "nested": ["é", "雪"]}
    other = {"id": "same", "nested": ["a"]}
    entry.results = [shared, other, shared]
    assert pages.revision(rel, lambda: None) == previous_revision(rel, lambda: None)
    assert len(calls) == 2 and calls[0] is shared and calls[1] is other
    assert entry.results[0] is entry.results[2] is shared


@pytest.mark.parametrize("bad", ["missing_id", "nan", "unsupported", "circular", "mixed_ids"])
def test_malformed_rows_preserve_r6_failure_type_and_message(bad):
    rel = sample()
    entry = rel.entries[0]
    if bad == "missing_id":
        entry.results = [{"nested": 1}]
    elif bad == "nan":
        entry.results = [{"id": "unique", "nested": float("nan")}]
    elif bad == "unsupported":
        entry.results = [{"id": "unique", "nested": object()}]
    elif bad == "circular":
        row = {"id": "unique"}
        row["nested"] = row
        entry.results = [row]
    else:
        entry.results = [{"id": "text"}, {"id": None}]
    with pytest.raises((KeyError, TypeError, ValueError, RecursionError)) as old:
        previous_revision(rel, lambda: None)
    with pytest.raises(type(old.value)) as current:
        pages.revision(rel, lambda: None)
    assert str(current.value) == str(old.value)


def metadata_relation(mode):
    rel, connection, session, _ = facts()
    question(rel, connection)
    rel.connections += (replace(connection, binding_id="second"), replace(connection, binding_id="third"))
    rel.server_attention = [dict(rel.entries[0].attention[0], attention_id=f"server-{i}",
        next_change_at="2026-11-17T12:00:08.000000Z", active=i != 4) for i in range(5)]
    if mode == "partial":
        rel.source_status["results"] = "unavailable"
        rel.connections = rel.connection_count = None
    elif mode == "expired":
        rel.operational_sessions = (replace(session, valid_until=NOW),)
    elif mode == "retention":
        rel.entries[0].results = [{"id": "old-unknown", "view_state": "not_tracked",
            "created_at": "2026-11-15T12:00:00.000000Z"}]
    # Refresh must include both external validity and attention deadlines.
    rel.entries[0].external = [{"observed_instance_id": "observation", "freshness": "current",
        "last_report": {"valid_until": "2026-11-17T12:00:04.000000Z"}}]
    return rel


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("mode", ["ready", "partial", "expired", "retention"])
def test_metadata_matches_r6_refresh_inventory_unknown_and_revision(version, mode):
    rel = metadata_relation(mode)
    before = deepcopy(rel)
    kwargs = {"scope": pages.filters({}), "server_id": "server", "now": NOW,
              "presentation_version": version}
    assert pages.metadata(rel, **kwargs) == previous_metadata(rel, **kwargs)
    assert rel == before


@pytest.mark.parametrize("version", [1, 2])
def test_entry_page_groups_and_every_related_cursor_match_r6_metadata(monkeypatch, version):
    rel = metadata_relation("ready")
    entry = rel.entries[0]
    entry.external = []
    session = rel.operational_sessions[0]
    entry.sessions = tuple(SessionContext(session.server_id, session.executor_id, session.workspace_id,
        f"session-{i}", session.binding_id, session.workspace_binding_id, session.agent_id, "READY") for i in range(7))
    occurrence = entry.attention[0]
    entry.attention = [dict(occurrence, attention_id=f"attention-{i}") for i in range(7)]
    entry.results = [{"id": f"result-{i}", "created_at": NOW, "view_state": "unseen"} for i in range(7)]
    before = deepcopy(rel)
    kwargs = {"scope": pages.filters({"quick": "all"}), "server_id": "server", "principal": "human",
              "now": NOW, "presentation_version": version, "limit": 2, "preview": 2}

    def compare(**options):
        actual = pages.page(rel, **kwargs, **options)
        with monkeypatch.context() as patch:
            patch.setattr(pages, "metadata", previous_metadata)
            expected = pages.page(rel, **kwargs, **options)
        assert actual == expected and list(actual) == list(expected)
        return actual

    groups = compare()
    group_id = groups["items"][0]["id"]
    child = groups["items"][0]["children"][0]
    assert child["has_more_sessions"] and child["has_more_attention"] and child["has_more_results"]
    compare(partition="children", group_id=group_id)
    for partition in ("sessions", "attention", "results"):
        page = compare(partition=partition, group_id=group_id, entry_id=entry.id)
        seen = list(page["items"])
        for _ in range(4):
            if page["next_cursor"] is None:
                break
            page = compare(partition=partition, group_id=group_id, entry_id=entry.id, cursor=page["next_cursor"])
            seen.extend(page["items"])
        assert len(seen) == 7 and page["next_cursor"] is None
        child_cursor = child[{"sessions": "sessions_cursor", "attention": "attention_cursor",
                              "results": "results_cursor"}[partition]]
        with pytest.raises(OktoNexusError):
            pages.page(rel, **(kwargs | {"principal": "other"}), partition=partition,
                group_id=group_id, entry_id=entry.id, cursor=child_cursor)
    assert rel == before


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("mode", ["ready", "expired"])
def test_board_all_partitions_and_cursors_match_discarded_r6_page_path(monkeypatch, version, mode):
    rel = metadata_relation(mode)
    # A metadata-only external record is intentionally used only by metadata
    # tests; the board fixture needs no external label/rendering contract.
    rel.entries[0].external = []
    kwargs = {"scope": pages.filters({"quick": "all"}), "server_id": "server",
              "principal": "human", "now": NOW, "presentation_version": version,
              "limit": 1, "preview": 1}
    before = deepcopy(rel)
    current_metadata = pages.metadata

    def discarded_page_path(relation, **options):
        with monkeypatch.context() as patch:
            patch.setattr(pages, "metadata", previous_metadata)
            return pages.page(relation, principal="human", limit=1, preview=1, **options)

    def compare(**options):
        actual = harness.page(rel, **kwargs, **options)
        with monkeypatch.context() as patch:
            patch.setattr(pages, "metadata", discarded_page_path)
            assert harness.page(rel, **kwargs, **options) == actual
        assert pages.metadata is current_metadata
        return actual

    root = compare()
    assert root["inventory"]["registered_harnesses"]["value"] == 3
    for column, page in root["columns"].items():
        if page["next_cursor"]:
            compare(partition="column", column=column, cursor=page["next_cursor"])
        for item in page["items"]:
            if item["kind"] == "harness":
                compare(partition="children", card_id=item["id"])
                if version == 2:
                    compare(partition="sessions", card_id=item["id"])
                    compare(partition="requests", card_id=item["id"])
    compare(partition="unlinked")
    assert rel == before


@pytest.mark.parametrize("version", [1, 2])
def test_board_does_not_render_a_discarded_entry_page(monkeypatch, version):
    rel, _, _, _ = facts()

    def forbidden(*args, **kwargs):
        pytest.fail("Harness board must not build an entry page just to discard its grouping/DTO/counts")

    monkeypatch.setattr(pages, "page", forbidden)
    value = harness.page(rel, scope=pages.filters({"quick": "all"}), server_id="server",
        principal="human", now=NOW, presentation_version=version)
    assert value["entry_revision"] and value["inventory"]["registered_harnesses"]["value"] == 1


@pytest.mark.parametrize("layer", ["metadata", "page", "board"])
def test_budget_error_propagates_without_mutation_or_partial_success(layer):
    rel, _, _, _ = facts()
    before = deepcopy(rel)

    def budget():
        raise OktoNexusError("HOME_QUERY_BUDGET", "Own read deadline", {})

    call = pages.metadata if layer == "metadata" else pages.page if layer == "page" else harness.page
    kwargs = {"scope": pages.filters({"quick": "all"}), "server_id": "server", "now": NOW,
              "check_budget": budget}
    if layer != "metadata":
        kwargs["principal"] = "human"
    with pytest.raises(OktoNexusError) as error:
        call(rel, **kwargs)
    assert error.value.code == "HOME_QUERY_BUDGET" and rel == before
