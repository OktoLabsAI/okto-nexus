"""Bind-aware MCP Host/Origin validation, independent of agent authentication."""
import socket


def mcp_transport_security(host: str = "127.0.0.1", port: int | None = None):
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = {"localhost", "127.0.0.1", "::1"}
    if host in ("0.0.0.0", "::"):
        # Enumerate this server, never trust request Host/forwarded headers.
        for name in {socket.gethostname(), socket.getfqdn()}:
            hosts.add(name.lower())
            try:
                hosts.update(item[4][0] for item in socket.getaddrinfo(name, None))
            except OSError:
                pass
    else:
        hosts.add(host.strip("[]").lower())
    authorities = []
    for name in sorted(hosts - {"0.0.0.0", "::", ""}):
        name = f"[{name}]" if ":" in name else name
        authorities.append(f"{name}:{port}" if port is not None else f"{name}:*")
        if port is None or port in (80, 443):
            authorities.append(name)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=authorities,
        allowed_origins=[f"{scheme}://{name}" for scheme in ("http", "https") for name in authorities],
    )
