from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.const import (
    CONF_COOKIE,
    CONF_SCAN_INTERVAL,
    CONF_USAGE_MODE,
    DOMAIN,
    USAGE_MODE_LEGACY,
)
from custom_components.ollama_cloud_usage.scraper import OllamaUsageData


async def test_upgrade_legacy_to_monthly_removes_legacy_sensors(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main Account",
        data={
            CONF_COOKIE: "test_cookie_value",
            CONF_SCAN_INTERVAL: 60,
            CONF_USAGE_MODE: USAGE_MODE_LEGACY,
        },
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    legacy_unique_ids = [
        f"{entry.entry_id}_session_usage",
        f"{entry.entry_id}_session_remaining",
        f"{entry.entry_id}_session_resets_in",
        f"{entry.entry_id}_weekly_usage",
        f"{entry.entry_id}_weekly_remaining",
        f"{entry.entry_id}_weekly_resets_in",
    ]
    for uid in legacy_unique_ids:
        registry.async_get_or_create(
            domain="sensor",
            platform=DOMAIN,
            unique_id=uid,
            suggested_object_id=f"ollama_{uid.split('_', 1)[1]}",
        )

    for uid in legacy_unique_ids:
        eid = registry.async_get_entity_id("sensor", DOMAIN, uid)
        assert eid is not None

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        AsyncMock(
            return_value=OllamaUsageData(
                monthly_percent=44.3,
                monthly_resets_in="3 weeks",
                monthly_resets_at="2026-10-01T21:51:07Z",
                tier="free",
                model_note="gemma4:31b, 331 requests",
            )
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for uid in legacy_unique_ids:
        eid = registry.async_get_entity_id("sensor", DOMAIN, uid)
        assert eid is None

    monthly_unique_ids = [
        f"{entry.entry_id}_monthly_usage",
        f"{entry.entry_id}_monthly_remaining",
        f"{entry.entry_id}_monthly_resets_in",
        f"{entry.entry_id}_monthly_resets_at",
        f"{entry.entry_id}_tier",
        f"{entry.entry_id}_model_info",
    ]
    for uid in monthly_unique_ids:
        eid = registry.async_get_entity_id("sensor", DOMAIN, uid)
        assert eid is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_fresh_install_on_monthly_model_only_creates_monthly(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Fresh Account",
        data={
            CONF_COOKIE: "fresh_cookie",
            CONF_SCAN_INTERVAL: 60,
            CONF_USAGE_MODE: USAGE_MODE_LEGACY,
        },
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        AsyncMock(
            return_value=OllamaUsageData(
                monthly_percent=44.3,
                monthly_resets_in="3 weeks",
                tier="free",
                model_note="gemma4:31b, 331 requests",
            )
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    legacy_unique_ids = [
        f"{entry.entry_id}_session_usage",
        f"{entry.entry_id}_weekly_usage",
    ]
    for uid in legacy_unique_ids:
        eid = registry.async_get_entity_id("sensor", DOMAIN, uid)
        assert eid is None

    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_monthly_usage"
        )
        is not None
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_fresh_install_on_legacy_model_only_creates_legacy(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pro Account",
        data={
            CONF_COOKIE: "pro_cookie",
            CONF_SCAN_INTERVAL: 60,
            CONF_USAGE_MODE: USAGE_MODE_LEGACY,
        },
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        AsyncMock(
            return_value=OllamaUsageData(
                session_percent=4.2,
                session_resets_in="4 hours",
                weekly_percent=1.1,
                weekly_resets_in="3 days",
                tier="pro",
                model_note="minimax-m3, 110 requests",
            )
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_session_usage"
        )
        is not None
    )
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_weekly_usage")
        is not None
    )
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_monthly_usage"
        )
        is None
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
