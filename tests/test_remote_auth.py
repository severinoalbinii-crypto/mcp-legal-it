"""Fail-closed GitHub OAuth tests; no real credentials or external requests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.remote_auth import configure_remote_auth


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "unit-test-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "unit-test-placeholder-not-real")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://mcp.example.invalid")
    monkeypatch.setenv("MCP_ALLOWED_GITHUB_USERS", "severinoalbinii-crypto")


def test_stdio_keeps_local_behavior(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)
    assert configure_remote_auth() == (None, [])


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_remote_without_credentials_refuses_to_start(monkeypatch, transport):
    monkeypatch.setenv("MCP_TRANSPORT", transport)
    for key in (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "MCP_PUBLIC_BASE_URL",
        "MCP_ALLOWED_GITHUB_USERS",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="Remote MCP authentication is required"):
        configure_remote_auth()


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://mcp.example.invalid",
        "https://mcp.example.invalid/mcp",
        "https://mcp.example.invalid?admin=1",
        "https://user:pass@mcp.example.invalid",
        "localhost:8000",
    ],
)
def test_invalid_public_url_refused(oauth_env, monkeypatch, bad_url):
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", bad_url)
    with pytest.raises(RuntimeError, match="root HTTPS URL"):
        configure_remote_auth()


@pytest.mark.parametrize(
    ("login", "accepted"),
    [
        ("severinoalbinii-crypto", True),
        ("SEVERINOALBINII-CRYPTO", True),
        ("someone-else", False),
        ("severinoalbinii-crypto-2", False),
        ("", False),
        (None, False),
    ],
)
def test_account_allowlist_applies_to_requests(oauth_env, monkeypatch, login, accepted):
    """Only exact configured GitHub login reaches MCP request handlers."""
    import fastmcp.server.auth.providers.github as github
    import fastmcp.server.dependencies as dependencies

    token = None if login is None else SimpleNamespace(claims={"login": login})
    monkeypatch.setattr(dependencies, "get_access_token", lambda: token)

    with patch.object(github, "GitHubProvider") as provider_type:
        provider, middlewares = configure_remote_auth()

    provider_type.assert_called_once()
    assert provider is provider_type.return_value
    assert len(middlewares) == 1
    middleware = middlewares[0]

    async def allowed_next(_):
        return "permitted"

    if accepted:
        assert asyncio.run(middleware.on_request(None, allowed_next)) == "permitted"
    else:
        with pytest.raises(Exception, match="not authorized"):
            asyncio.run(middleware.on_request(None, allowed_next))


@pytest.mark.parametrize("transport", ["invalid", "tcp", "ws"])
def test_unsupported_transport_refuses(monkeypatch, transport):
    monkeypatch.setenv("MCP_TRANSPORT", transport)
    with pytest.raises(ValueError, match="Unsupported MCP_TRANSPORT"):
        configure_remote_auth()
