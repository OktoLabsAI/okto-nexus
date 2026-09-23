"""Owner-only journal maintenance; no filesystem work in a database UoW."""
from ..errors import ErrorCode, OktoNexusError


class RuntimeMaintenanceService:
    def __init__(self, *, access, dispatcher):
        self.access, self.dispatcher = access, dispatcher

    def journal(self, context, *, compact=False):
        self.access.authorize(context, action="admin")
        owner = self.dispatcher
        with owner.cf.unit_of_work(write=False) as uow:
            valid = owner.repo.owns(uow, owner_id=owner.owner_id, epoch=owner.epoch, now=owner.clock.now_iso())
        if not valid or owner._quiescing.is_set() or owner._stop.is_set():
            raise OktoNexusError(ErrorCode.CONFLICT, "Journal maintenance requires the active serve owner.", {})
        try:
            result = owner.event_ingress.compact() if compact else owner.event_ingress.journal.diagnostics()
        except OSError:
            raise OktoNexusError(ErrorCode.CONFLICT, "Journal maintenance failed; preserve the store and inspect its recovery state.", {}) from None
        if compact:
            owner.wake()
        return result
