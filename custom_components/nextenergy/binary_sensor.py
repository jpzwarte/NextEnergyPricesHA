"""Cheapest-hours binary sensor for NextEnergy."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import NextEnergyConfigEntry
from .const import CONF_CHEAPEST_HOURS, DEFAULT_CHEAPEST_HOURS
from .coordinator import TZ, NextEnergyCoordinator
from .entity import NextEnergyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NextEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the cheapest-hours binary sensor."""
    count = entry.options.get(CONF_CHEAPEST_HOURS, DEFAULT_CHEAPEST_HOURS)
    async_add_entities([NextEnergyCheapestHours(entry.runtime_data, count)])


class NextEnergyCheapestHours(NextEnergyEntity, BinarySensorEntity):
    """On during the N cheapest hours of the next 24 hours.

    The window rolls with the clock and grows when tomorrow's prices are published,
    so the selection can shift during the day. Use it for loads that can run in
    any hours (e.g. a boiler or charger); for a fixed target such as "80% by 07:00",
    combine the price attributes with EV Smart Charging instead.
    """

    def __init__(self, coordinator: NextEnergyCoordinator, count: int) -> None:
        super().__init__(coordinator, "cheapest_hours")
        self._count = count

    @property
    def is_on(self) -> bool:
        now = dt_util.utcnow()
        return any(p.start <= now < p.end for p in self.coordinator.data.cheapest_hours(now, self._count))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        upcoming = self.coordinator.data.upcoming(now)
        return {
            "hours": self._count,
            "cheapest_hours": [
                {"start": p.start.astimezone(TZ).isoformat(), "value": p.value}
                for p in self.coordinator.data.cheapest_hours(now, self._count)
            ],
            "window_end": upcoming[-1].end.astimezone(TZ).isoformat() if upcoming else None,
        }
