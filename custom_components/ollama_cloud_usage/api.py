from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

from .const import USAGE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class OllamaApiError(Exception):
    pass


class OllamaAuthError(OllamaApiError):
    pass


class OllamaParseError(OllamaApiError):
    pass


@dataclass
class ModelUsage:
    name: str
    request_count: int


@dataclass
class UsageWindow:
    label: str
    usage_usd: float
    period_type: str | None = None
    starting_at: str | None = None
    ending_at: str | None = None
    predicted_start: datetime | None = None
    predicted_end: datetime | None = None
    models: list[ModelUsage] = field(default_factory=list)

    @property
    def total_requests(self) -> int:
        return sum(m.request_count for m in self.models)


@dataclass
class OllamaUsageData:
    session: UsageWindow | None = None
    weekly: UsageWindow | None = None
    activity: UsageWindow | None = None

    @property
    def windows(self) -> list[UsageWindow]:
        return [w for w in (self.session, self.weekly, self.activity) if w is not None]


async def fetch_usage(session: aiohttp.ClientSession, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with session.get(
        USAGE_URL,
        headers=headers,
        allow_redirects=False,
        raise_for_status=False,
    ) as resp:
        if resp.status in (401, 403):
            raise OllamaAuthError(
                f"API key rejected by ollama.com (HTTP {resp.status})"
            )
        if resp.status != 200:
            body = await resp.text()
            raise OllamaApiError(
                f"Unexpected HTTP {resp.status} from ollama.com: {body[:200]}"
            )
        try:
            return await resp.json(content_type=None)
        except aiohttp.ContentTypeError as err:
            raise OllamaParseError(
                f"Non-JSON response from {USAGE_URL}: {err}"
            ) from err


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as err:
            raise OllamaParseError(f"Expected number, got {value!r}") from err
    raise OllamaParseError(f"Expected number, got {type(value).__name__}")


def _coerce_int(value: object, *, field_name: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise OllamaParseError(f"Expected integer for {field_name}, got {value!r}")


def _parse_models(items: object) -> list[ModelUsage]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise OllamaParseError(f"Expected list of models, got {type(items).__name__}")
    models: list[ModelUsage] = []
    for item in items:
        if not isinstance(item, dict):
            raise OllamaParseError(f"Expected model object, got {type(item).__name__}")
        name = item.get("name")
        if not isinstance(name, str):
            raise OllamaParseError(f"Expected model.name string, got {name!r}")
        count = _coerce_int(item.get("request_count", 0), field_name="request_count")
        models.append(ModelUsage(name=name, request_count=count))
    return models


def _parse_window(
    payload: dict | None,
    *,
    label: str,
    default_period_type: str | None = None,
) -> UsageWindow | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected object for {label}, got {type(payload).__name__}"
        )
    usage = _coerce_float(payload.get("usage", 0))
    period = payload.get("period") or {}
    if not isinstance(period, dict):
        raise OllamaParseError(
            f"Expected period object for {label}, got {type(period).__name__}"
        )
    return UsageWindow(
        label=label,
        usage_usd=usage,
        period_type=period.get("type", default_period_type),
        starting_at=period.get("starting_at"),
        ending_at=period.get("ending_at"),
        models=_parse_models(payload.get("models")),
    )


def parse_usage(payload: dict) -> OllamaUsageData:
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected JSON object from /api/usage, got {type(payload).__name__}"
        )

    limits = payload.get("limits") or {}
    if not isinstance(limits, dict):
        raise OllamaParseError(f"Expected limits object, got {type(limits).__name__}")

    session = _parse_window(limits.get("session"), label="session")
    weekly = _parse_window(limits.get("weekly"), label="weekly")
    activity = _parse_window(payload.get("activity"), label="last_4_weeks")

    if session is None and weekly is None and activity is None:
        raise OllamaParseError(
            "API response contained no usage windows (limits or activity missing)"
        )

    return OllamaUsageData(session=session, weekly=weekly, activity=activity)


async def fetch_and_parse(
    session: aiohttp.ClientSession, api_key: str
) -> OllamaUsageData:
    payload = await fetch_usage(session, api_key)
    return parse_usage(payload)
