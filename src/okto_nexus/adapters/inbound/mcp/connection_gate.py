"""Per-call MCP admission, including already-open authenticated stdio sessions."""
import functools
import inspect

from ....application.connection_policy import require_method
from ....errors import OktoNexusError
from ..http.identity_ctx import get_authenticated_agent


class ConnectionGateServer:
    def __init__(self, inner, deps):
        self.inner, self.deps = inner, deps

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def check(self):
        actor = get_authenticated_agent()
        if actor:
            with self.deps.connection_factory.unit_of_work(write=False) as uow:
                require_method(uow, actor.agent_id, "mcp")

    def tool(self, *args, **kwargs):
        register = self.inner.tool(*args, **kwargs)

        def decorate(fn):
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def wrapped(*a, **kw):
                    try:
                        self.check()
                    except OktoNexusError as exc:
                        return {"ok": False, "error": exc.to_error_dict()}
                    return await fn(*a, **kw)
            else:
                @functools.wraps(fn)
                def wrapped(*a, **kw):
                    try:
                        self.check()
                    except OktoNexusError as exc:
                        return {"ok": False, "error": exc.to_error_dict()}
                    return fn(*a, **kw)
            register(wrapped)
            return fn
        return decorate
