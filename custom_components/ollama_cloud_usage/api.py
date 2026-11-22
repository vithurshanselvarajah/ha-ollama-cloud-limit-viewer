from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import aiohttp

from .const import (
    BALANCE_URL,
    SCOPE_SELF,
    SCOPE_TEAM,
    USAGE_RANGE_7D,
    USAGE_RANGE_24H,
    USAGE_RANGE_30D,
    USAGE_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

WEEKLY_WINDOW = timedelta(days=7)
ACTIVITY_WINDOW = timedelta(days=28)
SESSION_WINDOW = timedelta(hours=7)


class OllamaApiError(Exception):
    """Base error for every failure raised by the Ollama cloud API client."""


class OllamaAuthError(OllamaApiError):
    """The API key was rejected or the account may not read this data."""


class OllamaScopeError(OllamaAuthError):
    """The requested scope is not available to this API key."""


class OllamaParseError(OllamaApiError):
    """The API answered with something that does not match the documented shape."""


class OllamaRateLimitError(OllamaApiError):
    """The API rate limit was hit."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class ModelUsage:
    name: str
    request_count: int
    usage_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class UsageWindow:
    label: str
    request_count: int = 0
    usage_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    remaining_percent: float | None = None
    period_type: str | None = None
    starting_at: datetime | None = None
    ending_at: datetime | None = None
    resets_at: datetime | None = None
    models: list[ModelUsage] = field(default_factory=list)
    remainder_request_count: int = 0
    remainder_usage_usd: float | None = None
    remainder_input_tokens: int | None = None
    remainder_cached_input_tokens: int | None = None
    remainder_output_tokens: int | None = None

    @property
    def total_requests(self) -> int:
        return sum(model.request_count for model in self.models)

    @property
    def cache_hit_ratio(self) -> float | None:
        """Share of input tokens that were served from the prompt cache, in percent."""
        if not self.input_tokens or self.cached_input_tokens is None:
            return None
        return self.cached_input_tokens / self.input_tokens * 100

    @property
    def other_model_requests(self) -> int:
        """Requests attributed to models outside the reported group list."""
        return self.remainder_request_count


@dataclass
class UsageBucket:
    starting_at: datetime
    ending_at: datetime
    request_count: int
    usage_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    partial: bool = False
    models: list[ModelUsage] = field(default_factory=list)
    remainder_request_count: int = 0
    remainder_usage_usd: float | None = None
    remainder_input_tokens: int | None = None
    remainder_cached_input_tokens: int | None = None
    remainder_output_tokens: int | None = None


@dataclass
class UsageSummary:
    request_count: int = 0
    usage_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    models: list[ModelUsage] = field(default_factory=list)
    remainder_request_count: int = 0
    remainder_usage_usd: float | None = None
    remainder_input_tokens: int | None = None
    remainder_cached_input_tokens: int | None = None
    remainder_output_tokens: int | None = None


@dataclass
class UsageReport:
    range: str
    granularity: str
    starting_at: datetime
    ending_at: datetime
    totals: UsageSummary
    buckets: list[UsageBucket] = field(default_factory=list)


@dataclass
class BalanceReport:
    included_balance_usd: float | None = None
    included_allowance_usd: float | None = None
    included_period_start: datetime | None = None
    included_period_end: datetime | None = None
    purchased_balance_usd: float | None = None
    session_remaining_percent: float | None = None
    session_resets_at: datetime | None = None
    weekly_remaining_percent: float | None = None
    weekly_resets_at: datetime | None = None

    @property
    def is_legacy_plan(self) -> bool:
        return (
            self.session_remaining_percent is not None
            or self.weekly_remaining_percent is not None
        )

    @property
    def is_credit_plan(self) -> bool:
        return self.included_balance_usd is not None


@dataclass
class OllamaUsageData:
    session: UsageWindow | None = None
    weekly: UsageWindow | None = None
    activity: UsageWindow | None = None
    balance: BalanceReport | None = None
    scope: str = SCOPE_SELF

    @property
    def windows(self) -> list[UsageWindow]:
        return [w for w in (self.session, self.weekly, self.activity) if w is not None]


def _retry_after_seconds(resp: aiohttp.ClientResponse) -> int | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _request_json(
    session: aiohttp.ClientSession,
    url: str,
    api_key: str,
    params: dict[str, str] | None = None,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with session.get(
        url,
        headers=headers,
        params=params,
        allow_redirects=False,
        raise_for_status=False,
    ) as resp:
        if resp.status == 403:
            raise OllamaScopeError(
                "Access to the requested data was refused by ollama.com (HTTP 403)"
            )
        if resp.status == 401:
            raise OllamaAuthError("API key rejected by ollama.com (HTTP 401)")
        if resp.status == 429:
            raise OllamaRateLimitError(
                "Rate limited by ollama.com (HTTP 429)",
                retry_after=_retry_after_seconds(resp),
            )
        if resp.status != 200:
            body = await resp.text()
            raise OllamaApiError(
                f"Unexpected HTTP {resp.status} from ollama.com: {body[:200]}"
            )
        try:
            payload = await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise OllamaParseError(f"Non-JSON response from {url}: {err}") from err
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected JSON object from {url}, got {type(payload).__name__}"
        )
    return payload


async def fetch_usage(
    session: aiohttp.ClientSession,
    api_key: str,
    usage_range: str = USAGE_RANGE_7D,
    scope: str = SCOPE_SELF,
) -> dict:
    return await _request_json(
        session,
        USAGE_URL,
        api_key,
        params={"range": usage_range, "group_by": "model", "scope": scope},
    )


async def fetch_balance(session: aiohttp.ClientSession, api_key: str) -> dict:
    return await _request_json(session, BALANCE_URL, api_key)


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OllamaParseError(
            f"Expected timestamp string for {field_name}, got {value!r}"
        )
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as err:
        raise OllamaParseError(
            f"Expected ISO 8601 timestamp for {field_name}, got {value!r}"
        ) from err
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_models(items: object) -> list[ModelUsage]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise OllamaParseError(f"Expected list of models, got {type(items).__name__}")
    models: list[ModelUsage] = []
    for item in items:
        if not isinstance(item, dict):
            raise OllamaParseError(f"Expected model object, got {type(item).__name__}")
        name = item.get("model") or item.get("name")
        if not isinstance(name, str) or not name:
            raise OllamaParseError(f"Expected model name string, got {name!r}")
        count = _coerce_int(item.get("request_count", 0))
        if count is None:
            raise OllamaParseError(
                f"Expected integer request_count for model {name!r}, "
                f"got {item.get('request_count')!r}"
            )
        models.append(
            ModelUsage(
                name=name,
                request_count=count,
                usage_usd=_coerce_float(item.get("usage_usd")),
                input_tokens=_coerce_int(item.get("input_tokens")),
                cached_input_tokens=_coerce_int(item.get("cached_input_tokens")),
                output_tokens=_coerce_int(item.get("output_tokens")),
            )
        )
    return models


def _parse_summary(payload: dict) -> UsageSummary:
    request_count = _coerce_int(payload.get("request_count", 0))
    if request_count is None:
        raise OllamaParseError(
            f"Expected integer request_count, got {payload.get('request_count')!r}"
        )
    remainder = payload.get("remainder")
    if remainder is not None and not isinstance(remainder, dict):
        raise OllamaParseError(
            f"Expected remainder object, got {type(remainder).__name__}"
        )
    remainder = remainder or {}
    return UsageSummary(
        request_count=request_count,
        usage_usd=_coerce_float(payload.get("usage_usd")),
        input_tokens=_coerce_int(payload.get("input_tokens")),
        cached_input_tokens=_coerce_int(payload.get("cached_input_tokens")),
        output_tokens=_coerce_int(payload.get("output_tokens")),
        models=_parse_models(payload.get("groups")),
        remainder_request_count=_coerce_int(remainder.get("request_count", 0)) or 0,
        remainder_usage_usd=_coerce_float(remainder.get("usage_usd")),
        remainder_input_tokens=_coerce_int(remainder.get("input_tokens")),
        remainder_cached_input_tokens=_coerce_int(remainder.get("cached_input_tokens")),
        remainder_output_tokens=_coerce_int(remainder.get("output_tokens")),
    )


def _parse_buckets(payload: dict) -> list[UsageBucket]:
    raw_buckets = payload.get("buckets")
    if raw_buckets is None:
        return []
    if not isinstance(raw_buckets, list):
        raise OllamaParseError(
            f"Expected list of buckets, got {type(raw_buckets).__name__}"
        )
    buckets: list[UsageBucket] = []
    for item in raw_buckets:
        if not isinstance(item, dict):
            raise OllamaParseError(f"Expected bucket object, got {type(item).__name__}")
        summary = _parse_summary(item)
        buckets.append(
            UsageBucket(
                starting_at=_parse_timestamp(
                    item.get("from"), field_name="bucket.from"
                ),
                ending_at=_parse_timestamp(
                    item.get("until"), field_name="bucket.until"
                ),
                request_count=summary.request_count,
                usage_usd=summary.usage_usd,
                input_tokens=summary.input_tokens,
                cached_input_tokens=summary.cached_input_tokens,
                output_tokens=summary.output_tokens,
                partial=bool(item.get("partial", False)),
                models=summary.models,
                remainder_request_count=summary.remainder_request_count,
                remainder_usage_usd=summary.remainder_usage_usd,
                remainder_input_tokens=summary.remainder_input_tokens,
                remainder_cached_input_tokens=summary.remainder_cached_input_tokens,
                remainder_output_tokens=summary.remainder_output_tokens,
            )
        )
    return buckets


def parse_usage(payload: dict) -> UsageReport:
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected JSON object from /api/usage, got {type(payload).__name__}"
        )

    totals_payload = payload.get("totals")
    if not isinstance(totals_payload, dict):
        raise OllamaParseError(
            f"Expected totals object, got {type(totals_payload).__name__}"
        )

    granularity = payload.get("granularity")
    if granularity not in ("hour", "day"):
        raise OllamaParseError(f"Expected granularity hour or day, got {granularity!r}")

    return UsageReport(
        range=str(payload.get("range", "")),
        granularity=granularity,
        starting_at=_parse_timestamp(payload.get("from"), field_name="from"),
        ending_at=_parse_timestamp(payload.get("until"), field_name="until"),
        totals=_parse_summary(totals_payload),
        buckets=_parse_buckets(payload),
    )


def _parse_legacy_limit(
    payload: object, *, field_name: str
) -> tuple[float, datetime] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected object for {field_name}, got {type(payload).__name__}"
        )
    percent = _coerce_float(payload.get("remaining_percent"))
    if percent is None:
        raise OllamaParseError(
            f"Expected remaining_percent for {field_name}, "
            f"got {payload.get('remaining_percent')!r}"
        )
    resets_at = _parse_timestamp(
        payload.get("resets_at"), field_name=f"{field_name}.resets_at"
    )
    return percent, resets_at


def parse_balance(payload: dict) -> BalanceReport:
    if not isinstance(payload, dict):
        raise OllamaParseError(
            f"Expected JSON object from /api/balance, got {type(payload).__name__}"
        )

    included = payload.get("included")
    if not isinstance(included, dict):
        raise OllamaParseError(
            f"Expected included object, got {type(included).__name__}"
        )

    purchased = payload.get("purchased")
    if purchased is not None and not isinstance(purchased, dict):
        raise OllamaParseError(
            f"Expected purchased object, got {type(purchased).__name__}"
        )

    report = BalanceReport()

    if purchased is not None:
        report.purchased_balance_usd = _coerce_float(purchased.get("balance_usd"))

    included_balance = _coerce_float(included.get("balance_usd"))
    if included_balance is not None:
        report.included_balance_usd = included_balance
        report.included_allowance_usd = _coerce_float(included.get("allowance_usd"))
        period = included.get("period")
        if isinstance(period, dict):
            if period.get("from") is not None:
                report.included_period_start = _parse_timestamp(
                    period.get("from"), field_name="included.period.from"
                )
            if period.get("until") is not None:
                report.included_period_end = _parse_timestamp(
                    period.get("until"), field_name="included.period.until"
                )

    session = _parse_legacy_limit(
        included.get("session"), field_name="included.session"
    )
    if session is not None:
        report.session_remaining_percent, report.session_resets_at = session

    weekly = _parse_legacy_limit(included.get("weekly"), field_name="included.weekly")
    if weekly is not None:
        report.weekly_remaining_percent, report.weekly_resets_at = weekly

    if not report.is_legacy_plan and not report.is_credit_plan:
        raise OllamaParseError(
            "Balance response contained neither credit balances nor legacy limits"
        )

    return report


def _sum_models(buckets: list[UsageBucket]) -> list[ModelUsage]:
    totals: dict[str, dict[str, float | int | None | bool]] = {}
    for bucket in buckets:
        for model in bucket.models:
            entry = totals.setdefault(
                model.name,
                {
                    "request_count": 0,
                    "usage_usd": 0.0,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "has_usage_usd": False,
                    "has_input_tokens": False,
                    "has_cached_input_tokens": False,
                    "has_output_tokens": False,
                },
            )
            entry["request_count"] += model.request_count
            if model.usage_usd is not None:
                entry["usage_usd"] += model.usage_usd
                entry["has_usage_usd"] = True
            if model.input_tokens is not None:
                entry["input_tokens"] += model.input_tokens
                entry["has_input_tokens"] = True
            if model.cached_input_tokens is not None:
                entry["cached_input_tokens"] += model.cached_input_tokens
                entry["has_cached_input_tokens"] = True
            if model.output_tokens is not None:
                entry["output_tokens"] += model.output_tokens
                entry["has_output_tokens"] = True
    return [
        ModelUsage(
            name=name,
            request_count=int(entry["request_count"]),
            usage_usd=entry["usage_usd"] if entry["has_usage_usd"] else None,
            input_tokens=(
                int(entry["input_tokens"]) if entry["has_input_tokens"] else None
            ),
            cached_input_tokens=(
                int(entry["cached_input_tokens"])
                if entry["has_cached_input_tokens"]
                else None
            ),
            output_tokens=(
                int(entry["output_tokens"]) if entry["has_output_tokens"] else None
            ),
        )
        for name, entry in sorted(
            totals.items(), key=lambda item: (-item[1]["request_count"], item[0])
        )
    ]


def _sum_remainder(buckets: list[UsageBucket]) -> dict[str, float | int | None]:
    usage_values = [
        b.remainder_usage_usd for b in buckets if b.remainder_usage_usd is not None
    ]
    input_values = [
        b.remainder_input_tokens
        for b in buckets
        if b.remainder_input_tokens is not None
    ]
    cached_values = [
        b.remainder_cached_input_tokens
        for b in buckets
        if b.remainder_cached_input_tokens is not None
    ]
    output_values = [
        b.remainder_output_tokens
        for b in buckets
        if b.remainder_output_tokens is not None
    ]
    return {
        "request_count": sum(bucket.remainder_request_count for bucket in buckets),
        "usage_usd": sum(usage_values) if usage_values else None,
        "input_tokens": sum(input_values) if input_values else None,
        "cached_input_tokens": sum(cached_values) if cached_values else None,
        "output_tokens": sum(output_values) if output_values else None,
    }


def _window_from_buckets(
    buckets: list[UsageBucket],
    *,
    label: str,
    period_type: str,
    start: datetime,
    end: datetime,
) -> UsageWindow:
    selected = [
        bucket
        for bucket in buckets
        if bucket.starting_at >= start and bucket.starting_at < end
    ]
    usage_values = [b.usage_usd for b in selected if b.usage_usd is not None]
    input_values = [b.input_tokens for b in selected if b.input_tokens is not None]
    cached_values = [
        b.cached_input_tokens for b in selected if b.cached_input_tokens is not None
    ]
    output_values = [b.output_tokens for b in selected if b.output_tokens is not None]
    remainder = _sum_remainder(selected)
    return UsageWindow(
        label=label,
        request_count=sum(bucket.request_count for bucket in selected),
        usage_usd=sum(usage_values) if usage_values else None,
        input_tokens=sum(input_values) if input_values else None,
        cached_input_tokens=sum(cached_values) if cached_values else None,
        output_tokens=sum(output_values) if output_values else None,
        period_type=period_type,
        starting_at=start,
        ending_at=end,
        models=_sum_models(selected),
        remainder_request_count=int(remainder["request_count"]),
        remainder_usage_usd=remainder["usage_usd"],
        remainder_input_tokens=remainder["input_tokens"],
        remainder_cached_input_tokens=remainder["cached_input_tokens"],
        remainder_output_tokens=remainder["output_tokens"],
    )


def _floor_to_day(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _floor_to_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def build_activity_window(report: UsageReport) -> UsageWindow:
    """The last 28 days, matching the documented `30d` range minus two days."""
    end = report.ending_at
    start = _floor_to_day(end - ACTIVITY_WINDOW)
    return _window_from_buckets(
        report.buckets,
        label="last_4_weeks",
        period_type="last_4_weeks",
        start=start,
        end=end,
    )


def build_weekly_window(
    report: UsageReport, balance: BalanceReport
) -> UsageWindow | None:
    """The seven days ending at the weekly reset reported by the balance API."""
    if balance.weekly_remaining_percent is None:
        return None
    end = balance.weekly_resets_at or report.ending_at
    start = _floor_to_day(end - WEEKLY_WINDOW)
    window = _window_from_buckets(
        report.buckets,
        label="weekly",
        period_type="weekly",
        start=start,
        end=end,
    )
    window.remaining_percent = balance.weekly_remaining_percent
    window.resets_at = balance.weekly_resets_at
    return window


def build_session_window(
    hourly: UsageReport, balance: BalanceReport
) -> UsageWindow | None:
    """The session window ending at the session reset reported by the balance API.

    Ollama rotates the session limit on a seven hour UTC grid, so the reset
    time is what anchors the window.
    """
    if balance.session_remaining_percent is None:
        return None
    end = balance.session_resets_at or hourly.ending_at
    start = _floor_to_hour(end - SESSION_WINDOW)
    window = _window_from_buckets(
        hourly.buckets,
        label="session",
        period_type="session",
        start=start,
        end=end,
    )
    window.remaining_percent = balance.session_remaining_percent
    window.resets_at = balance.session_resets_at
    return window


def build_credit_session_window(hourly: UsageReport) -> UsageWindow:
    """Credit plans have no session limit, so the last seven hours are used."""
    end = hourly.ending_at
    start = _floor_to_hour(end - SESSION_WINDOW)
    return _window_from_buckets(
        hourly.buckets,
        label="session",
        period_type="session",
        start=start,
        end=end,
    )


async def _fetch_usage_with_scope(
    session: aiohttp.ClientSession,
    api_key: str,
    usage_range: str,
    scope: str,
) -> tuple[dict, str]:
    """Fetch usage for the requested scope, falling back to personal scope.

    Team scope is only available to team admins. Anyone else gets a 403, so
    fall back to the personal scope instead of failing the whole update.
    """
    if scope == SCOPE_TEAM:
        try:
            return await fetch_usage(
                session, api_key, usage_range, SCOPE_TEAM
            ), SCOPE_TEAM
        except OllamaScopeError:
            _LOGGER.warning(
                "Team scope is not available for this API key, "
                "falling back to personal scope"
            )
    return await fetch_usage(session, api_key, usage_range, SCOPE_SELF), SCOPE_SELF


async def fetch_and_parse(
    session: aiohttp.ClientSession,
    api_key: str,
    usage_range: str = USAGE_RANGE_30D,
    scope: str = SCOPE_SELF,
) -> OllamaUsageData:
    balance_payload = await fetch_balance(session, api_key)
    balance = parse_balance(balance_payload)

    daily_payload, used_scope = await _fetch_usage_with_scope(
        session, api_key, usage_range, scope
    )
    daily = parse_usage(daily_payload)

    hourly_payload, _ = await _fetch_usage_with_scope(
        session, api_key, USAGE_RANGE_24H, used_scope
    )
    hourly = parse_usage(hourly_payload)

    data = OllamaUsageData(balance=balance, scope=used_scope)
    data.activity = build_activity_window(daily)

    if balance.is_legacy_plan:
        data.session = build_session_window(hourly, balance)
        data.weekly = build_weekly_window(daily, balance)
    else:
        data.session = build_credit_session_window(hourly)

    return data
