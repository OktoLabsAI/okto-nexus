"""Bounded local Core event publication with durable Server ACK recovery."""
import asyncio
from dataclasses import asdict

from nexus_connector_core import CoreError, EventCursor, R4_PREVIEW_REVISION
from nexus_connector_core.protocol import canonical_json

from ..application.execution_events import commit_execution_events


class EmbeddedEventPublisher:
    def __init__(self, owner):
        self.owner = owner
        self.after = 0

    def _page(self, *, after=None, agent_id=None, live_only=False):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            rows = uow.connection.execute("SELECT rowid,* FROM execution_local_streams "
                "WHERE server_id=? AND executor_id=? AND rowid>? AND (? IS NULL OR agent_id=?) "
                "AND (?=0 OR drained=0) ORDER BY rowid LIMIT 128",
                (self.owner.channel.server_id,self.owner.channel.executor_id,self.after if after is None else after,
                 agent_id,agent_id,live_only)).fetchall()
            return [dict(row) for row in rows]

    def _watermark(self, scope):
        with self.owner.factory.unit_of_work(write=False) as uow:
            self.owner.verify(uow=uow)
            row = uow.connection.execute("SELECT committed_contiguous FROM execution_event_watermarks "
                "WHERE server_id=? AND executor_id=? AND session_id=? AND stream_epoch=?",
                tuple(scope[k] for k in ("server_id","executor_id","session_id","stream_epoch"))).fetchone()
            return row[0] if row else 0

    async def step(self, scope):
        async def publish(journal):
            after = await asyncio.to_thread(self._watermark,scope)
            cursor = EventCursor(scope["server_id"],scope["executor_id"],scope["session_id"],scope["stream_epoch"],after)
            # This ACK was committed in Nexus even if a previous Core ACK failed.
            await journal.acknowledge_events(cursor,after)
            iterator = journal.events(cursor)
            events, size = [], 0
            try:
                async for event in iterator:
                    value = asdict(event)
                    if value["operation_id"] is None:
                        value.pop("operation_id")
                    raw = canonical_json(value)
                    if len(raw)>64*1024:
                        raise CoreError("CAPACITY_EXCEEDED","embedded_event")
                    if value["sequence"] != after+len(events)+1:
                        raise CoreError("EVENT_GAP","embedded_event")
                    if size+len(raw)>768*1024:
                        break
                    events.append(value)
                    size += len(raw)
                    if len(events)==128:
                        break
            finally:
                await iterator.aclose()
            if not events:
                return False
            channel = self.owner.channel
            frame = {k:scope[k] for k in ("server_id","executor_id","binding_id","agent_id","session_id","stream_epoch")}
            frame.update(type="event.batch",protocol_major=1,contract_revision=R4_PREVIEW_REVISION,
                connection_id=channel.connection_id,connection_generation=channel.connection_generation,events=events)
            ack = await asyncio.to_thread(commit_execution_events,self.owner.factory,
                channel=channel,frame=frame,embedded_owner=self.owner,approvals=self.owner.deps.approvals)
            if ack is None or ack["sequence"]!=events[-1]["sequence"]:
                raise CoreError("EVENT_GAP","embedded_event_ack")
            await journal.acknowledge_events(cursor,ack["sequence"])
            return True
        return await self.owner.host.with_history(executor_id=scope["executor_id"],
            session_id=scope["session_id"],read=publish)

    async def pass_once(self, *, drain=False):
        rows = await asyncio.to_thread(self._page)
        self.after = rows[-1]["rowid"] if rows else 0
        for scope in rows:
            if drain:
                for _ in range(4096):
                    if not await self.step(scope):
                        break
                else:
                    raise CoreError("CAPACITY_EXCEEDED","embedded_event_recovery")
            else:
                await self.step(scope)
        return bool(rows)

    async def recover(self, *, agent_id=None, live_only=False):
        after = 0
        while True:
            rows = await asyncio.to_thread(self._page, after=after, agent_id=agent_id, live_only=live_only)
            if not rows:
                return
            for scope in rows:
                for _ in range(4096):
                    if not await self.step(scope):
                        break
                else:
                    raise CoreError("CAPACITY_EXCEEDED", "embedded_event_recovery")
            after = rows[-1]["rowid"]
