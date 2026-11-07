"""Base entity for NextEnergy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NextEnergyCoordinator


class NextEnergyEntity(CoordinatorEntity[NextEnergyCoordinator]):
    """An entity backed by the NextEnergy coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NextEnergyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name="NextEnergy",
            manufacturer="NextEnergy",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://mijn.nextenergy.nl/Mobile_EnergyNext/MarketPrices",
        )
