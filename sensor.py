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

    # Vytvoření sdíleného objektu pro data
    shared_data = SpaData(client)

    async_add_entities(
        [
            SpaTemperatureSensor(shared_data),  # Aktuální teplota
            SpaDesiredTemperatureSensor(shared_data),  # Požadovaná teplota
        ],
        True,
    )

class SpaData:
    """Sdílený objekt pro uchování dat z webového dotazu."""
    def __init__(self, client):
        self._client = client
        self._data = None

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data

class SpaTemperatureSensor(SensorEntity):
    def __init__(self, shared_data):
        self._shared_data = shared_data
        self._attr_name = "Spa Current Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = True
        self._state = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("currentTemp")
            if fahrenheit_temp is not None and fahrenheit_temp != 0:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated current temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state

class SpaDesiredTemperatureSensor(SensorEntity):
    def __init__(self, shared_data):
        self._shared_data = shared_data
        self._attr_name = "Spa Desired Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = True
        self._state = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated desired temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state

