"""Clock sensor exposing the time reported by the spa control panel."""

from homeassistant.helpers.entity import EntityCategory
from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaClockSensor(SpaSensorBase):
    """Diagnostic sensor showing the time configured on the spa panel."""

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._state = None
        self._attr_should_poll = False
        self._attr_icon = "mdi:clock-outline"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_clock{unique_id_suffix}"
        self._attr_translation_key = "spa_clock"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._state = data.get("time")
            _LOGGER.debug("Updated spa clock: %s", self._state)

    @property
    def native_value(self):
        return self._state
