"""Alert and fault message sensor entities."""

from homeassistant.components.sensor import SensorStateClass
from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaFaultMessageSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._state = None
        self._attr_should_poll = False
        self._attr_icon = "mdi:alert-circle"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_fault_message{unique_id_suffix}"
        self._attr_translation_key = "fault_message"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fault = data.get("currentFaultMessage")
            if isinstance(fault, dict):
                self._state = fault.get("description")
                self._attrs = {
                    "code": fault.get("code"),
                    "severity": fault.get("severity"),
                    "controller_type": fault.get("controllerType"),
                }
            else:
                self._state = fault
                self._attrs = {}
            _LOGGER.debug("Updated fault message: %s", self._state)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return getattr(self, "_attrs", {})


class SpaTotalAlertsSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._state = None
        self._attr_should_poll = False
        self._attr_icon = "mdi:bell-alert"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_total_alerts{unique_id_suffix}"
        self._attr_translation_key = "total_alerts"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._state = data.get("totalAlerts")
            _LOGGER.debug("Updated total alerts: %s", self._state)

    @property
    def native_value(self):
        return self._state
