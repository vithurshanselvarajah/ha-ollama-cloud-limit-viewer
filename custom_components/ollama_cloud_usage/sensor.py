from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .scraper import OllamaUsageData

_LOGGER = logging.getLogger(__name__)

LEGACY_KEYS: frozenset[str] = frozenset(
    {
        "session_usage",
        "session_remaining",
        "session_resets_in",
        "weekly_usage",
        "weekly_remaining",
        "weekly_resets_in",
    }
)

MONTHLY_KEYS: frozenset[str] = frozenset(
    {
        "monthly_usage",
        "monthly_remaining",
        "monthly_resets_in",
        "monthly_resets_at",
        "tier",
    }
)


@dataclass(frozen=True, kw_only=True)
class OllamaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OllamaUsageData], str | float | None]


def _remaining(value: float | None) -> float | None:
    return round(100.0 - value, 1) if value is not None else None


SENSOR_DESCRIPTIONS: tuple[OllamaSensorDescription, ...] = (
    OllamaSensorDescription(
        key="session_usage",
        translation_key="session_usage",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge",
        value_fn=lambda d: d.session_percent,
    ),
    OllamaSensorDescription(
        key="session_remaining",
        translation_key="session_remaining",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge-empty",
        value_fn=lambda d: _remaining(d.session_percent),
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
        suggested_display_precision=1,
        icon="mdi:chart-bar",
        value_fn=lambda d: d.weekly_percent,
    ),
    OllamaSensorDescription(
        key="weekly_remaining",
        translation_key="weekly_remaining",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:chart-bar-stacked",
        value_fn=lambda d: _remaining(d.weekly_percent),
    ),
    OllamaSensorDescription(
        key="weekly_resets_in",
        translation_key="weekly_resets_in",
        icon="mdi:calendar-clock",
        value_fn=lambda d: d.weekly_resets_in,
    ),
    OllamaSensorDescription(
        key="monthly_usage",
        translation_key="monthly_usage",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge",
        value_fn=lambda d: d.monthly_percent,
    ),
    OllamaSensorDescription(
        key="monthly_remaining",
        translation_key="monthly_remaining",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge-empty",
        value_fn=lambda d: _remaining(d.monthly_percent),
    ),
    OllamaSensorDescription(
        key="monthly_resets_in",
        translation_key="monthly_resets_in",
        icon="mdi:calendar-clock",
        value_fn=lambda d: d.monthly_resets_in,
    ),
    OllamaSensorDescription(
        key="monthly_resets_at",
        translation_key="monthly_resets_at",
        icon="mdi:calendar-arrow-right",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=None,
        value_fn=lambda d: d.monthly_resets_at,
    ),
    OllamaSensorDescription(
        key="tier",
        translation_key="tier",
        icon="mdi:tag",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.tier,
    ),
    OllamaSensorDescription(
        key="model_info",
        translation_key="model_info",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.model_note,
    ),
)


def _purge_legacy_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    for key in LEGACY_KEYS:
        unique_id = f"{entry.entry_id}_{key}"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id:
            _LOGGER.info(
                "Removing legacy sensor %s (entry %s) — account is on monthly usage",
                entity_id,
                entry.entry_id,
            )
            registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DataUpdateCoordinator[OllamaUsageData] = entry.runtime_data
    data = coordinator.data
    if data is not None and data.has_monthly:
        active_keys: frozenset[str] = MONTHLY_KEYS | frozenset({"model_info"})
        _purge_legacy_entities(hass, entry)
    elif data is not None:
        active_keys = LEGACY_KEYS | frozenset({"model_info"})
    else:
        _LOGGER.debug(
            "Coordinator data unavailable during sensor setup for %s; deferring",
            entry.title,
        )
        return

    async_add_entities(
        OllamaUsageSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
        if description.key in active_keys
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Ollama {entry.title}",
            manufacturer="Ollama",
            model="Cloud Usage",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str | float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.last_update_success
