"""Config flow for NextEnergy."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import NextEnergyAuthError, NextEnergyClient, NextEnergyError
from .const import CONF_CHEAPEST_HOURS, DEFAULT_CHEAPEST_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class NextEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NextEnergy."""

    VERSION = 1

    async def _validate(self, username: str, password: str) -> tuple[str | None, dict[str, str]]:
        """Log in; returns the contract id, or errors for the form."""
        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
                contract_id = await NextEnergyClient(session, username, password).login()
        except NextEnergyAuthError:
            return None, {"base": "invalid_auth"}
        except NextEnergyError:
            _LOGGER.exception("Could not connect to NextEnergy")
            return None, {"base": "cannot_connect"}
        return contract_id, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the NextEnergy app credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            contract_id, errors = await self._validate(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if contract_id:
                await self.async_set_unique_id(contract_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="NextEnergy", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the credentials were rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            contract_id, errors = await self._validate(
                entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if contract_id:
                await self.async_set_unique_id(contract_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return NextEnergyOptionsFlow()


class NextEnergyOptionsFlow(OptionsFlow):
    """Options for NextEnergy."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_CHEAPEST_HOURS: int(user_input[CONF_CHEAPEST_HOURS])}
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHEAPEST_HOURS,
                        default=self.config_entry.options.get(
                            CONF_CHEAPEST_HOURS, DEFAULT_CHEAPEST_HOURS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=12, step=1, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
