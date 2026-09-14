from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OllamaApiError, OllamaAuthError, OllamaParseError, fetch_and_parse
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_NAME, default="Main"): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=60, max=3600)
        ),
    }
)


class OllamaCloudUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                user_input[CONF_ACCOUNT_NAME].lower().strip()
            )
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            try:
                await fetch_and_parse(session, user_input[CONF_API_KEY])
            except OllamaAuthError:
                errors["base"] = "invalid_api_key"
            except OllamaParseError:
                errors["base"] = "parse_error"
            except OllamaApiError:
                errors["base"] = "api_error"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_ACCOUNT_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
