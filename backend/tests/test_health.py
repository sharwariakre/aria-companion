"""
Unit tests for the ngrok health check.

httpx calls are fully mocked — no network access required.
"""

import pytest
import services.health as health_module


def _make_mock_client(json_payload=None, raise_exc=None):
    """Return a context-manager-compatible AsyncMock for httpx.AsyncClient."""
    from unittest.mock import AsyncMock, MagicMock

    mock_resp = MagicMock()
    mock_resp.json.return_value = json_payload or {}

    mock_client = AsyncMock()
    if raise_exc:
        mock_client.get = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=mock_resp)

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_was_up():
    """Reset module-level state so tests don't leak into each other."""
    health_module._was_up = True
    yield
    health_module._was_up = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_returns_true_when_tunnels_present(monkeypatch):
    payload = {"tunnels": [{"name": "cmd", "public_url": "https://example.ngrok.io"}]}
    monkeypatch.setattr("services.health.httpx.AsyncClient", lambda **kw: _make_mock_client(payload))

    result = await health_module.check_ngrok_health()
    assert result is True


async def test_returns_false_when_tunnels_empty(monkeypatch):
    monkeypatch.setattr("services.health.httpx.AsyncClient", lambda **kw: _make_mock_client({"tunnels": []}))

    result = await health_module.check_ngrok_health()
    assert result is False


async def test_returns_false_on_connection_error(monkeypatch):
    monkeypatch.setattr(
        "services.health.httpx.AsyncClient",
        lambda **kw: _make_mock_client(raise_exc=Exception("Connection refused")),
    )

    result = await health_module.check_ngrok_health()
    assert result is False


async def test_gauge_set_to_1_when_up(monkeypatch):
    payload = {"tunnels": [{"name": "cmd"}]}
    monkeypatch.setattr("services.health.httpx.AsyncClient", lambda **kw: _make_mock_client(payload))

    values = []
    original_set = health_module.NGROK_UP.set

    def capture_set(v):
        values.append(v)
        original_set(v)

    monkeypatch.setattr(health_module.NGROK_UP, "set", capture_set)

    await health_module.check_ngrok_health()
    assert values[-1] == 1


async def test_gauge_set_to_0_when_down(monkeypatch):
    monkeypatch.setattr("services.health.httpx.AsyncClient", lambda **kw: _make_mock_client({"tunnels": []}))

    values = []
    original_set = health_module.NGROK_UP.set

    def capture_set(v):
        values.append(v)
        original_set(v)

    monkeypatch.setattr(health_module.NGROK_UP, "set", capture_set)

    await health_module.check_ngrok_health()
    assert values[-1] == 0
