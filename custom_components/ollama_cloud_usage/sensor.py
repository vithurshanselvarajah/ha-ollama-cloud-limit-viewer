from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import OllamaUsageData, UsageWindow
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OllamaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OllamaUsageData], str | float | int | datetime | None]


def _window_usage(window: UsageWindow | None) -> float | None:
    return window.usage_usd if window else None


def _window_total_requests(window: UsageWindow | None) -> int | None:
    return window.total_requests if window else None


def _window_top_model(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return max(window.models, key=lambda m: m.request_count).name


def _window_model_breakdown(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return ", ".join(f"{m.name} ({m.request_count})" for m in window.models)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _period_start(window: UsageWindow | None) -> datetime | None:
    if not window:
        return None
    if window.predicted_start is not None:
        return window.predicted_start
    return _parse_iso(window.starting_at)


def _period_end(window: UsageWindow | None) -> datetime | None:
    if not window:
        return None
    if window.predicted_end is not None:
        return window.predicted_end
    return _parse_iso(window.ending_at)


def _period_remaining(window: UsageWindow | None) -> float | None:
    end = _period_end(window)
    if not end:
        return None
    now = datetime.now(UTC)
    return max(0.0, (end - now).total_seconds())


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


SENSOR_DESCRIPTIONS: tuple[OllamaSensorDescription, ...] = (
    OllamaSensorDescription(
        key="session_spend",
        translation_key="session_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=5,
        icon="mdi:cash-clock",
        value_fn=lambda d: _window_usage(d.session),
    ),
    OllamaSensorDescription(
        key="session_requests",
        translation_key="session_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda d: _window_total_requests(d.session),
    ),
    OllamaSensorDescription(
        key="session_top_model",
        translation_key="session_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_top_model(d.session),
    ),
    OllamaSensorDescription(
        key="session_model_breakdown",
        translation_key="session_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_model_breakdown(d.session),
    ),
    OllamaSensorDescription(
        key="session_period_start",
        translation_key="session_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_start(d.session),
    ),
    OllamaSensorDescription(
        key="session_period_end",
        translation_key="session_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_end(d.session),
    ),
    OllamaSensorDescription(
        key="session_period_remaining",
        translation_key="session_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _as_float(_period_remaining(d.session)),
    ),
    OllamaSensorDescription(
        key="weekly_spend",
        translation_key="weekly_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=5,
        icon="mdi:cash-multiple",
        value_fn=lambda d: _window_usage(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_requests",
        translation_key="weekly_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda d: _window_total_requests(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_top_model",
        translation_key="weekly_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_top_model(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_model_breakdown",
        translation_key="weekly_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_model_breakdown(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_start",
        translation_key="weekly_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_start(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_end",
        translation_key="weekly_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_end(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_remaining",
        translation_key="weekly_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _as_float(_period_remaining(d.weekly)),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_spend",
        translation_key="last_4_weeks_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=5,
        icon="mdi:cash-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_usage(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_requests",
        translation_key="last_4_weeks_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:counter",
        value_fn=lambda d: _window_total_requests(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_top_model",
        translation_key="last_4_weeks_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_top_model(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_model_breakdown",
        translation_key="last_4_weeks_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_model_breakdown(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_start",
        translation_key="last_4_weeks_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_start(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_end",
        translation_key="last_4_weeks_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _period_end(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_remaining",
        translation_key="last_4_weeks_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _as_float(_period_remaining(d.activity)),
    ),
)


def _available_keys(data: OllamaUsageData) -> set[str]:
    keys: set[str] = set()
    if data.session is not None:
        keys.update(
            {
                "session_spend",
                "session_requests",
                "session_top_model",
                "session_model_breakdown",
                "session_period_start",
                "session_period_end",
                "session_period_remaining",
            }
        )
    if data.weekly is not None:
        keys.update(
            {
                "weekly_spend",
                "weekly_requests",
                "weekly_top_model",
                "weekly_model_breakdown",
                "weekly_period_start",
                "weekly_period_end",
                "weekly_period_remaining",
            }
        )
    if data.activity is not None:
        keys.update(
            {
                "last_4_weeks_spend",
                "last_4_weeks_requests",
                "last_4_weeks_top_model",
                "last_4_weeks_model_breakdown",
                "last_4_weeks_period_start",
                "last_4_weeks_period_end",
                "last_4_weeks_period_remaining",
            }
        )
    return keys


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DataUpdateCoordinator[OllamaUsageData] = entry.runtime_data
    data = coordinator.data
    if data is None:
        _LOGGER.debug(
            "Coordinator data unavailable during sensor setup for %s; deferring",
            entry.title,
        )
        return

    active_keys = _available_keys(data)

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
    def native_value(self) -> str | float | int | datetime | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.last_update_success
