from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant

from .coordinator import OllamaConfigEntry, OllamaCoordinator, scan_interval

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    """Set up the Ollama cloud usage integration."""
    coordinator = OllamaCoordinator(hass, entry)
    coordinator.async_add_listener(coordinator._async_update_listener)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: OllamaConfigEntry) -> None:
    """Apply changed options."""
    coordinator = entry.runtime_data
    coordinator.update_interval = timedelta(seconds=scan_interval(entry))
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: OllamaConfigEntry) -> bool:
    """Unload the Ollama cloud usage integration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
