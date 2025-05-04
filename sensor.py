from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Nastavení intervalu aktualizace na 2 minuty
SCAN_INTERVAL = timedelta(minutes=2)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]
    async_add_entities(
        [
            SpaTemperatureSensor(client),  # Aktuální teplota
            SpaDesiredTemperatureSensor(client),  # Požadovaná teplota
        ],
        True,
    )

class SpaTemperatureSensor(SensorEntity):
    def __init__(self, client):
        self._client = client
        self._attr_name = "Spa Current Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = True
        self._state = None

    async def async_update(self):
        data = await self._client.getSpa()
        if data:
            fahrenheit_temp = data.get("currentTemp")
            if fahrenheit_temp is not None and fahrenheit_temp != 0:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated current temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state

class SpaDesiredTemperatureSensor(SensorEntity):
    def __init__(self, client):
        self._client = client
        self._attr_name = "Spa Desired Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = True
        self._state = None

    async def async_update(self):
        data = await self._client.getSpa()
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated desired temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state

# class SpaTempRangeSensor(SensorEntity):
#     def __init__(self, client):
#         self._client = client
#         self._attr_name = "Spa Temperature Range"
#         self._attr_should_poll = True
#         self._state = None

#     async def async_update(self):
#         data = await self._client.getSpa()
#         if data:
#             self._state = data.get("tempRange")  # Načtení hodnoty tempRange
#             _LOGGER.debug("Updated temperature range: %s", self._state)

#     @property
#     def native_value(self):
#         return self._state


