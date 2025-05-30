from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
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

    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    # Najít všechny LIGHT komponenty
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT"
    ]

    # Vytvořit entity pro každou PUMP
    entities = []
    # entities = [SpaPumpSelect(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    # entities += [SpaBlowerSelect(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    # entities += [SpaLightSelect(shared_data, device_info, light, len(lights)) for light in lights]
    entities.append(SpaTempRangeSelect(shared_data, device_info))  # Přidat entitu
    entities.append(SpaHeaterModeSelect(shared_data, device_info))  # Přidat entitu pro heater mode


    async_add_entities(entities, True)
    _LOGGER.debug("START Select control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Select (%s) (%s) ", entity._attr_unique_id, entity.entity_id)

class SpaSelectBase(SelectEntity):
    _attr_has_entity_name = True

class SpaTempRangeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:pool-thermometer"
        self._attr_unique_id = f"select.spa_temperature_range"
        self._attr_translation_key = f"temperature_range"
        self.entity_id = self._attr_unique_id
 
    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_current_option = data.get("tempRange")
            _LOGGER.debug("Updated tempRange: %s", self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty tempRange a odeslání do zařízení."""
        if option in self._attr_options:
            success = await self._shared_data._client.setTempRange(option == "HIGH")
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set tempRange to %s", option)
            else:
                _LOGGER.error("Failed to set tempRange to %s", option)
            await self._shared_data.async_force_update()

class SpaPumpSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_options = pump_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_unique_id = f"select.spa_pump" if pump_count == 1 or pump_data['port'] == None else f"select.spa_pump_{int(pump_data['port']) + 1}"
        self._attr_translation_key = f"pump" if pump_count == 1 or pump_data['port'] == None else f"pump_{int(pump_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající PUMP podle portu
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            if pump:
                self._attr_current_option = pump["value"]
                _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty PUMP a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._pump_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Pump: %s", self._pump_data["port"])
                return

            # Simulace odeslání příkazu do zařízení
            success = await self._shared_data._client.setJetState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Pump %s to %s", self._pump_data["port"], option)
            else:
                _LOGGER.error("Failed to set Pump %s to %s", self._pump_data["port"], option)
            await self._shared_data.async_force_update()

class SpaLightSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_options = light_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_unique_id = f"select.spa_light" if light_count == 1 or light_data['port'] == None else f"select.spa_light_{int(light_data['port']) + 1}"
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající LIGHT podle portu
            light = next(
                (comp for comp in data["components"] if comp["componentType"] == "LIGHT" and comp["port"] == self._light_data["port"]),
                None
            )
            if light:
                self._attr_current_option = light["value"]
                _LOGGER.debug("Updated Light %s: %s", self._light_data["port"], self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty LIGHT a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._light_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Light: %s", self._light_data["port"])
                return

            success = await self._shared_data._client.setLightState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Light %s to %s", self._light_data["port"], option)
            else:
                _LOGGER.error("Failed to set Light %s to %s", self._light_data["port"], option)
            await self._shared_data.async_force_update()

class SpaBlowerSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_options = blower_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = f"select.spa_blower" if blower_count == 1 or blower_data['port'] == None else f"select.spa_blower_{int(blower_data['port']) + 1}"
        self._attr_translation_key = f"blower" if blower_count == 1 or blower_data['port'] == None else f"blower_{int(blower_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající BLOWER podle portu
            blower = next(
                (comp for comp in data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            if blower:
                self._attr_current_option = blower["value"]
                _LOGGER.debug("Updated Blower %s: %s", self._blower_data["port"], self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty BLOWER a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._blower_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Blower: %s", self._blower_data["port"])
                return

            # Simulace odeslání příkazu do zařízení
            success = await self._shared_data._client.setBlowerState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Blower %s to %s", self._blower_data["port"], option)
            else:
                _LOGGER.error("Failed to set Blower %s to %s", self._blower_data["port"], option)
            await self._shared_data.async_force_update()

class SpaHeaterModeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_options = ["READY", "REST", "READY_IN_REST"]  
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:radiator"
        self._attr_unique_id = f"select.spa_heater_mode"
        self._attr_translation_key = f"heater_mode"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_current_option = data.get("heaterMode")
            _LOGGER.debug("Updated heaterMode: %s", self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty heaterMode a odeslání do zařízení."""
        if option in self._attr_options:
            success = await self._shared_data._client.setHeaterMode(option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set heaterMode to %s", option)
            else:
                _LOGGER.error("Failed to set heaterMode to %s", option)
            await self._shared_data.async_force_update()
