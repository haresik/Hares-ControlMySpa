from ast import Await
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]

    # Najít všechny LIGHT komponenty
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT"
    ]
    # Najít všechny PUMP komponenty
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]

    entities = [SpaLightSwitch(shared_data, device_info, light, len(lights)) for light in lights]
    entities += [SpaPumpSwitch(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSwitch(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    
    async_add_entities(entities, True)
    _LOGGER.debug("START Switch control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Switch (%s) (%s)", entity._attr_unique_id, entity.entity_id)

class SpaSwitchBase(SwitchEntity):
    _attr_has_entity_name = True

class SpaLightSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_light"
            if light_count == 1 or light_data['port'] is None
            else f"switch.spa_light_{int(light_data['port']) + 1}"
        )
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id

    @property
    def icon(self):
        if self.is_on:
            return "mdi:lightbulb-on"
        else:
            return "mdi:lightbulb"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            light = next(
                (comp for comp in data["components"] if comp["componentType"] == "LIGHT" and comp["port"] == self._light_data["port"]),
                None
            )
            _LOGGER.debug("Updated Light %s: %s", self._light_data["port"], light["value"])
            if light:
                self._attr_is_on = light["value"] == "HIGH"
            else:
                self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        device_number = int(self._light_data["port"])
        await self._shared_data._client.setLightState(device_number, "HIGH")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()

    async def async_turn_off(self, **kwargs):
        device_number = int(self._light_data["port"])
        await self._shared_data._client.setLightState(device_number, "OFF")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()

class SpaPumpSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], pump["value"])
            if pump:
                self._attr_is_on = pump["value"] == "HIGH"
            else:
                self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        try:
            device_number = int(self._pump_data["port"])
        except (ValueError, TypeError):
            _LOGGER.error("Invalid port value for Pump: %s", self._pump_data["port"])
            return
        await self._shared_data._client.setJetState(device_number, "HIGH")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()


    async def async_turn_off(self, **kwargs):
        try:
            device_number = int(self._pump_data["port"])
        except (ValueError, TypeError):
            _LOGGER.error("Invalid port value for Pump: %s", self._pump_data["port"])
            return
        await self._shared_data._client.setJetState(device_number, "OFF")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()

class SpaBlowerSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"switch.spa_blower_{int(blower_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"blower_{int(blower_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            blower = next(
                (comp for comp in data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            _LOGGER.debug("Updated Blower %s: %s", self._blower_data["port"], blower["value"])
            if blower:
                self._attr_is_on = blower["value"] == "HIGH"
            else:
                self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        try:
            device_number = int(self._blower_data["port"])
        except (ValueError, TypeError):
            _LOGGER.error("Invalid port value for Blower: %s", self._blower_data["port"])
            return
        await self._shared_data._client.setBlowerState(device_number, "HIGH")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()

    async def async_turn_off(self, **kwargs):
        try:
            device_number = int(self._blower_data["port"])
        except (ValueError, TypeError):
            _LOGGER.error("Invalid port value for Blower: %s", self._blower_data["port"])
            return
        await self._shared_data._client.setBlowerState(device_number, "OFF")
        self.async_write_ha_state()
        await self._shared_data.async_force_update()
