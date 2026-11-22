from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import aiohttp

from .const import (
    BALANCE_URL,
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

    @property
    def total_requests(self) -> int:
        return sum(model.request_count for model in self.models)


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


@dataclass
class UsageSummary:
    request_count: int = 0
    usage_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    models: list[ModelUsage] = field(default_factory=list)


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
        if resp.status in (401, 403):
            raise OllamaAuthError(
                f"API key rejected by ollama.com (HTTP {resp.status})"
            )
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
) -> dict:
    return await _request_json(
        session,
        USAGE_URL,
        api_key,
        params={"range": usage_range, "group_by": "model"},
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
        models.append(ModelUsage(name=name, request_count=count))
    return models


def _parse_summary(payload: dict) -> UsageSummary:
    request_count = _coerce_int(payload.get("request_count", 0))
    if request_count is None:
        raise OllamaParseError(
            f"Expected integer request_count, got {payload.get('request_count')!r}"
        )
    return UsageSummary(
        request_count=request_count,
        usage_usd=_coerce_float(payload.get("usage_usd")),
        input_tokens=_coerce_int(payload.get("input_tokens")),
        cached_input_tokens=_coerce_int(payload.get("cached_input_tokens")),
        output_tokens=_coerce_int(payload.get("output_tokens")),
        models=_parse_models(payload.get("groups")),
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
    counts: dict[str, int] = {}
    for bucket in buckets:
        for model in bucket.models:
            counts[model.name] = counts.get(model.name, 0) + model.request_count
    return [
        ModelUsage(name=name, request_count=count)
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


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
    )


def _floor_to_day(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _floor_to_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def build_activity_window(report: UsageReport) -> UsageWindow:
    end = report.ending_at
    start = _floor_to_day(end - ACTIVITY_WINDOW)
    return _window_from_buckets(
        report.buckets,
        label="last_4_weeks",
        period_type="last_4_weeks",
        start=start,
        end=end,
    )


def build_legacy_session_window(
    hourly: UsageReport,
    daily: UsageReport,
    balance: BalanceReport,
) -> UsageWindow | None:
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


def build_legacy_weekly_window(
    report: UsageReport, balance: BalanceReport
) -> UsageWindow | None:
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


def build_credit_session_window(hourly: UsageReport) -> UsageWindow:
    end = hourly.ending_at
    start = _floor_to_hour(end - SESSION_WINDOW)
    return _window_from_buckets(
        hourly.buckets,
        label="session",
        period_type="session",
        start=start,
        end=end,
    )


async def fetch_and_parse(
    session: aiohttp.ClientSession,
    api_key: str,
    usage_range: str = USAGE_RANGE_30D,
) -> OllamaUsageData:
    balance_payload = await fetch_balance(session, api_key)
    balance = parse_balance(balance_payload)

    daily_payload = await fetch_usage(session, api_key, usage_range)
    daily = parse_usage(daily_payload)

    hourly_payload = await fetch_usage(session, api_key, USAGE_RANGE_24H)
    hourly = parse_usage(hourly_payload)

    data = OllamaUsageData(balance=balance)
    data.activity = build_activity_window(daily)

    if balance.is_legacy_plan:
        data.session = build_legacy_session_window(hourly, daily, balance)
        data.weekly = build_legacy_weekly_window(daily, balance)
    else:
        data.session = build_credit_session_window(hourly)

    return data
