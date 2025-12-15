from datetime import timedelta
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    entities = [
        SpaIsOnlineSensor(shared_data, device_info),
    ]

    async_add_entities(entities)
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)


class SpaBinarySensorBase(BinarySensorEntity):
    _attr_has_entity_name = True

class SpaIsOnlineSensor(SpaBinarySensorBase):

    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_should_poll = False
        self._attr_device_info = device_info
        self._attr_unique_id = f"binary_sensor.{self._attr_device_info['serial_number']}_isOnline"
        self._attr_translation_key = f'isOnline'
        self.entity_id = self._attr_unique_id
        super().__init__()

    @property
    def icon(self):
        if self.is_on:
            return "mdi:led-on"
        else:
            return "mdi:led-off"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_is_on = data.get("isOnline")
            _LOGGER.debug("Updated isOnline %s", data.get("isOnline"))
