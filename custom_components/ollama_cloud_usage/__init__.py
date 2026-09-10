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

from .const import (
    CONF_COOKIE,
    CONF_SCAN_INTERVAL,
    CONF_USAGE_MODE,
    DEFAULT_SCAN_INTERVAL,
    USAGE_MODE_LEGACY,
    USAGE_MODE_MONTHLY,
)
from .scraper import (
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
    fetch_and_parse,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

type OllamaConfigEntry = ConfigEntry[DataUpdateCoordinator[OllamaUsageData]]


async def async_migrate_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version < 2:
        new_data = {**entry.data, CONF_USAGE_MODE: USAGE_MODE_LEGACY}
        hass.config_entries.async_update_entry(
            entry, data=new_data, version=2, minor_version=1
        )
    return True


def _detect_mode(data: OllamaUsageData) -> str | None:
    if data.has_monthly and not data.has_legacy:
        return USAGE_MODE_MONTHLY
    if data.has_legacy and not data.has_monthly:
        return USAGE_MODE_LEGACY
    return None


async def async_setup_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    cookie = entry.data[CONF_COOKIE]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    current_mode = entry.data.get(CONF_USAGE_MODE)
    session = async_get_clientsession(hass)

    async def _async_update() -> OllamaUsageData:
        return await fetch_and_parse(session, cookie)

    async def _async_update_with_handling() -> OllamaUsageData:
        try:
            data = await _async_update()
        except OllamaAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Cookie expired or invalid — reauth required: {err}"
            ) from err
        except OllamaParseError as err:
            raise UpdateFailed(f"Could not parse usage data: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not connect to ollama.com: {err}") from err

        nonlocal current_mode
        detected = _detect_mode(data)
        if detected is not None and detected != current_mode:
            if current_mode == USAGE_MODE_LEGACY and detected == USAGE_MODE_MONTHLY:
                _LOGGER.info(
                    "Account %s transitioned from legacy to monthly usage",
                    entry.title,
                )
            current_mode = detected
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_USAGE_MODE: current_mode}
            )
        elif current_mode is None:
            current_mode = detected or USAGE_MODE_LEGACY
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_USAGE_MODE: current_mode}
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
