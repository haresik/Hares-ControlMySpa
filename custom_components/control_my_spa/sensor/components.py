"""Component-related sensor entities."""

from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


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


class SpaHeaterSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, heater_data, count_heater):
        self._shared_data = shared_data
        self._heater_data = heater_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:fire"
        self._attr_unique_id = (
            f"sensor.spa_heater"
            if count_heater == 1 or heater_data['port'] is None
            else f"sensor.spa_heater_{int(heater_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "heater"
            if count_heater == 1 or heater_data['port'] is None
            else f"heater_{int(heater_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající HEATER podle portu
            heater_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "HEATER" and comp["port"] == self._heater_data["port"]
                ),
                None,
            )
            if heater_comp:
                self._state = heater_comp["value"]
                _LOGGER.debug("Updated Heater %s: %s", self._heater_data["port"], self._state)
            else:
                # Pokud není nalezena komponenta, nastav stav na OFF
                self._state = "OFF"
        else:
            # Pokud nejsou dostupná data, nastav stav na OFF
            self._state = "OFF"

    @property
    def native_value(self):
        return self._state

