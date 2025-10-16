from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    # client = data["client"]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny CIRCULATION_PUMP komponenty
    circulation_pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "CIRCULATION_PUMP"
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]
    # Najít všechny OZONE komponenty
    ozones = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "OZONE"
    ]
    
    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])

    # Vytvořit entity pro každou CIRCULATION_PUMP
    entities = [SpaCirculationPumpSensor(shared_data, device_info, pump, len(circulation_pumps)) for pump in circulation_pumps]
    entities.append(SpaTemperatureSensor(shared_data, device_info))  # Aktuální teplota
    entities.append(SpaDesiredTemperatureSensor(shared_data, device_info))  # Požadovaná teplota
    entities += [SpaFilterSensor(shared_data, device_info, filter_data, len(filters)) for filter_data in filters]
    entities += [SpaOzoneSensor(shared_data, device_info, ozone_data, len(ozones)) for ozone_data in ozones]

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
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS  # Výchozí hodnota
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
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._high_range_value = None  # Poslední hodnota pro HIGH rozsah
        self._low_range_value = None   # Poslední hodnota pro LOW rozsah
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_desired_temperature"
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

class SpaFilterSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, filter_data, count_filter):
        self._shared_data = shared_data
        self._filter_data = filter_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:water-sync"
        self._attr_unique_id = (
            f"sensor.spa_filter"
            if count_filter == 1 or filter_data['port'] is None
            else f"sensor.spa_filter_{int(filter_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "filter"
            if count_filter == 1 or filter_data['port'] is None
            else f"filter_{int(filter_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající FILTER podle portu
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            if filter_comp:
                self._state = filter_comp["value"]
                _LOGGER.debug("Updated Filter %s: %s", self._filter_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající FILTER podle portu
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            if filter_comp:
                attrs = {
                    "Start time": f"{filter_comp['hour']} : {str(filter_comp['minute']).zfill(2)}",
                    "Duration ": filter_comp["durationMinutes"],
                }
                return attrs

class SpaOzoneSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, ozone_data, count_ozone):
        self._shared_data = shared_data
        self._ozone_data = ozone_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-hazy"
        self._attr_unique_id = (
            f"sensor.spa_ozone"
            if count_ozone == 1 or ozone_data['port'] is None
            else f"sensor.spa_ozone_{int(ozone_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "ozone"
            if count_ozone == 1 or ozone_data['port'] is None
            else f"ozone_{int(ozone_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající OZONE podle portu
            ozone_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "OZONE" and comp["port"] == self._ozone_data["port"]
                ),
                None,
            )
            if ozone_comp:
                self._state = ozone_comp["value"]
                _LOGGER.debug("Updated Ozone %s: %s", self._ozone_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

