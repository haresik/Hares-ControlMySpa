"""Temperature-related sensor entities."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS  # Výchozí hodnota
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.{self._attr_device_info['serial_number']}_spa_current_temperature"
        self._attr_translation_key = f"current_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("currentTemp")
            if fahrenheit_temp is not None and fahrenheit_temp != 0:
                # Nastavit jednotku podle data.get("celsius")
                if data.get("celsius"):
                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                    self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                    _LOGGER.debug("Updated current temperature (Celsius): %s", self._state)
                else:
                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                    self._state = fahrenheit_temp  # Zachovat původní hodnotu ve Fahrenheit
                    _LOGGER.debug("Updated current temperature (Fahrenheit): %s", self._state)

    @property
    def native_value(self):
        return self._state


class SpaDesiredTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS  # Výchozí hodnota
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._high_range_value = None  # Poslední hodnota pro HIGH rozsah
        self._low_range_value = None   # Poslední hodnota pro LOW rozsah
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.{self._attr_device_info['serial_number']}_spa_desired_temperature"
        self._attr_translation_key = f"desired_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            temp_range = data.get("tempRange")
            
            if fahrenheit_temp is not None:
                # Nastavit jednotku podle data.get("celsius")
                if data.get("celsius"):
                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                    celsius_temp = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                    self._state = celsius_temp
                    
                    # Uložit hodnotu podle aktuálního rozsahu
                    if temp_range == "HIGH":
                        self._high_range_value = celsius_temp
                        _LOGGER.debug("Updated desired temperature (Celsius): %s (HIGH range)", self._state)
                    elif temp_range == "LOW":
                        self._low_range_value = celsius_temp
                        _LOGGER.debug("Updated desired temperature (Celsius): %s (LOW range)", self._state)
                    else:
                        _LOGGER.debug("Updated desired temperature (Celsius): %s (unknown range: %s)", self._state, temp_range)
                else:
                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                    # Zachovat původní hodnotu ve Fahrenheit
                    self._state = fahrenheit_temp
                    
                    # Uložit hodnotu podle aktuálního rozsahu
                    if temp_range == "HIGH":
                        self._high_range_value = fahrenheit_temp
                        _LOGGER.debug("Updated desired temperature (Fahrenheit): %s (HIGH range)", self._state)
                    elif temp_range == "LOW":
                        self._low_range_value = fahrenheit_temp
                        _LOGGER.debug("Updated desired temperature (Fahrenheit): %s (LOW range)", self._state)
                    else:
                        _LOGGER.debug("Updated desired temperature (Fahrenheit): %s (unknown range: %s)", self._state, temp_range)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy entity."""
        attrs = {}
        if self._high_range_value is not None:
            attrs["high_range_value"] = self._high_range_value
        if self._low_range_value is not None:
            attrs["low_range_value"] = self._low_range_value
        return attrs

