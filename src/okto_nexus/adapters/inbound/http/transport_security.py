"""One transport policy for the dashboard, APIs, MCP and WebSocket links."""
from starlette.responses import JSONResponse


def transport_allowed(config, scheme):
    # Trust only the ASGI scheme set by the server/trusted proxy middleware.
    # Never interpret client-supplied Forwarded headers here.
    return scheme in ("https", "wss") or (
        config.transport_security == "http_https" and scheme in ("http", "ws"))


class TransportSecurityMiddleware:
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and not transport_allowed(
                self.config, scope.get("scheme")):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4406,
                            "reason": "TLS_REQUIRED: Use WSS."})
            else:
                await JSONResponse(
                    {"ok": False, "error": {"code": "TLS_REQUIRED",
                     "message": "This Nexus server requires HTTPS and WSS."}},
                    status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
