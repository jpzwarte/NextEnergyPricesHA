# NextEnergy for Home Assistant

Brings the dynamic electricity prices from your NextEnergy contract into Home Assistant: the
same hourly prices the NextEnergy app shows on
[MarketPrices](https://mijn.nextenergy.nl/Mobile_EnergyNext/MarketPrices), for today and (once
published, usually early afternoon) tomorrow.

> This uses the private API of the NextEnergy app, logging in with your app credentials. It is
> not an official NextEnergy product and may break when NextEnergy changes its app. The
> integration reads the app's current version identifiers on each login, so ordinary app
> updates are handled automatically.

## Installation

1. In HACS, add this repository as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/)
   (type: Integration) and install **NextEnergy**. Or copy `custom_components/nextenergy` into
   your Home Assistant `config/custom_components` folder.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → NextEnergy**, and log in with your
   NextEnergy app username and password.

## Entities

| Entity | Description |
| --- | --- |
| `sensor.nextenergy_current_price` | All-in price (market + purchase fee + energy tax + VAT) for the current hour, in €/kWh. Its attributes hold all known prices (see below). |
| `sensor.nextenergy_current_market_price` | Market price for the current hour, with the same attributes. |
| `sensor.nextenergy_next_hour_price` | All-in price for the next hour. |
| `sensor.nextenergy_average_price_today` / `lowest_price_today` / `highest_price_today` | Statistics for today's all-in prices. |
| `sensor.nextenergy_cheapest_hour` | Start of the cheapest hour in the next 24 hours (attribute `price`). |
| `sensor.nextenergy_gas_price` | Today's all-in gas price in €/m³ (attribute `market_price`). |
| `binary_sensor.nextenergy_cheapest_hours` | On during the N cheapest hours of the next 24 hours. N defaults to 3 and can be changed under **Configure** on the integration. Attribute `cheapest_hours` lists the selected hours. |

The price sensors have the same attributes as the Nord Pool integration (`today`,
`tomorrow`, `tomorrow_valid`, `raw_today`, `raw_tomorrow`), so tools made for Nord Pool, such
as [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging), work with
them directly:

```yaml
raw_today:
  - start: "2026-11-07T00:00:00+01:00"
    end: "2026-11-07T01:00:00+01:00"
    value: 0.44
  # ...
```

NextEnergy rounds the prices to whole cents, so several hours often share the same price; the
cheapest-hours selection then prefers the earliest hour.

`sensor.nextenergy_current_price` can also be used as the electricity price in the
Energy dashboard.

## Price card

The integration includes a dashboard card showing today's or tomorrow's hourly prices, the
selected hour's price relative to the day average, and the day's average, cheapest and most
expensive hour. It is loaded automatically; add it from the card picker (**NextEnergy
prijzen**) or with:

```yaml
type: custom:nextenergy-price-card
```

Tap or hover a bar to see that hour. Optional settings:

```yaml
type: custom:nextenergy-price-card
entity: sensor.nextenergy_current_price  # or sensor.nextenergy_current_market_price
decimals: 2                              # decimals of the hourly prices
```

## Automations

Switch a charger (or boiler, heat pump, ...) on during the cheapest hours:

```yaml
alias: Charger on during cheapest hours
triggers:
  - trigger: state
    entity_id: binary_sensor.nextenergy_cheapest_hours
    to: ["on", "off"]
actions:
  - action: switch.turn_{{ trigger.to_state.state }}
    target:
      entity_id: switch.charger
mode: single
```

Or whenever the price drops below a threshold:

```yaml
alias: Charger on when electricity is cheap
triggers:
  - trigger: numeric_state
    entity_id: sensor.nextenergy_current_price
    below: 0.30
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.charger
```

For "charge the car to 80% by 07:00 at the lowest cost", use EV Smart Charging with
`sensor.nextenergy_current_price` as its price sensor.

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```

## License

MIT
