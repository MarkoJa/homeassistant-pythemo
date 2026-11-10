"""Module containing the sensor entities for the Themo integration."""

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import DOMAIN
from .helpers import async_setup_device

_LOGGER = logging.getLogger(__name__)

POWER_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="power",
    name="Power",
    native_unit_of_measurement=UnitOfPower.KILO_WATT,
    state_class=SensorStateClass.MEASUREMENT,
    device_class=SensorDeviceClass.POWER,
)

ENERGY_TODAY_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="energy_today",
    name="Energy today",
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    device_class=SensorDeviceClass.ENERGY,
    suggested_display_precision=2,
)

TEMPERATURE_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="temperature",
    name="Temperature",
    native_unit_of_measurement="°C",
    state_class=SensorStateClass.MEASUREMENT,
    device_class=SensorDeviceClass.TEMPERATURE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Themo sensor platform from a config entry."""
    await async_setup_device(
        hass,
        entry,
        async_add_entities,
        [
            ThemoPowerSensor,
            ThemoEnergyTodaySensor,
            ThemoFloorTemperatureSensor,
            ThemoRoomTemperatureSensor,
        ],
    )


class ThemoPowerSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Themo Power Sensor."""

    entity_description: SensorEntityDescription = POWER_SENSOR_DESCRIPTION

    def __init__(
        self, device: Any, coordinator: DataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        """Initialize the power sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{device.name} {POWER_SENSOR_DESCRIPTION.name}"
        self._attr_unique_id = f"{device.device_id}_{POWER_SENSOR_DESCRIPTION.key}"
        self._attr_device_info = device_info

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self._device.power * self._device.max_power * 1e3


class ThemoEnergyTodaySensor(CoordinatorEntity, SensorEntity):
    """Today's energy from the imported hourly statistics.

    Hours appear once the Themo cloud has reported them, so the value lags
    behind by about an hour. Yesterday's total is the last_period attribute,
    like a utility meter's.
    """

    entity_description: SensorEntityDescription = ENERGY_TODAY_SENSOR_DESCRIPTION

    def __init__(
        self, device: Any, coordinator: DataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{device.name} {ENERGY_TODAY_SENSOR_DESCRIPTION.name}"
        self._attr_unique_id = (
            f"{device.device_id}_{ENERGY_TODAY_SENSOR_DESCRIPTION.key}"
        )
        self._attr_device_info = device_info

    @property
    def _daily(self) -> tuple[float, float] | None:
        return self.hass.data[DOMAIN].get("daily_energy", {}).get(self._device.id)

    @property
    def native_value(self) -> float | None:
        """Return today's energy."""
        return daily[0] if (daily := self._daily) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return yesterday's energy."""
        return {"last_period": daily[1]} if (daily := self._daily) else None


class ThemoFloorTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Themo Floor Temperature Sensor."""

    entity_description: SensorEntityDescription = TEMPERATURE_SENSOR_DESCRIPTION

    def __init__(
        self, device: Any, coordinator: DataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        """Initialize the floor temperature sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{device.name} floor temperature"
        self._attr_unique_id = (
            f"{device.device_id}_floor_{TEMPERATURE_SENSOR_DESCRIPTION.key}"
        )
        self._attr_device_info = device_info

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self._device.floor_temperature


class ThemoRoomTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Themo Room Temperature Sensor."""

    entity_description: SensorEntityDescription = TEMPERATURE_SENSOR_DESCRIPTION

    def __init__(
        self, device: Any, coordinator: DataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        """Initialize the room temperature sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = f"{device.name} room temperature"
        self._attr_unique_id = (
            f"{device.device_id}_room_{TEMPERATURE_SENSOR_DESCRIPTION.key}"
        )
        self._attr_device_info = device_info

    @property
    def state(self) -> float:
        """Return the state of the sensor."""
        return self._device.room_temperature
