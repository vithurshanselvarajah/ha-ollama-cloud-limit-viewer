from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OllamaConfigEntry, OllamaCoordinator


class OllamaUsageEntity(CoordinatorEntity[OllamaCoordinator]):
    """Base entity for the Ollama cloud usage integration."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: OllamaCoordinator, entry: OllamaConfigEntry
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Ollama {entry.title}",
            manufacturer="Ollama",
            model="Cloud Usage",
            entry_type=DeviceEntryType.SERVICE,
        )
