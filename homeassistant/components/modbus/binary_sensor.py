"""Support for Modbus Coil and Discrete Input sensors."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import CONF_BINARY_SENSORS, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_hub
from .base_platform import BasePlatform

PARALLEL_UPDATES = 1
_LOGGER = logging.getLogger(__name__)


def _create_virtual(sensor_name, device_class, count, names):
    """Create virtual sensors."""
    if count is None:
        count = 0
    if names is None:
        names = []
    for i in range(len(names) + 1, count + 1):
        names.append(f"{sensor_name}_{i}")
    virtual_sensors = []
    for name in names:
        virtual_sensors.append(virtualBinarySensor(name, device_class))
    return virtual_sensors


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Modbus binary sensors."""
    sensors = []

    if discovery_info is None:  # pragma: no cover
        return

    for entry in discovery_info[CONF_BINARY_SENSORS]:
        hub = get_hub[discovery_info[CONF_NAME]]
        virtual_sensors = _create_virtual(
            entry[CONF_NAME],
            entry.get(CONF_DEVICE_CLASS),
            entry.get(CONF_VIRTUAL_COUNT),
            entry.get(CONF_VIRTUAL_NAMES),
        )
        sensors.append(ModbusBinarySensor(hub, entry, virtual_sensors))
        sensors.extend(virtual_sensors)

    async_add_entities(sensors)


class ModbusBinarySensor(BasePlatform, RestoreEntity, BinarySensorEntity):
    """Modbus binary sensor."""

    def __init__(self, hub, entry, virtual_sensors):
        """Initialize the Modbus binary sensor."""
        if len(virtual_sensors) == 0:
            self._virtual_sensors = None
        else:
            self._virtual_sensors = virtual_sensors

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await self.async_base_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            self._attr_is_on = state.state == STATE_ON

    async def async_update(self, now: datetime | None = None) -> None:
        """Update the state of the sensor."""

        # do not allow multiple active calls to the same platform
        if self._call_active:
            return
        self._call_active = True
        result = await self._hub.async_pymodbus_call(
            self._slave, self._address, 1, self._input_type
        )
        self._call_active = False
        if result is None:
            if self._lazy_errors:
                self._lazy_errors -= 1
                return
            self._lazy_errors = self._lazy_error_count
            self._attr_available = False
            if self._virtual_sensors:
                for entry in self._virtual_sensors:
                    entry.set_from_master(self._value, self._available)
            self.async_write_ha_state()
            return

        self._lazy_errors = self._lazy_error_count
        self._attr_is_on = result.bits[0] & 1
        self._attr_available = True
        if self._virtual_sensors:
            for entry in self._virtual_sensors:
                entry.set_from_master(self._value, self._available)
        self.schedule_update_ha_state()
        self.async_write_ha_state()


class virtualBinarySensor(BinarySensorEntity):
    """Modbus virtual binary sensor."""

    def __init__(self, name, device_class):
        """Initialize the Modbus binary sensor."""
        self._name = name
        self._device_class = device_class
        self._state = None
        self._available = True

    async def async_added_to_hass(self):
        """Handle entity which will be added."""

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def is_on(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_class(self) -> str | None:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    def set_from_master(self, state, available):
        """Update the state of the sensor."""
        self._state = state
        self._available = available
        self.schedule_update_ha_state()
