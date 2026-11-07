"""Price sensors for NextEnergy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import NextEnergyConfigEntry
from .coordinator import TZ, NextEnergyData, PricePoint
from .entity import NextEnergyEntity

PRICE_PER_KWH = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
PRICE_PER_M3 = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"


def _value(point: PricePoint | None) -> float | None:
    return point.value if point else None


def _today_values(data: NextEnergyData, now: datetime) -> list[float]:
    return [p.value for p in data.for_day(now.astimezone(TZ).date())]


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _price_attributes(data: NextEnergyData, now: datetime, market: bool) -> dict[str, Any]:
    """Price lists in the format of the Nord Pool integration.

    Tools built for Nord Pool (EV Smart Charging, cheapest-hours templates, ApexCharts
    examples) read ``raw_today``/``raw_tomorrow`` and work with these sensors as-is.
    """
    today = now.astimezone(TZ).date()
    tomorrow = today + timedelta(days=1)

    def raw(points: list[PricePoint]) -> list[dict[str, Any]]:
        return [
            {"start": p.start.astimezone(TZ).isoformat(), "end": p.end.astimezone(TZ).isoformat(), "value": p.value}
            for p in points
        ]

    today_points = data.for_day(today, market)
    tomorrow_points = data.for_day(tomorrow, market)
    return {
        "today": [p.value for p in today_points],
        "tomorrow": [p.value for p in tomorrow_points],
        "tomorrow_valid": bool(tomorrow_points),
        "raw_today": raw(today_points),
        "raw_tomorrow": raw(tomorrow_points),
    }


@dataclass(frozen=True, kw_only=True)
class NextEnergySensorDescription(SensorEntityDescription):
    """Describes a NextEnergy sensor."""

    value_fn: Callable[[NextEnergyData, datetime], float | datetime | None]
    attributes_fn: Callable[[NextEnergyData, datetime], dict[str, Any]] | None = None


def _price_sensor(key: str, value_fn, attributes_fn=None, **kwargs) -> NextEnergySensorDescription:
    return NextEnergySensorDescription(
        key=key,
        native_unit_of_measurement=PRICE_PER_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=value_fn,
        attributes_fn=attributes_fn,
        **kwargs,
    )


SENSORS: tuple[NextEnergySensorDescription, ...] = (
    _price_sensor(
        "current_price",
        lambda data, now: _value(data.at(now)),
        lambda data, now: _price_attributes(data, now, market=False),
    ),
    _price_sensor(
        "current_market_price",
        lambda data, now: _value(data.at(now, market=True)),
        lambda data, now: _price_attributes(data, now, market=True),
    ),
    _price_sensor(
        "next_hour_price",
        lambda data, now: _value(data.at(now + timedelta(hours=1))),
    ),
    _price_sensor(
        "average_price_today",
        lambda data, now: _average(_today_values(data, now)),
    ),
    _price_sensor(
        "lowest_price_today",
        lambda data, now: min(_today_values(data, now), default=None),
    ),
    _price_sensor(
        "highest_price_today",
        lambda data, now: max(_today_values(data, now), default=None),
    ),
    NextEnergySensorDescription(
        key="cheapest_hour",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, now: c[0].start if (c := data.cheapest_hours(now, 1)) else None,
        attributes_fn=lambda data, now: {
            "price": c[0].value if (c := data.cheapest_hours(now, 1)) else None
        },
    ),
    NextEnergySensorDescription(
        key="gas_price",
        native_unit_of_measurement=PRICE_PER_M3,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data, now: data.gas_total,
        attributes_fn=lambda data, now: {"market_price": data.gas_market},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NextEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NextEnergy sensors."""
    coordinator = entry.runtime_data
    async_add_entities(NextEnergySensor(coordinator, description) for description in SENSORS)


class NextEnergySensor(NextEnergyEntity, SensorEntity):
    """A NextEnergy price sensor."""

    entity_description: NextEnergySensorDescription

    def __init__(self, coordinator, description: NextEnergySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data, dt_util.utcnow())
