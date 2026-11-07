"""Tests for the NextEnergy integration."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.nextenergy.api import NextEnergyAuthError
from custom_components.nextenergy.const import CONF_CHEAPEST_HOURS, DOMAIN

from .conftest import TOMORROW, TOMORROW_TOTAL

CREDENTIALS = {"username": "user", "password": "secret"}


async def setup_entry(hass: HomeAssistant, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="203387", data=CREDENTIALS, options=options or {})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    mock_client.login.side_effect = NextEnergyAuthError("Invalid username or password.")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "203387"
    assert result["data"] == CREDENTIALS


async def test_sensors(hass: HomeAssistant, mock_client, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to("2026-11-07 11:44:00+01:00")
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.nextenergy_current_price").state == "0.38"
    assert hass.states.get("sensor.nextenergy_current_market_price").state == "0.25"
    assert hass.states.get("sensor.nextenergy_next_hour_price").state == "0.36"
    assert hass.states.get("sensor.nextenergy_lowest_price_today").state == "0.35"
    assert hass.states.get("sensor.nextenergy_highest_price_today").state == "0.52"
    assert hass.states.get("sensor.nextenergy_gas_price").state == "1.83"
    assert hass.states.get("sensor.nextenergy_cheapest_hour").state == "2026-11-07T12:00:00+00:00"

    attrs = hass.states.get("sensor.nextenergy_current_price").attributes
    assert attrs["unit_of_measurement"] == "€/kWh"
    assert len(attrs["raw_today"]) == 24
    assert attrs["raw_today"][0] == {"start": "2026-11-07T00:00:00+01:00", "end": "2026-11-07T01:00:00+01:00", "value": 0.44}
    assert attrs["tomorrow_valid"] is False

    # Default: 3 cheapest of the remaining hours today (12:00-14:00 local = 0.36, 0.35, 0.37).
    cheapest = hass.states.get("binary_sensor.nextenergy_cheapest_hours")
    assert cheapest.state == "off"
    assert [h["start"] for h in cheapest.attributes["cheapest_hours"]] == [
        "2026-11-07T12:00:00+01:00", "2026-11-07T13:00:00+01:00", "2026-11-07T14:00:00+01:00"]

    # The state follows the clock without a new fetch.
    freezer.move_to("2026-11-07 12:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nextenergy_current_price").state == "0.36"
    assert hass.states.get("binary_sensor.nextenergy_cheapest_hours").state == "on"

    # Tomorrow's prices are picked up on the next poll; cheapest hours move to the night.
    mock_client.published[TOMORROW] = TOMORROW_TOTAL
    freezer.move_to("2026-11-07 14:30:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    attrs = hass.states.get("sensor.nextenergy_current_price").attributes
    assert attrs["tomorrow_valid"] is True
    assert len(attrs["raw_tomorrow"]) == 24
    cheapest = hass.states.get("binary_sensor.nextenergy_cheapest_hours")
    assert cheapest.state == "off"
    assert [h["start"] for h in cheapest.attributes["cheapest_hours"]] == [
        "2026-11-08T03:00:00+01:00", "2026-11-08T04:00:00+01:00", "2026-11-08T05:00:00+01:00"]

    # A published day is cached: today was fetched once per cost level.
    today_calls = [c for c in mock_client.get_day_prices.call_args_list if c.args[0].day == 7]
    assert len(today_calls) == 2


async def test_cheapest_hours_option(hass: HomeAssistant, mock_client, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to("2026-11-07 11:44:00+01:00")
    entry = await setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_CHEAPEST_HOURS: 5})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    cheapest = hass.states.get("binary_sensor.nextenergy_cheapest_hours")
    assert cheapest.attributes["hours"] == 5
    assert cheapest.state == "on"  # 11:00 (0.38) is now among the 5 cheapest


async def test_auth_failure_starts_reauth(hass: HomeAssistant, mock_client) -> None:
    mock_client.get_day_prices.side_effect = NextEnergyAuthError("Invalid username or password.")
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]

    mock_client.get_day_prices.side_effect = None
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"password": "new"})
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["password"] == "new"


async def test_card_is_served_and_registered(hass: HomeAssistant) -> None:
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
    from homeassistant.setup import async_setup_component

    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    assert await async_setup_component(hass, DOMAIN, {})

    (path,) = hass.http.async_register_static_paths.call_args.args[0]
    assert path.url_path == "/nextenergy/nextenergy-price-card.js"
    assert Path(path.path).is_file()
    (url,) = hass.data[DATA_EXTRA_MODULE_URL]
    assert url.startswith("/nextenergy/nextenergy-price-card.js?v=")
