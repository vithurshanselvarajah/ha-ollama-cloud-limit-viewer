from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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

type OllamaConfigEntry = ConfigEntry[OllamaCoordinator]


class OllamaCoordinator(DataUpdateCoordinator[OllamaUsageData]):
    """Fetch usage data from the Ollama cloud API."""

    config_entry: OllamaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: OllamaConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Ollama {entry.title}",
            update_interval=timedelta(seconds=scan_interval(entry)),
        )
        self._api_key = entry.data[CONF_API_KEY]
        self._session = async_get_clientsession(hass)
        self._was_available = True

    async def _async_update_data(self) -> OllamaUsageData:
        """Fetch the latest usage data."""
        try:
            return await fetch_and_parse(
                self._session, self._api_key, scope=scope(self.config_entry)
            )
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

    @callback
    def _async_update_listener(self) -> None:
        """Log when the connection is lost and when it comes back."""
        available = self.last_update_success
        if available == self._was_available:
            return
        self._was_available = available
        if available:
            _LOGGER.info("Connection to ollama.com restored")
        else:
            _LOGGER.warning("Lost connection to ollama.com")


def scan_interval(entry: ConfigEntry) -> int:
    """Return the configured update interval."""
    return entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )


def scope(entry: ConfigEntry) -> str:
    """Return the configured usage scope."""
    return entry.options.get(
        CONF_SCOPE,
        entry.data.get(CONF_SCOPE, SCOPE_SELF),
    )
