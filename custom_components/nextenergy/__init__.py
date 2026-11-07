"""The NextEnergy integration."""

from __future__ import annotations

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import NextEnergyClient
from .coordinator import NextEnergyCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type NextEnergyConfigEntry = ConfigEntry[NextEnergyCoordinator]


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
