"""Coordinated shutdown without releasing ownership over undrained resources."""
import logging
import time


def shutdown_runtime(dispatcher, supervisor, *, timeout=10):
    deadline = time.monotonic() + max(0, timeout)
    dispatcher.quiesce()
    supervisor.begin_shutdown(wake=dispatcher.wake)
    if dispatcher._stop.is_set():
        # Compatibility for standalone owners explicitly closed by their caller.
        # Production lifespan keeps the coordinator alive through this method.
        drained = supervisor.wait_drained(max(0, deadline - time.monotonic()))
        if drained and supervisor.event_ingress:
            while supervisor.event_ingress.recover():
                if time.monotonic() >= deadline:
                    drained = False
                    break
            if drained:
                supervisor.event_ingress.close()
                dispatcher._shutdown_finished.set()
    else:
        dispatcher.event_ingress = supervisor.event_ingress
        drained = dispatcher.finish_shutdown_when(supervisor.drained,
            timeout=max(0, deadline - time.monotonic()))
    if not drained:
        logging.getLogger(__name__).warning(
            "Runtime shutdown remains pending; owner lease and journal retained until activity drains.")
    return {"state": "drained" if drained else "pending", "owner_released": drained}
