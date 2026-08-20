from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from .const import DOMAIN
import logging

# Odchylka nad tento práh (minuty) zapne kontrolku. Panel hlásí jen HH:MM.
CLOCK_DRIFT_THRESHOLD_MINUTES = 5
_UNRECORDED_DRIFT_ATTRIBUTES = frozenset({"spa_time", "drift_minutes"})

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    unique_id_suffix = data["unique_id_suffix"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    entities = [
        SpaIsOnlineSensor(shared_data, device_info, unique_id_suffix),
        SpaClockOutOfSyncSensor(shared_data, device_info, unique_id_suffix),
    ]

    async_add_entities(entities)
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)


class SpaBinarySensorBase(BinarySensorEntity):
    _attr_has_entity_name = True

class SpaIsOnlineSensor(SpaBinarySensorBase):

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._attr_should_poll = False
        self._attr_device_info = device_info
        self._attr_unique_id = f'binary_sensor.isonline{unique_id_suffix}'
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


def _spa_clock_drift_minutes(spa_time: str | None) -> int | None:
    """Vrátí absolutní odchylku času vany od HA v minutách, nebo None."""
    if not spa_time or not isinstance(spa_time, str):
        return None
    try:
        parts = spa_time.strip().split(":")
        if len(parts) < 2:
            return None
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
    except (ValueError, TypeError):
        return None

    now = dt_util.now()
    spa_mins = hour * 60 + minute
    ha_mins = now.hour * 60 + now.minute
    diff = abs(spa_mins - ha_mins)
    return min(diff, 24 * 60 - diff)


class SpaClockOutOfSyncSensor(SpaBinarySensorBase):
    """Kontrolka: čas panelu vířivky se odchýlil od času Home Assistantu."""

    _unrecorded_attributes = _UNRECORDED_DRIFT_ATTRIBUTES

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._spa_time = None
        self._drift_minutes = None
        self._last_written_is_on = object()  # první zápis vždy projde
        self._attr_should_poll = False
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = device_info
        self._attr_unique_id = f"binary_sensor.spa_clock_out_of_sync{unique_id_suffix}"
        self._attr_translation_key = "clock_out_of_sync"
        self.entity_id = self._attr_unique_id
        super().__init__()

    @property
    def icon(self):
        if self.is_on:
            return "mdi:clock-alert-outline"
        return "mdi:clock-check-outline"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "spa_time": self._spa_time,
            "drift_minutes": self._drift_minutes,
        }

    def async_write_ha_state(self):
        """Do historie zapisuj jen když se změní on/off, ne každou minutu."""
        if self._attr_is_on == self._last_written_is_on:
            return
        self._last_written_is_on = self._attr_is_on
        super().async_write_ha_state()

    async def async_update(self):
        data = self._shared_data.data
        if not data:
            return
        self._spa_time = data.get("time")
        self._drift_minutes = _spa_clock_drift_minutes(self._spa_time)
        self._attr_is_on = (
            self._drift_minutes is not None
            and self._drift_minutes > CLOCK_DRIFT_THRESHOLD_MINUTES
        )
        _LOGGER.debug(
            "Updated clock drift: spa_time=%s drift=%s on=%s",
            self._spa_time,
            self._drift_minutes,
            self._attr_is_on,
        )
