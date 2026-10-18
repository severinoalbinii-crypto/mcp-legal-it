"""Security fail-closed tests. No credentials or network required."""
import pytest

from src.remote_auth import configure_remote_auth


def test_stdio_keeps_local_behavior(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)
    assert configure_remote_auth() == (None, [])


def test_http_without_credentials_refuses_to_start(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    for key in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "MCP_PUBLIC_BASE_URL", "MCP_ALLOWED_GITHUB_USERS"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="Remote MCP authentication is required"):
        configure_remote_auth()


def test_non_https_public_url_refused(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "example-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "example-placeholder")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "http://example.invalid")
    monkeypatch.setenv("MCP_ALLOWED_GITHUB_USERS", "test")
    with pytest.raises(RuntimeError, match="root HTTPS URL"):
        configure_remote_auth()
