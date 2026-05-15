"""C8Z Chromazone current state sensors (API c8zCurrentState)."""

from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


def _read_c8z_state(shared_data):
    """Vrátí slovník c8zCurrentState nebo None, pokud chybí nebo není dict."""
    data = shared_data.data
    if not data:
        return None
    c8z = data.get("c8zCurrentState")
    if not isinstance(c8z, dict):
        if c8z is not None:
            _LOGGER.debug("c8zCurrentState není dict, ignoruji: %r", type(c8z).__name__)
        return None
    return c8z


class SpaC8zHeaterStateSensor(SpaSensorBase):
    """Stav ohřevu C8Z z c8zCurrentState.c8zHeaterState."""

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._state = None
        self._attr_should_poll = False
        # Tepelné čerpadlo (C8Z ohřev) — mdi:heat-pump je v MDI přímo TČ
        self._attr_icon = "mdi:heat-pump"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_c8z_heater_state{unique_id_suffix}"
        self._attr_translation_key = "c8z_heater_state"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        c8z = _read_c8z_state(self._shared_data)
        if c8z is None:
            self._state = None
            return
        self._state = c8z.get("c8zHeaterState")
        _LOGGER.debug("Aktualizace C8Z heater state: %s", self._state)

    @property
    def native_value(self):
        return self._state


class SpaC8zStatusSensor(SpaSensorBase):
    """Stav C8Z zařízení z c8zCurrentState.c8zStatus."""

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._state = None
        self._attr_should_poll = False
        # Stav jednotky TČ / C8Z — odlišná varianta stejné rodiny ikon
        self._attr_icon = "mdi:heat-pump-outline"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_c8z_status{unique_id_suffix}"
        self._attr_translation_key = "c8z_status"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        c8z = _read_c8z_state(self._shared_data)
        if c8z is None:
            self._state = None
            return
        self._state = c8z.get("c8zStatus")
        _LOGGER.debug("Aktualizace C8Z status: %s", self._state)

    @property
    def native_value(self):
        return self._state
