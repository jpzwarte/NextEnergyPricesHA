"""Fixtures for NextEnergy tests."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.nextenergy.api import DayPrices
from custom_components.nextenergy.const import COST_LEVEL_MARKET

TODAY = date(2026, 11, 7)
TOMORROW = date(2026, 11, 8)

# UTC hour labels as NextEnergy returns them: local midnight (CET) is 23:00 UTC.
LABELS = [23, *range(23)]
TODAY_TOTAL = [0.44, 0.43, 0.42, 0.41, 0.41, 0.42, 0.42, 0.43, 0.44, 0.42, 0.40, 0.38,
               0.36, 0.35, 0.37, 0.40, 0.45, 0.50, 0.52, 0.49, 0.48, 0.45, 0.42, 0.40]
TOMORROW_TOTAL = [0.39, 0.37, 0.33, 0.31, 0.30, 0.32, 0.36, 0.41, 0.43, 0.40, 0.38, 0.36,
                  0.35, 0.34, 0.36, 0.39, 0.44, 0.49, 0.51, 0.48, 0.46, 0.44, 0.41, 0.39]


def day_prices(values, offset=0.0, gas=1.83):
    return DayPrices(electricity=[(h, round(v - offset, 2)) for h, v in zip(LABELS, values)], gas=gas)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in every test."""


@pytest.fixture
def mock_client():
    """A NextEnergyClient whose network calls are mocked."""
    published = {TODAY: TODAY_TOTAL}

    async def get_day_prices(day, level):
        values = published.get(day)
        if values is None:
            return DayPrices(electricity=[], gas=None)
        if level == COST_LEVEL_MARKET:
            return day_prices(values, offset=0.13, gas=1.03)
        return day_prices(values)

    client = AsyncMock()
    client.login.return_value = "203387"
    client.get_day_prices.side_effect = get_day_prices
    client.published = published
    with (
        patch("custom_components.nextenergy.NextEnergyClient", return_value=client),
        patch("custom_components.nextenergy.config_flow.NextEnergyClient", return_value=client),
    ):
        yield client
