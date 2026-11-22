from __future__ import annotations

import logging
from typing import Any

import aiohttp
import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OllamaApiError, OllamaAuthError, OllamaParseError, fetch_and_parse
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCOPE_SELF,
    SCOPE_TEAM,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_ACCOUNT_NAME, default="Main"): str,
        probatio.Required(CONF_API_KEY): str,
        probatio.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): probatio.All(int, probatio.Range(min=60, max=3600)),
        probatio.Optional(CONF_SCOPE, default=SCOPE_SELF): probatio.In(
            [SCOPE_SELF, SCOPE_TEAM]
        ),
    }
)

STEP_REAUTH_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_API_KEY): str})

STEP_RECONFIGURE_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_API_KEY): str})


async def _async_validate(hass: HomeAssistant, api_key: str) -> str | None:
    session = async_get_clientsession(hass)
    try:
        await fetch_and_parse(session, api_key)
    except OllamaAuthError:
        return "invalid_api_key"
    except OllamaParseError:
        return "parse_error"
    except OllamaApiError:
        return "api_error"
    except (aiohttp.ClientError, TimeoutError):
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error during setup")
        return "unknown"
    return None


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

            error = await _async_validate(self.hass, user_input[CONF_API_KEY])
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_ACCOUNT_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error = await _async_validate(self.hass, user_input[CONF_API_KEY])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={CONF_ACCOUNT_NAME: entry.title},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await _async_validate(self.hass, user_input[CONF_API_KEY])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_RECONFIGURE_DATA_SCHEMA,
            errors=errors,
            description_placeholders={CONF_ACCOUNT_NAME: entry.title},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OllamaCloudUsageOptionsFlow()


class OllamaCloudUsageOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_scope = self.config_entry.options.get(
            CONF_SCOPE,
            self.config_entry.data.get(CONF_SCOPE, SCOPE_SELF),
        )
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_SCAN_INTERVAL, default=current): probatio.All(
                    int, probatio.Range(min=60, max=3600)
                ),
                probatio.Optional(CONF_SCOPE, default=current_scope): probatio.In(
                    [SCOPE_SELF, SCOPE_TEAM]
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
