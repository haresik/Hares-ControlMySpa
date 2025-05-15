from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Nastavení intervalu aktualizace na 2 minuty
SCAN_INTERVAL = timedelta(minutes=60)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    # client = data["client"]
    shared_data = data["data"]
    device_info = data["device_info"]

    # Najít všechny CIRCULATION_PUMP komponenty
    circulation_pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "CIRCULATION_PUMP"
    ]

    # Vytvořit entity pro každou CIRCULATION_PUMP
    entities = [SpaCirculationPumpSensor(shared_data, device_info, pump, len(circulation_pumps)) for pump in circulation_pumps]
    entities.append(SpaTemperatureSensor(shared_data, device_info))  # Aktuální teplota
    entities.append(SpaDesiredTemperatureSensor(shared_data, device_info))  # Požadovaná teplota

    async_add_entities(entities, True)
    _LOGGER.debug("START Śensor control_my_spa")
    
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaSensorBase(SensorEntity):
    _attr_has_entity_name = True

class SpaTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_current_temperature"
        self._attr_translation_key = f"current_temperature"
        self.entity_id = self._attr_unique_id

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

class SpaDesiredTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_desired_temperature"
        self._attr_translation_key = f"desired_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated desired temperature (Celsius): %s", self._state)
                # self.async_write_ha_state()

    @property
    def native_value(self):
        return self._state

class SpaCirculationPumpSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, pump_data, count_pump):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-tornado"
        self._attr_unique_id = f"sensor.spa_circulation_pump" if count_pump == 1 or pump_data['port'] == None else f"sensor.spa_circulation_pump_{pump_data['port']}"
        self._attr_translation_key = f"circulation_pump" if count_pump == 1 or pump_data['port'] == None else f"spa_circulation_pump_{pump_data['port']}"
        self.entity_id = self._attr_unique_id

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
                self._state = pump["value"]  # Stav čerpadla 
                _LOGGER.debug("Updated Circulation Pump %s: %s", self._pump_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

