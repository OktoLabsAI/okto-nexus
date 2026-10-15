"""Bounded, payload-free runtime progress queries for already-authorized views."""
import json


class SqliteHandoffRuntimeViewRepository:
    def sample_attempts(self, uow, *, limit):
        if type(limit) is not int or not 1 <= limit <= 1001:
            raise ValueError('Invalid metrics sample bound.')
        return [dict(row) for row in uow.connection.execute('''
            SELECT a.state,a.reason,
                CASE WHEN json_valid(COALESCE(c.reservation_json,a.reservation_json))
                THEN json_extract(COALESCE(c.reservation_json,a.reservation_json),'$.state') END AS reservation_state
            FROM handoff_runtime_attempts a LEFT JOIN execution_capacity_admissions c ON c.domain_operation_id=a.operation_id
            ORDER BY a.updated_at DESC,a.attempt_id DESC LIMIT ?
        ''', (limit,))]

    def sample_handoff_ids(self, uow, *, limit):
        if type(limit) is not int or not 1 <= limit <= 1001:
            raise ValueError('Invalid metrics sample bound.')
        return [row[0] for row in uow.connection.execute('''
            SELECT handoff_id FROM handoffs
            WHERE CASE WHEN json_valid(target) THEN json_extract(target,'$.strategy') END='broadcast'
            ORDER BY created_at DESC,handoff_id DESC LIMIT ?
        ''', (limit,))]

    def handoffs(self, uow, handoff_ids):
        if not handoff_ids:
            return {}
        if len(handoff_ids) > 1000:
            raise ValueError('Handoff projection page exceeds its bound.')
        rows = uow.connection.execute('''
            WITH selected AS (
                SELECT h.handoff_id,h.status,h.claimed_by,h.claim_epoch,h.created_at,
                       b.operation_id AS domain_operation_id,b.created_at AS claimed_at
                FROM handoffs h LEFT JOIN runtime_handoff_bindings b
                  ON b.handoff_id=h.handoff_id AND b.claim_epoch=h.claim_epoch
                WHERE h.handoff_id IN (SELECT value FROM json_each(?))
                  AND json_valid(h.target) AND json_extract(h.target,'$.strategy')='broadcast'
            ), operations AS (
                SELECT d.domain_operation_id,o.server_id,o.executor_id,o.operation_id,o.action,
                       ROW_NUMBER() OVER (PARTITION BY d.domain_operation_id ORDER BY
                         (o.action IN ('turn.submit','turn.steer')) DESC,o.created_at DESC,o.operation_id DESC) AS rank
                FROM selected h JOIN execution_domain_deliveries d ON d.domain_operation_id=h.domain_operation_id
                JOIN execution_operations o USING(server_id,executor_id,operation_id)
                WHERE o.action IN ('runtime.start','turn.submit','turn.steer')
            )
            SELECT h.*,origin.source_kind,schedule.reason AS schedule_reason,
                   capacity.state AS capacity_state,delivery.status AS delivery_state,
                   o.action AS native_action,r.stage AS native_stage,
                   (SELECT MIN(started.received_at) FROM execution_receipts started
                      WHERE started.server_id=o.server_id AND started.executor_id=o.executor_id
                        AND started.operation_id=o.operation_id AND started.stage='RUNNING') AS started_at
            FROM selected h
            LEFT JOIN execution_handoff_origins origin ON origin.handoff_id=h.handoff_id
            LEFT JOIN handoff_runtime_schedule schedule
              ON schedule.handoff_id=h.handoff_id AND schedule.claim_generation=h.claim_epoch
            LEFT JOIN execution_capacity_admissions capacity ON capacity.domain_operation_id=h.domain_operation_id
            LEFT JOIN delivery_outbox delivery ON delivery.operation_id=h.domain_operation_id
            LEFT JOIN operations o ON o.domain_operation_id=h.domain_operation_id AND o.rank=1
            LEFT JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
              AND r.operation_id=o.operation_id AND r.receipt_revision=(
                SELECT MAX(latest.receipt_revision) FROM execution_receipts latest
                WHERE latest.server_id=o.server_id AND latest.executor_id=o.executor_id AND latest.operation_id=o.operation_id)
        ''', (json.dumps(handoff_ids),)).fetchall()
        return {r['handoff_id']: dict(r) for r in rows}

    def agent_attempts(self, uow, agent_id, *, limit):
        if type(limit) is not int or not 1 <= limit <= 21:
            raise ValueError('Invalid attempt page bound.')
        return [dict(row) for row in uow.connection.execute('''
            SELECT a.attempt_id,a.handoff_id,a.workspace_id,a.claim_generation,a.operation_id,a.state,
                   a.active,a.reason,a.created_at,a.updated_at,
                   CASE WHEN json_valid(COALESCE(c.reservation_json,a.reservation_json))
                     THEN json_extract(COALESCE(c.reservation_json,a.reservation_json),'$.state') END AS reservation_state,
                   COALESCE(c.updated_at,a.updated_at) AS reservation_observed_at
            FROM handoff_runtime_attempts a
            LEFT JOIN execution_capacity_admissions c ON c.domain_operation_id=a.operation_id
            WHERE a.agent_id=?
            ORDER BY a.updated_at DESC,a.attempt_id DESC LIMIT ?
        ''', (agent_id, limit))]
