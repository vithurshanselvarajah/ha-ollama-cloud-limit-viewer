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


def _window_usage(window: UsageWindow | None) -> float | None:
    return window.usage_usd if window else None


def _window_requests(window: UsageWindow | None) -> int | None:
    return window.request_count if window else None


def _window_remaining_percent(window: UsageWindow | None) -> float | None:
    return window.remaining_percent if window else None


def _window_top_model(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return max(window.models, key=lambda m: m.request_count).name


def _window_model_breakdown(window: UsageWindow | None) -> str | None:
    if not window or not window.models:
        return None
    return ", ".join(f"{m.name} ({m.request_count})" for m in window.models)


def _window_period_start(window: UsageWindow | None) -> datetime | None:
    return window.starting_at if window else None


def _window_period_end(window: UsageWindow | None) -> datetime | None:
    if not window:
        return None
    if window.resets_at is not None:
        return window.resets_at
    return window.ending_at


def _period_remaining(window: UsageWindow | None) -> float | None:
    end = _window_period_end(window)
    if not end:
        return None
    return max(0.0, (end - datetime.now(UTC)).total_seconds())


def _balance_included_balance(balance: BalanceReport | None) -> float | None:
    return balance.included_balance_usd if balance else None


def _balance_included_allowance(balance: BalanceReport | None) -> float | None:
    return balance.included_allowance_usd if balance else None


def _balance_purchased_balance(balance: BalanceReport | None) -> float | None:
    return balance.purchased_balance_usd if balance else None


def _balance_period_start(balance: BalanceReport | None) -> datetime | None:
    return balance.included_period_start if balance else None


def _balance_period_end(balance: BalanceReport | None) -> datetime | None:
    return balance.included_period_end if balance else None


def _balance_period_remaining(balance: BalanceReport | None) -> float | None:
    end = _balance_period_end(balance)
    if not end:
        return None
    return max(0.0, (end - datetime.now(UTC)).total_seconds())


def _session_requests(data: OllamaUsageData) -> int | None:
    return _window_requests(data.session)


def _weekly_requests(data: OllamaUsageData) -> int | None:
    return _window_requests(data.weekly)


def _activity_requests(data: OllamaUsageData) -> int | None:
    return _window_requests(data.activity)


def _session_spend(data: OllamaUsageData) -> float | None:
    return _window_usage(data.session)


def _weekly_spend(data: OllamaUsageData) -> float | None:
    return _window_usage(data.weekly)


def _activity_spend(data: OllamaUsageData) -> float | None:
    return _window_usage(data.activity)


def _session_remaining(data: OllamaUsageData) -> float | None:
    return _window_remaining_percent(data.session)


def _weekly_remaining(data: OllamaUsageData) -> float | None:
    return _window_remaining_percent(data.weekly)


def _session_period_end(data: OllamaUsageData) -> datetime | None:
    return _window_period_end(data.session)


def _weekly_period_end(data: OllamaUsageData) -> datetime | None:
    return _window_period_end(data.weekly)


def _session_period_remaining(data: OllamaUsageData) -> float | None:
    return _period_remaining(data.session)


def _weekly_period_remaining(data: OllamaUsageData) -> float | None:
    return _period_remaining(data.weekly)


SENSOR_DESCRIPTIONS: tuple[OllamaSensorDescription, ...] = (
    OllamaSensorDescription(
        key="session_requests",
        translation_key="session_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=_session_requests,
    ),
    OllamaSensorDescription(
        key="session_spend",
        translation_key="session_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=5,
        icon="mdi:cash-clock",
        value_fn=_session_spend,
    ),
    OllamaSensorDescription(
        key="session_remaining",
        translation_key="session_remaining",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=_session_remaining,
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
        value_fn=lambda d: _window_period_start(d.session),
    ),
    OllamaSensorDescription(
        key="session_period_end",
        translation_key="session_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_session_period_end,
    ),
    OllamaSensorDescription(
        key="session_period_remaining",
        translation_key="session_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_session_period_remaining,
    ),
    OllamaSensorDescription(
        key="weekly_requests",
        translation_key="weekly_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=_weekly_requests,
    ),
    OllamaSensorDescription(
        key="weekly_spend",
        translation_key="weekly_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=5,
        icon="mdi:cash-multiple",
        value_fn=_weekly_spend,
    ),
    OllamaSensorDescription(
        key="weekly_remaining",
        translation_key="weekly_remaining",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gauge",
        value_fn=_weekly_remaining,
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
        value_fn=lambda d: _window_period_start(d.weekly),
    ),
    OllamaSensorDescription(
        key="weekly_period_end",
        translation_key="weekly_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_weekly_period_end,
    ),
    OllamaSensorDescription(
        key="weekly_period_remaining",
        translation_key="weekly_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_weekly_period_remaining,
    ),
    OllamaSensorDescription(
        key="last_4_weeks_requests",
        translation_key="last_4_weeks_requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_activity_requests,
    ),
    OllamaSensorDescription(
        key="last_4_weeks_spend",
        translation_key="last_4_weeks_spend",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=5,
        icon="mdi:cash-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_activity_spend,
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
        value_fn=lambda d: _window_period_start(d.activity),
    ),
    OllamaSensorDescription(
        key="last_4_weeks_period_end",
        translation_key="last_4_weeks_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _window_period_end(d.activity),
    ),
    OllamaSensorDescription(
        key="included_balance",
        translation_key="included_balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:credit-card-outline",
        value_fn=lambda d: _balance_included_balance(d.balance),
    ),
    OllamaSensorDescription(
        key="included_allowance",
        translation_key="included_allowance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:credit-card-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _balance_included_allowance(d.balance),
    ),
    OllamaSensorDescription(
        key="purchased_balance",
        translation_key="purchased_balance",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        icon="mdi:wallet",
        value_fn=lambda d: _balance_purchased_balance(d.balance),
    ),
    OllamaSensorDescription(
        key="included_period_start",
        translation_key="included_period_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _balance_period_start(d.balance),
    ),
    OllamaSensorDescription(
        key="included_period_end",
        translation_key="included_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _balance_period_end(d.balance),
    ),
    OllamaSensorDescription(
        key="included_period_remaining",
        translation_key="included_period_remaining",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _balance_period_remaining(d.balance),
    ),
)

LEGACY_ONLY_KEYS = frozenset(
    {
        "session_remaining",
        "weekly_remaining",
    }
)

CREDIT_ONLY_KEYS = frozenset(
    {
        "included_balance",
        "included_allowance",
        "included_period_start",
        "included_period_end",
        "included_period_remaining",
    }
)

COMMON_BALANCE_KEYS = frozenset({"purchased_balance"})


def _available_keys(data: OllamaUsageData) -> set[str]:
    keys: set[str] = set()
    if data.session is not None:
        keys.update(
            {
                "session_requests",
                "session_spend",
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
                "weekly_requests",
                "weekly_spend",
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
                "last_4_weeks_requests",
                "last_4_weeks_spend",
                "last_4_weeks_top_model",
                "last_4_weeks_model_breakdown",
                "last_4_weeks_period_start",
                "last_4_weeks_period_end",
            }
        )
    balance = data.balance
    if balance is not None:
        if balance.is_legacy_plan:
            keys.update(LEGACY_ONLY_KEYS)
        elif balance.is_credit_plan:
            keys.update(CREDIT_ONLY_KEYS)
        if balance.purchased_balance_usd is not None:
            keys.update(COMMON_BALANCE_KEYS)
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
