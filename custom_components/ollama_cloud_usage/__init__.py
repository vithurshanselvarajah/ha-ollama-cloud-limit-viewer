from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_COOKIE, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .scraper import (
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
    fetch_and_parse,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

type OllamaConfigEntry = ConfigEntry[DataUpdateCoordinator[OllamaUsageData]]


async def async_setup_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    cookie = entry.data[CONF_COOKIE]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    session = async_get_clientsession(hass)

    async def _async_update() -> OllamaUsageData:
        try:
            return await fetch_and_parse(session, cookie)
        except OllamaAuthError as err:
            raise UpdateFailed(
                f"Authentication failed — cookie may need refreshing: {err}"
            ) from err
        except OllamaParseError as err:
            raise UpdateFailed(f"Could not parse usage data: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not connect to ollama.com: {err}") from err

    coordinator: DataUpdateCoordinator[OllamaUsageData] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Ollama {entry.title}",
        update_method=_async_update,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
