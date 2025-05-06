from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Nastavení intervalu aktualizace na 2 minuty
SCAN_INTERVAL = timedelta(minutes=2)
DEVICE_INFO = {
    "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
    "name": "Spa Balboa Device",
    "manufacturer": "Balboa",
    "model": "Spa Model 1",
    "sw_version": "1.0",
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]

    # Vytvoření sdíleného objektu pro data
    shared_data = SpaData(client, hass)
    
    # Spustit pravidelnou aktualizaci dat
    shared_data.start_periodic_update(SCAN_INTERVAL)

    # Aktualizace dat pouze jednou
    await shared_data.update()

    # Najít všechny CIRCULATION_PUMP komponenty
    circulation_pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "CIRCULATION_PUMP"
    ]

    # Vytvořit entity pro každou CIRCULATION_PUMP
    entities = [SpaCirculationPumpSensor(shared_data, pump, circulation_pumps.count) for pump in circulation_pumps]
    entities.append(SpaTemperatureSensor(shared_data))  # Aktuální teplota
    entities.append(SpaDesiredTemperatureSensor(shared_data))  # Požadovaná teplota

    async_add_entities(entities, True)

class SpaData:
    """Sdílený objekt pro uchování dat z webového dotazu."""
    def __init__(self, client, hass):
        self._client = client
        self._data = None
        self._hass = hass
        self._subscribers = []  # Seznam odběratelů

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)
        await self._notify_subscribers()  # Notifikace odběratelů

    def start_periodic_update(self, interval):
        """Spustí pravidelnou aktualizaci dat."""
        async_track_time_interval(self._hass, self._periodic_update, interval)

    async def _periodic_update(self, _):
        """Interní metoda pro pravidelnou aktualizaci."""
        await self.update()

    def register_subscriber(self, subscriber):
        """Registrace odběratele."""
        self._subscribers.append(subscriber)

    async def _notify_subscribers(self):
        """Notifikace všech odběratelů."""
        for subscriber in self._subscribers:
            await subscriber.async_update()

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data


class SpaTemperatureSensor(SensorEntity):
    def __init__(self, shared_data):
        self._shared_data = shared_data
        self._attr_name = "Spa Current Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = False  # Data jsou sdílena
        self._state = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = DEVICE_INFO

        # Registrace jako odběratel
        self._shared_data.register_subscriber(self)

    async def async_update(self):
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
        self._attr_should_poll = False  # Data jsou sdílena
        self._state = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = DEVICE_INFO

        # Registrace jako odběratel
        self._shared_data.register_subscriber(self)

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated desired temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state


class SpaCirculationPumpSensor(SensorEntity):
    def __init__(self, shared_data, pump_data, count_pump):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_name = "Spa Circulation Pump" if count_pump == 1 or pump_data['port'] == None else f"Spa Circulation Pump {pump_data['port']}"
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena
        self._state = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"
        self._attr_device_info = DEVICE_INFO

        # Registrace jako odběratel
        self._shared_data.register_subscriber(self)

    async def async_update(self):
        # Data jsou již aktualizována v async_setup_entry
        data = self._shared_data.data
        if data:
            # Najít odpovídající CIRCULATION_PUMP podle portu
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "CIRCULATION_PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            if pump:
                self._state = pump["value"]  # Stav čerpadla (např. ON/OFF)
                _LOGGER.debug("Updated Circulation Pump %s: %s", self._pump_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

