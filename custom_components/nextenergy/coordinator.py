"""Data coordinator for NextEnergy prices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import DayPrices, NextEnergyAuthError, NextEnergyClient, NextEnergyError
from .const import COST_LEVEL_MARKET, COST_LEVEL_TOTAL, DOMAIN, PRICE_TIMEZONE, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

TZ = ZoneInfo(PRICE_TIMEZONE)


@dataclass(frozen=True)
class PricePoint:
    """Price for one hour."""

    start: datetime
    end: datetime
    value: float


@dataclass
class NextEnergyData:
    """Known prices, oldest first, covering today and (once published) tomorrow."""

    total: list[PricePoint] = field(default_factory=list)
    market: list[PricePoint] = field(default_factory=list)
    gas_total: float | None = None
    gas_market: float | None = None

    def prices(self, market: bool = False) -> list[PricePoint]:
        """All known prices at the requested cost level."""
        return self.market if market else self.total

    def at(self, moment: datetime, market: bool = False) -> PricePoint | None:
        """The price covering ``moment``."""
        return next((p for p in self.prices(market) if p.start <= moment < p.end), None)

    def for_day(self, day: date, market: bool = False) -> list[PricePoint]:
        """Prices of a Dutch calendar day."""
        return [p for p in self.prices(market) if p.start.astimezone(TZ).date() == day]

    def upcoming(self, now: datetime, hours: int = 24) -> list[PricePoint]:
        """Known prices from the current hour up to ``hours`` ahead."""
        until = now + timedelta(hours=hours)
        return [p for p in self.total if p.end > now and p.start < until]

    def cheapest_hours(self, now: datetime, count: int) -> list[PricePoint]:
        """The ``count`` cheapest hours of the next 24 hours, in chronological order.

        Ties (prices are rounded to whole cents) go to the earliest hour.
        """
        cheapest = sorted(self.upcoming(now), key=lambda p: (p.value, p.start))[:count]
        return sorted(cheapest, key=lambda p: p.start)


def to_points(day: date, prices: DayPrices) -> list[PricePoint]:
    """Attach timestamps to a day's hourly prices.

    NextEnergy labels each hour with its UTC hour, starting at local midnight, so the
    23 or 25 hours of DST transition days are handled by counting from midnight.
    """
    start = datetime.combine(day, datetime.min.time(), TZ).astimezone(dt_util.UTC)
    points = []
    for index, (utc_hour, value) in enumerate(prices.electricity):
        hour_start = start + timedelta(hours=index)
        if hour_start.hour != utc_hour:
            _LOGGER.warning(
                "Unexpected hour label %s for %s (expected %s)", utc_hour, day, hour_start.hour
            )
        points.append(PricePoint(hour_start, hour_start + timedelta(hours=1), value))
    return points


class NextEnergyCoordinator(DataUpdateCoordinator[NextEnergyData]):
    """Fetches today's and tomorrow's prices.

    A day's prices are final once published, so each day is fetched once and then
    served from cache; the periodic update mainly waits for tomorrow's prices
    (published early in the afternoon).
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: NextEnergyClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._cache: dict[tuple[date, str], DayPrices] = {}

        # Prices are hourly; refresh the entities at the start of every hour.
        entry.async_on_unload(
            async_track_utc_time_change(hass, self._hour_changed, minute=0, second=0)
        )

    @callback
    def _hour_changed(self, _now: datetime) -> None:
        if self.data is not None:
            self.async_update_listeners()

    async def _async_update_data(self) -> NextEnergyData:
        today = dt_util.now(TZ).date()
        days = (today, today + timedelta(days=1))
        self._cache = {key: value for key, value in self._cache.items() if key[0] in days}

        try:
            for day in days:
                for level in (COST_LEVEL_TOTAL, COST_LEVEL_MARKET):
                    if (day, level) not in self._cache:
                        prices = await self.client.get_day_prices(day, level)
                        if prices.electricity:
                            self._cache[(day, level)] = prices
        except NextEnergyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NextEnergyError as err:
            raise UpdateFailed(f"Error fetching NextEnergy prices: {err}") from err

        if (today, COST_LEVEL_TOTAL) not in self._cache:
            raise UpdateFailed(f"NextEnergy returned no prices for {today}")

        def points(level: str) -> list[PricePoint]:
            return [
                point
                for day in days
                if (day, level) in self._cache
                for point in to_points(day, self._cache[(day, level)])
            ]

        total_today = self._cache[(today, COST_LEVEL_TOTAL)]
        market_today = self._cache.get((today, COST_LEVEL_MARKET))
        return NextEnergyData(
            total=points(COST_LEVEL_TOTAL),
            market=points(COST_LEVEL_MARKET),
            gas_total=total_today.gas,
            gas_market=market_today.gas if market_today else None,
        )
