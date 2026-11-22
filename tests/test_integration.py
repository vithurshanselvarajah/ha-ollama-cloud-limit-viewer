from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from unittest.mock import patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    OllamaApiError,
    OllamaRateLimitError,
)
from custom_components.ollama_cloud_usage.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
API_KEY = "abcdef0123456789abcdef0123456789.0123456789abcdefghijklmnopqrstuvwxyzABCD"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class _FakeResponse:
    def __init__(self, status: int, payload: object, headers: dict[str, str]) -> None:
        self.status = status
        self._payload = payload
        self.headers = headers

    async def json(self, content_type: str | None = None) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self) -> str:
        return str(self._payload)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeSession:
    def __init__(
        self,
        routes: dict[str, list[_FakeResponse]],
        usage_by_scope: dict[str, list[_FakeResponse]] | None = None,
    ) -> None:
        self.routes = routes
        self.usage_by_scope = usage_by_scope or {}
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append(url)
        if url.endswith("/balance"):
            responses = self.routes["balance"]
            return responses.pop(0) if len(responses) > 1 else responses[0]
        params = kwargs.get("params") or {}
        scope = params.get("scope", "self")
        scoped = self.usage_by_scope.get(scope)
        if scoped is not None:
            return scoped.pop(0) if len(scoped) > 1 else scoped[0]
        responses = self.routes["usage"]
        return responses.pop(0) if len(responses) > 1 else responses[0]


async def _setup(
    hass: HomeAssistant, session: _FakeSession, scope: str = "self"
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={
            "account_name": "Main",
            "api_key": API_KEY,
            "scan_interval": 300,
            "scope": scope,
        },
    )
    with patch(
        "custom_components.ollama_cloud_usage.coordinator.async_get_clientsession",
        return_value=session,
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id == f"{entry.entry_id}_{key}":
            return hass.states.get(registry_entry.entity_id).state
    return None


def _usage(payload: dict) -> _FakeResponse:
    return _FakeResponse(200, payload, {})


async def test_end_to_end_legacy_plan(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_usage(_fixture("api_balance_legacy.json"))],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.LOADED
    assert len(session.calls) == 3
    assert _state(hass, entry, "weekly_requests") == "6236"
    assert _state(hass, entry, "session_remaining") == "73.6"
    assert _state(hass, entry, "weekly_remaining") == "70.32"
    assert _state(hass, entry, "last_4_weeks_requests") == "26589"
    assert _state(hass, entry, "purchased_balance") == "0.0"


async def test_end_to_end_auth_failure(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(401, {"error": "invalid credentials"}, {})],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_end_to_end_rate_limited(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [
                _FakeResponse(429, {"error": "rate limited"}, {"Retry-After": "42"})
            ],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_end_to_end_non_json_response(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(200, aiohttp.ContentTypeError(None, None), {})],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state.recoverable is True


async def test_rate_limit_error_carries_retry_after():
    error = OllamaRateLimitError("slow down", retry_after=42)

    assert error.retry_after == 42
    assert isinstance(error, OllamaApiError)


async def test_balance_parsing_of_credit_plan(hass: HomeAssistant):
    credit = {
        "included": {
            "balance_usd": 72.5,
            "allowance_usd": 100,
            "period": {
                "from": "2026-09-15T09:30:00Z",
                "until": "2026-10-15T09:30:00Z",
            },
        },
        "purchased": {"balance_usd": 25},
    }
    session = _FakeSession(
        {
            "balance": [_usage(credit)],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        }
    )

    entry = await _setup(hass, session)

    assert _state(hass, entry, "included_balance") == "72.5"
    assert _state(hass, entry, "included_allowance") == "100.0"
    assert _state(hass, entry, "purchased_balance") == "25.0"
    assert _state(hass, entry, "session_requests") is not None
    assert _state(hass, entry, "weekly_requests") is None


async def test_weekly_window_matches_api_range(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_usage(_fixture("api_balance_legacy.json"))],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        }
    )

    entry = await _setup(hass, session)

    weekly = _state(hass, entry, "weekly_requests")
    seven_day_total = _fixture("api_usage_30d.json")["totals"]["request_count"]

    assert int(weekly) <= seven_day_total
    assert int(weekly) > 0


async def test_session_period_end_is_reset_time(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_usage(_fixture("api_balance_legacy.json"))],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        }
    )

    entry = await _setup(hass, session)

    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id == f"{entry.entry_id}_session_period_end":
            state = hass.states.get(registry_entry.entity_id)
            assert datetime.fromisoformat(state.state) == datetime(
                2026, 11, 23, tzinfo=UTC
            )
            return
    raise AssertionError("session_period_end entity not found")


async def test_team_scope_falls_back_to_self(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_usage(_fixture("api_balance_legacy.json"))],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        },
        usage_by_scope={
            "team": [
                _FakeResponse(403, {"error": "only team admins can use scope=team"}, {})
            ]
        },
    )

    entry = await _setup(hass, session, scope="team")

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data.scope == "self"


async def test_team_scope_is_used_when_allowed(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_usage(_fixture("api_balance_legacy.json"))],
            "usage": [
                _usage(_fixture("api_usage_30d.json")),
                _usage(_fixture("api_usage_24h.json")),
            ],
        }
    )

    entry = await _setup(hass, session, scope="team")

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data.scope == "team"


async def test_end_to_end_server_error(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(500, {"error": "boom"}, {})],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_end_to_end_non_object_payload(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(200, ["not", "an", "object"], {})],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_end_to_end_retry_after_header_is_used(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [
                _FakeResponse(429, {"error": "slow down"}, {"Retry-After": "90"})
            ],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_end_to_end_missing_retry_after_header(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(429, {"error": "slow down"}, {})],
            "usage": [],
        }
    )

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_end_to_end_connection_error(hass: HomeAssistant):
    session = _FakeSession(
        {
            "balance": [_FakeResponse(200, {"error": "boom"}, {})],
            "usage": [],
        }
    )
    session.get = lambda url, **kwargs: _FakeResponse(200, {"error": "boom"}, {})

    entry = await _setup(hass, session)

    assert entry.state is ConfigEntryState.SETUP_RETRY
