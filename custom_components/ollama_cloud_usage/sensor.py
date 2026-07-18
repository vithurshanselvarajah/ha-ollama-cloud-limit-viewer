from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .scraper import OllamaUsageData


@dataclass(frozen=True, kw_only=True)
class OllamaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OllamaUsageData], str | float | None]


SENSOR_DESCRIPTIONS: tuple[OllamaSensorDescription, ...] = (
    OllamaSensorDescription(
        key="session_usage",
        translation_key="session_usage",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda d: d.session_percent,
    ),
    OllamaSensorDescription(
        key="session_remaining",
        translation_key="session_remaining",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge-empty",
        value_fn=lambda d: (
            round(100.0 - d.session_percent, 1)
            if d.session_percent is not None
            else None
        ),
    ),
    OllamaSensorDescription(
        key="session_resets_in",
        translation_key="session_resets_in",
        icon="mdi:timer-sand",
        value_fn=lambda d: d.session_resets_in,
    ),
    OllamaSensorDescription(
        key="weekly_usage",
        translation_key="weekly_usage",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bar",
        value_fn=lambda d: d.weekly_percent,
    ),
    OllamaSensorDescription(
        key="weekly_remaining",
        translation_key="weekly_remaining",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bar-stacked",
        value_fn=lambda d: (
            round(100.0 - d.weekly_percent, 1) if d.weekly_percent is not None else None
        ),
    ),
    OllamaSensorDescription(
        key="weekly_resets_in",
        translation_key="weekly_resets_in",
        icon="mdi:calendar-clock",
        value_fn=lambda d: d.weekly_resets_in,
    ),
    OllamaSensorDescription(
        key="model_info",
        translation_key="model_info",
        icon="mdi:robot",
        value_fn=lambda d: d.model_note,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DataUpdateCoordinator[OllamaUsageData] = entry.runtime_data

    async_add_entities(
        OllamaUsageSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class OllamaUsageSensor(
    CoordinatorEntity[DataUpdateCoordinator[OllamaUsageData]], SensorEntity
):
    entity_description: OllamaSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[OllamaUsageData],
        entry: ConfigEntry,
        description: OllamaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Ollama {entry.title}",
            "manufacturer": "Ollama",
            "model": "Cloud Usage",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> str | float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
