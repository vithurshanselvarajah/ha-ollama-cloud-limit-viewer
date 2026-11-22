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
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import BalanceReport, OllamaUsageData, UsageWindow
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OllamaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OllamaUsageData], str | float | int | datetime | None]


def _window_requests(window: UsageWindow | None) -> int | None:
    return window.request_count if window else None


def _window_spend(window: UsageWindow | None) -> float | None:
    return window.usage_usd if window else None


def _window_remaining(window: UsageWindow | None) -> float | None:
    return window.remaining_percent if window else None


def _window_top_model(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return max(window.models, key=lambda model: model.request_count).name


def _window_model_breakdown(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return ", ".join(f"{model.name} ({model.request_count})" for model in window.models)


def _window_start(window: UsageWindow | None) -> datetime | None:
    return window.starting_at if window else None


def _window_end(window: UsageWindow | None) -> datetime | None:
    if not window:
        return None
    return window.resets_at or window.ending_at


def _window_seconds_remaining(window: UsageWindow | None) -> float | None:
    end = _window_end(window)
    if end is None:
        return None
    return max(0.0, (end - datetime.now(UTC)).total_seconds())


def _balance_value(balance: BalanceReport | None, attribute: str) -> float | None:
    if balance is None:
        return None
    return getattr(balance, attribute)


def _balance_period_start(balance: BalanceReport | None) -> datetime | None:
    return balance.included_period_start if balance else None


def _balance_period_end(balance: BalanceReport | None) -> datetime | None:
    return balance.included_period_end if balance else None


def _balance_period_seconds_remaining(balance: BalanceReport | None) -> float | None:
    end = _balance_period_end(balance)
    if end is None:
        return None
    return max(0.0, (end - datetime.now(UTC)).total_seconds())


SENSOR_DESCRIPTIONS: tuple[OllamaSensorDescription, ...] = (
    OllamaSensorDescription(
        key="session_requests",
        translation_key="session_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda data: _window_requests(data.session),
    ),
    OllamaSensorDescription(
        key="session_spend",
        translation_key="session_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=5,
        icon="mdi:cash-clock",
        value_fn=lambda data: _window_spend(data.session),
    ),
    OllamaSensorDescription(
        key="session_remaining",
        translation_key="session_remaining",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=lambda data: _window_remaining(data.session),
    ),
    OllamaSensorDescription(
        key="session_top_model",
        translation_key="session_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_top_model(data.session),
    ),
    OllamaSensorDescription(
        key="session_model_breakdown",
        translation_key="session_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_model_breakdown(data.session),
    ),
    OllamaSensorDescription(
        key="session_period_start",
        translation_key="session_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_start(data.session),
    ),
    OllamaSensorDescription(
        key="session_period_end",
        translation_key="session_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_end(data.session),
    ),
    OllamaSensorDescription(
        key="session_period_remaining",
        translation_key="session_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_seconds_remaining(data.session),
    ),
    OllamaSensorDescription(
        key="weekly_requests",
        translation_key="weekly_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda data: _window_requests(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_spend",
        translation_key="weekly_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=5,
        icon="mdi:cash-multiple",
        value_fn=lambda data: _window_spend(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_remaining",
        translation_key="weekly_remaining",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=lambda data: _window_remaining(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_top_model",
        translation_key="weekly_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_top_model(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_model_breakdown",
        translation_key="weekly_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_model_breakdown(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_start",
        translation_key="weekly_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_start(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_end",
        translation_key="weekly_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_end(data.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_remaining",
        translation_key="weekly_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_seconds_remaining(data.weekly),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_requests",
        translation_key="last_4_weeks_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_requests(data.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_spend",
        translation_key="last_4_weeks_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=5,
        icon="mdi:cash-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_spend(data.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_top_model",
        translation_key="last_4_weeks_top_model",
        icon="mdi:robot",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_top_model(data.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_model_breakdown",
        translation_key="last_4_weeks_model_breakdown",
        icon="mdi:format-list-bulleted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_model_breakdown(data.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_start",
        translation_key="last_4_weeks_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_start(data.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_end",
        translation_key="last_4_weeks_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _window_end(data.activity),
    ),
    OllamaSensorDescription(
        key="included_balance",
        translation_key="included_balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:credit-card-outline",
        value_fn=lambda data: _balance_value(data.balance, "included_balance_usd"),
    ),
    OllamaSensorDescription(
        key="included_allowance",
        translation_key="included_allowance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:credit-card-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _balance_value(data.balance, "included_allowance_usd"),
    ),
    OllamaSensorDescription(
        key="purchased_balance",
        translation_key="purchased_balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:wallet",
        value_fn=lambda data: _balance_value(data.balance, "purchased_balance_usd"),
    ),
    OllamaSensorDescription(
        key="included_period_start",
        translation_key="included_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _balance_period_start(data.balance),
    ),
    OllamaSensorDescription(
        key="included_period_end",
        translation_key="included_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _balance_period_end(data.balance),
    ),
    OllamaSensorDescription(
        key="included_period_remaining",
        translation_key="included_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _balance_period_seconds_remaining(data.balance),
    ),
)


def _available_keys(data: OllamaUsageData) -> set[str]:
    keys: set[str] = set()

    for prefix, window in (
        ("session", data.session),
        ("weekly", data.weekly),
        ("last_4_weeks", data.activity),
    ):
        if window is None:
            continue
        keys.update(
            {
                f"{prefix}_requests",
                f"{prefix}_top_model",
                f"{prefix}_model_breakdown",
                f"{prefix}_period_start",
                f"{prefix}_period_end",
            }
        )
        if window.usage_usd is not None:
            keys.add(f"{prefix}_spend")
        if prefix != "last_4_weeks":
            keys.add(f"{prefix}_period_remaining")

    balance = data.balance
    if balance is None:
        return keys

    if balance.is_legacy_plan:
        keys.update({"session_remaining", "weekly_remaining"})
    if balance.is_credit_plan:
        keys.update(
            {
                "included_balance",
                "included_allowance",
                "included_period_start",
                "included_period_end",
                "included_period_remaining",
            }
        )
    if balance.purchased_balance_usd is not None:
        keys.add("purchased_balance")
    return keys


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DataUpdateCoordinator[OllamaUsageData] = entry.runtime_data
    data = coordinator.data
    if data is None:
        _LOGGER.debug("No data available yet for %s, skipping sensors", entry.title)
        return

    active_keys = _available_keys(data)
    _async_remove_stale_entities(hass, entry, active_keys)

    async_add_entities(
        OllamaUsageSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
        if description.key in active_keys
    )


def _async_remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, active_keys: set[str]
) -> None:
    registry = er.async_get(hass)
    for registry_entry in list(
        er.async_entries_for_config_entry(registry, entry.entry_id)
    ):
        unique_id = registry_entry.unique_id
        if not unique_id or not unique_id.startswith(f"{entry.entry_id}_"):
            continue
        if unique_id.removeprefix(f"{entry.entry_id}_") in active_keys:
            continue
        registry.async_remove(registry_entry.entity_id)


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
