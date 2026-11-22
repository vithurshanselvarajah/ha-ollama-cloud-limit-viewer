from __future__ import annotations

import logging
from datetime import timedelta

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
    OllamaRateLimitError,
    OllamaUsageData,
    fetch_and_parse,
)
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE,
    DEFAULT_SCAN_INTERVAL,
    SCOPE_SELF,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

type OllamaConfigEntry = ConfigEntry[DataUpdateCoordinator[OllamaUsageData]]


def _scan_interval(entry: OllamaConfigEntry) -> int:
    return entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )


def _scope(entry: OllamaConfigEntry) -> str:
    return entry.options.get(
        CONF_SCOPE,
        entry.data.get(CONF_SCOPE, SCOPE_SELF),
    )


async def async_setup_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    api_key = entry.data[CONF_API_KEY]
    session = async_get_clientsession(hass)

    async def _async_update_with_handling() -> OllamaUsageData:
        try:
            return await fetch_and_parse(session, api_key, scope=_scope(entry))
        except OllamaAuthError as err:
            raise ConfigEntryAuthFailed(
                f"API key rejected by ollama.com: {err}"
            ) from err
        except OllamaRateLimitError as err:
            retry_after = err.retry_after if err.retry_after is not None else 60
            raise UpdateFailed(
                f"Rate limited by ollama.com: {err}",
                retry_after=retry_after,
            ) from err
        except OllamaParseError as err:
            raise UpdateFailed(f"Could not parse usage data: {err}") from err
        except OllamaApiError as err:
            raise UpdateFailed(f"Ollama API error: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not connect to ollama.com: {err}") from err

    coordinator: DataUpdateCoordinator[OllamaUsageData] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=f"Ollama {entry.title}",
        update_method=_async_update_with_handling,
        update_interval=timedelta(seconds=_scan_interval(entry)),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: OllamaConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator.update_interval = timedelta(seconds=_scan_interval(entry))
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
