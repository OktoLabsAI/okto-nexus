"""Retained, independent historical checkpoint work outside agent readiness.

The cursor is a scheduling hint only. Missing checkpoints remain canonical SQL
obligations; wrapping or restarting the worker cannot waive a release proof.
"""
import asyncio
import logging
import time

from .embedded_retirement import EmbeddedRetirement


class EmbeddedRetirementMaintenance:
    def __init__(self, agents):
        self.agents = agents
        self.tasks = {}
        self.after = {}
        self.retry_at = {}
        self.errors = {}

    def tick(self, subjects):
        owner = self.agents.owner
        for agent_id, task in tuple(self.tasks.items()):
            if task.done():
                task.result()
                del self.tasks[agent_id]
        if owner._stopping.is_set():
            return
        now = time.monotonic()
        for agent_id in subjects:
            if (agent_id in self.agents.blocked or agent_id in self.tasks
                    or now < self.retry_at.get(agent_id, 0)):
                continue
            self.tasks[agent_id] = asyncio.create_task(self._run(agent_id),
                name='embedded-retirement-' + agent_id)

    async def _run(self, agent_id):
        owner = self.agents.owner
        try:
            rows = await asyncio.to_thread(EmbeddedRetirement(owner).pending, agent_id,
                after=self.after.get(agent_id, 0), limit=1)
            if not rows:
                self.after.pop(agent_id, None)
                self.retry_at[agent_id] = time.monotonic() + 1
                return
            row = rows[0]
            try:
                if owner._stopping.is_set() or agent_id in self.agents.blocked:
                    return
                await self.agents._retire_session(agent_id, row)
            finally:
                # A busy or broken historical session must not starve the next
                # one. Uncommitted work is revisited on the next bounded pass.
                self.after[agent_id] = row['retirement_rowid']
            self.errors.pop(agent_id, None)
            self.retry_at.pop(agent_id, None)
        except Exception as error:
            # Nothing here grants authority or frees uncertain capacity. Exact
            # proof and owner checks remain in release_session/commit. Keep this
            # obligation pending without revoking healthy sibling executions.
            code = str(getattr(error, 'code', type(error).__name__))
            if self.errors.get(agent_id) != code:
                logging.getLogger(__name__).warning(
                    'Historical runtime checkpoint remains pending: agent=%s code=%s', agent_id, code)
            self.errors[agent_id] = code
            self.retry_at[agent_id] = time.monotonic() + 2

    async def close(self):
        # Never cancel a native/history producer and mistake cancellation for
        # resource release. The enclosing owner has already fenced new ticks.
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks.values()))
