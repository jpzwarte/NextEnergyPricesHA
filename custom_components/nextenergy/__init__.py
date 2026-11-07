"""The NextEnergy integration."""

from __future__ import annotations

from pathlib import Path

import aiohttp

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import NextEnergyClient
from .const import DOMAIN
from .coordinator import NextEnergyCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_FILE = Path(__file__).parent / "frontend" / "nextenergy-price-card.js"
CARD_URL = f"/{DOMAIN}/nextenergy-price-card.js"

type NextEnergyConfigEntry = ConfigEntry[NextEnergyCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the price card and load it in the frontend, so no dashboard resource is needed."""
    if hass.http is None or DATA_EXTRA_MODULE_URL not in hass.data:
        return True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    integration = await async_get_integration(hass, DOMAIN)
    # The version busts the browser cache after an update.
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NextEnergyConfigEntry) -> bool:
    """Set up NextEnergy from a config entry."""
    # The NextEnergy session lives in cookies, so it needs a cookie jar of its own.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    client = NextEnergyClient(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = NextEnergyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NextEnergyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: NextEnergyConfigEntry) -> None:
    """Reload after the options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
