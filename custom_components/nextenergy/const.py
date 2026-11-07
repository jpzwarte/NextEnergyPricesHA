"""Constants for the NextEnergy integration."""

from datetime import timedelta

DOMAIN = "nextenergy"

CONF_CHEAPEST_HOURS = "cheapest_hours"
DEFAULT_CHEAPEST_HOURS = 3

UPDATE_INTERVAL = timedelta(minutes=15)

# NextEnergy publishes prices per Dutch calendar day.
PRICE_TIMEZONE = "Europe/Amsterdam"

# PriceCostLevel values used by the NextEnergy app.
COST_LEVEL_TOTAL = "TotalPrice"  # all-in: market + purchase fee + energy tax + VAT
COST_LEVEL_MARKET = "MarketPrice"
