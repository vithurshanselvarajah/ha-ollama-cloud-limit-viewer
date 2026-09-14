from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
    fetch_and_parse,
)
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .resets import SessionResetTracker, WeeklyResetTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

type OllamaConfigEntry = ConfigEntry[DataUpdateCoordinator[OllamaUsageData]]


def _apply_reset_predictions(
    data: OllamaUsageData,
    session_tracker: SessionResetTracker,
    weekly_tracker: WeeklyResetTracker,
    now: datetime,
) -> None:
    if data.session is not None:
        session_tracker.observe(data.session.usage_usd, now)
        if session_tracker.has_anchor:
            end = session_tracker.next_reset(now)
            if end is not None:
                start = end - timedelta(hours=SessionResetTracker.BUCKET_HOURS)
                data.session.predicted_start = start
                data.session.predicted_end = end

    if data.weekly is not None:
        weekly_tracker.observe(data.weekly.usage_usd, now)
        if weekly_tracker.has_anchor:
            end = weekly_tracker.next_reset(now)
            if end is not None:
                start = end - timedelta(days=7)
                data.weekly.predicted_start = start
                data.weekly.predicted_end = end


async def async_setup_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    api_key = entry.data[CONF_API_KEY]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    session = async_get_clientsession(hass)
    session_tracker = SessionResetTracker()
    weekly_tracker = WeeklyResetTracker()

    async def _async_update_with_handling() -> OllamaUsageData:
        try:
            data = await fetch_and_parse(session, api_key)
        except OllamaAuthError as err:
            raise ConfigEntryAuthFailed(
                f"API key rejected by ollama.com: {err}"
            ) from err
        except OllamaParseError as err:
            raise UpdateFailed(f"Could not parse usage data: {err}") from err
        except OllamaApiError as err:
            raise UpdateFailed(f"Ollama API error: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not connect to ollama.com: {err}") from err

        _apply_reset_predictions(
            data, session_tracker, weekly_tracker, datetime.now(UTC)
        )
        return data

    coordinator: DataUpdateCoordinator[OllamaUsageData] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Ollama {entry.title}",
        update_method=_async_update_with_handling,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: OllamaConfigEntry) -> None:
    coordinator = entry.runtime_data
    new_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=new_interval)
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
