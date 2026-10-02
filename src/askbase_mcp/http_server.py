"""Hosted MCP server (Cloud Run): streamable HTTP at /mcp, health at /health.

Stateless: every request carries the caller's own AskBase API key
(X-API-Key, or Authorization: Bearer). Nothing is shared between requests,
so one caller can never act with another caller's key. Requests to /mcp
without a key are refused with 401 before reaching MCP.
"""

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from askbase_mcp.config import get_settings
from askbase_mcp.tools import api_key_from_headers, build_server

settings = get_settings()
server = build_server(settings, allow_env_key=False)


@server.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "server": settings.server_name, "version": settings.server_version})


class RequireApiKey:
    """ASGI middleware: 401 on /mcp without an API key."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if not api_key_from_headers(headers):
                response = JSONResponse(
                    {"error": "AskBase API key required: send it as the X-API-Key header."},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="askbase"'},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


# A public server reached through Cloud Run / a custom domain: the
# localhost-only DNS-rebinding guard doesn't apply (no browser session or
# ambient credentials to protect; every request carries its own key).
_app = server.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
app = RequireApiKey(_app)
