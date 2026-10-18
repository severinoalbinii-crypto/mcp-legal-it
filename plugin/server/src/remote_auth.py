"""Fail-closed GitHub OAuth for remote (HTTP/SSE) MCP Legal IT.

STDIO continues to use the local host's security context.
Remote deployments must explicitly configure a public HTTPS URL,
GitHub OAuth app credentials, and an authorized GitHub username.
No secrets are hardcoded or printed by this module.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def _required_environment() -> dict[str, str]:
    names = (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "MCP_PUBLIC_BASE_URL",
        "MCP_ALLOWED_GITHUB_USERS",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Remote MCP authentication is required. Missing environment: "
            + ", ".join(missing)
        )
    return values


def configure_remote_auth():
    """Return (OAuth provider, middlewares); refuse unprotected HTTP/SSE startup."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        return None, []
    if transport not in ("http", "sse"):
        raise ValueError(f"Unsupported MCP_TRANSPORT: {transport!r}")

    values = _required_environment()
    public_url = values["MCP_PUBLIC_BASE_URL"].rstrip("/")
    parsed = urlsplit(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError("MCP_PUBLIC_BASE_URL must be a root HTTPS URL.")

    allowed = frozenset(
        user.strip().casefold()
        for user in values["MCP_ALLOWED_GITHUB_USERS"].split(",")
        if user.strip()
    )
    if not allowed:
        raise RuntimeError("MCP_ALLOWED_GITHUB_USERS must name at least one account.")

    from fastmcp.server.auth.providers.github import GitHubProvider
    from fastmcp.server.middleware import Middleware, MiddlewareContext
    from fastmcp.server.dependencies import get_access_token
    from fastmcp.exceptions import ToolError, ResourceError, PromptError, McpError

    provider = GitHubProvider(
        client_id=values["GITHUB_CLIENT_ID"],
        client_secret=values["GITHUB_CLIENT_SECRET"],
        base_url=public_url,
        redirect_path="/auth/callback",
    )

    class AllowedGitHubUsers(Middleware):
        """Restrict every MCP request to the configured GitHub accounts."""

        async def on_request(self, context: MiddlewareContext, call_next):
            if not self._authorized():
                raise McpError(code=-32000, message="GitHub account is not authorized")
            return await call_next(context)

        @staticmethod
        def _authorized():
            token = get_access_token()
            login = token.claims.get("login") if token is not None else None
            return isinstance(login, str) and login.casefold() in allowed

        async def on_call_tool(self, context: MiddlewareContext, call_next):
            if not self._authorized():
                raise ToolError("GitHub account is not authorized")
            return await call_next(context)

        async def on_read_resource(self, context: MiddlewareContext, call_next):
            if not self._authorized():
                raise ResourceError("GitHub account is not authorized")
            return await call_next(context)

        async def on_get_prompt(self, context: MiddlewareContext, call_next):
            if not self._authorized():
                raise PromptError("GitHub account is not authorized")
            return await call_next(context)

    return provider, [AllowedGitHubUsers()]
