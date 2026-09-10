from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import aiohttp
from bs4 import BeautifulSoup, Tag

from .const import SETTINGS_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

MeterKind = Literal["session", "weekly", "monthly"]


class OllamaAuthError(Exception):
    pass


class OllamaParseError(Exception):
    pass


@dataclass
class OllamaUsageData:
    # Legacy model (session + weekly).
    session_percent: float | None = None
    session_resets_in: str | None = None
    weekly_percent: float | None = None
    weekly_resets_in: str | None = None

    # New model (single fixed monthly/included-usage limit).
    monthly_percent: float | None = None
    monthly_resets_in: str | None = None
    monthly_resets_at: str | None = None  # ISO 8601 UTC, if available
    tier: str | None = None  # "free" / "pro" / "plus" / etc.

    # Shared.
    model_note: str | None = None

    @property
    def has_monthly(self) -> bool:
        return self.monthly_percent is not None

    @property
    def has_legacy(self) -> bool:
        return self.session_percent is not None or self.weekly_percent is not None


async def fetch_settings_html(session: aiohttp.ClientSession, cookie: str) -> str:
    headers = {
        "Cookie": cookie,
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }
    async with session.get(
        SETTINGS_URL,
        headers=headers,
        allow_redirects=False,
        raise_for_status=False,
    ) as resp:
        if 300 <= resp.status < 400:
            raise OllamaAuthError(
                "Cookie expired or not authenticated (redirected to login)"
            )
        if resp.status != 200:
            raise OllamaAuthError(f"Unexpected HTTP {resp.status} from ollama.com")
        return await resp.text()


def _parse_percent(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"([\d.]+)\s*%", text)
    return float(match.group(1)) if match else None


def _parse_resets(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"resets?\s+in\s+(.+?)\.?\s*$", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip() or None


def _classify_block(label: str | None) -> MeterKind:
    if not label:
        return "monthly"
    lbl = label.lower()
    if "session" in lbl:
        return "session"
    if "week" in lbl:
        return "weekly"
    return "monthly"


def _extract_block(meter: Tag) -> dict:
    label_row = meter.find_previous_sibling("div")
    label = None
    percent_text = None
    if label_row:
        spans = label_row.find_all("span")
        if spans:
            label = spans[0].get_text(strip=True)
        if len(spans) > 1:
            percent_text = spans[-1].get_text(strip=True)

    reset_text = None
    resets_at = None
    sibling = meter.find_next_sibling()
    guard = 0
    while sibling and guard < 4:
        text = sibling.get_text(strip=True)
        if re.search(r"resets?\s+in", text, re.IGNORECASE):
            reset_text = text
            resets_at = sibling.get("data-time")
            break
        sibling = sibling.find_next_sibling()
        guard += 1

    segments = []
    for seg in meter.find_all(attrs={"data-usage-segment": True}):
        model = seg.get("data-model")
        if not model:
            continue
        reqs = seg.get("data-requests")
        if reqs and reqs.isdigit():
            n = int(reqs)
            req_str = f"{n} request{'s' if n != 1 else ''}"
            segments.append(f"{model}, {req_str}")
        else:
            segments.append(model)

    return {
        "label": label,
        "percent_text": percent_text,
        "reset_text": reset_text,
        "resets_at": resets_at,
        "model_note": " · ".join(segments) if segments else None,
    }


def _extract_tier(soup: BeautifulSoup) -> str | None:
    heading = soup.find(
        lambda tag: (
            tag.name in {"h1", "h2"}
            and tag.find("span", class_=re.compile(r"capitalize")) is not None
            and re.search(r"\busage\b", tag.get_text(), re.IGNORECASE) is not None
        )
    )
    if not heading:
        return None
    badge = heading.find("span", class_=re.compile(r"capitalize"))
    if badge:
        return badge.get_text(strip=True).lower() or None
    return None


def parse_usage(html: str) -> OllamaUsageData:
    soup = BeautifulSoup(html, "html.parser")
    meters = soup.find_all(attrs={"data-usage-meter": True})

    if not meters:
        raise OllamaParseError(
            "No usage meters found — page structure may have changed or cookie invalid"
        )

    tier = _extract_tier(soup)

    blocks = [_extract_block(m) for m in meters]

    session_block: dict | None = None
    weekly_block: dict | None = None
    monthly_block: dict | None = None

    for block in blocks:
        kind = _classify_block(block["label"])
        if kind == "session" and session_block is None:
            session_block = block
        elif kind == "weekly" and weekly_block is None:
            weekly_block = block
        elif kind == "monthly" and monthly_block is None:
            monthly_block = block

    session_percent = _parse_percent(
        session_block["percent_text"] if session_block else None
    )
    session_resets_in = _parse_resets(
        session_block["reset_text"] if session_block else None
    )
    weekly_percent = _parse_percent(
        weekly_block["percent_text"] if weekly_block else None
    )
    weekly_resets_in = _parse_resets(
        weekly_block["reset_text"] if weekly_block else None
    )
    monthly_percent = _parse_percent(
        monthly_block["percent_text"] if monthly_block else None
    )
    monthly_resets_in = _parse_resets(
        monthly_block["reset_text"] if monthly_block else None
    )
    monthly_resets_at = monthly_block.get("resets_at") if monthly_block else None

    if weekly_percent is not None and weekly_percent >= 100:
        session_percent = 100.0
        session_resets_in = weekly_resets_in

    model_note = None
    if monthly_block and monthly_block["model_note"]:
        model_note = monthly_block["model_note"]
    elif weekly_block and weekly_block["model_note"]:
        model_note = weekly_block["model_note"]
    elif session_block and session_block["model_note"]:
        model_note = session_block["model_note"]

    if session_percent is None and weekly_percent is None and monthly_percent is None:
        raise OllamaParseError("Found usage meters but could not extract any values")

    return OllamaUsageData(
        session_percent=session_percent,
        session_resets_in=session_resets_in,
        weekly_percent=weekly_percent,
        weekly_resets_in=weekly_resets_in,
        monthly_percent=monthly_percent,
        monthly_resets_in=monthly_resets_in,
        monthly_resets_at=monthly_resets_at,
        tier=tier,
        model_note=model_note,
    )


async def fetch_and_parse(
    session: aiohttp.ClientSession, cookie: str
) -> OllamaUsageData:
    html = await fetch_settings_html(session, cookie)
    return parse_usage(html)
