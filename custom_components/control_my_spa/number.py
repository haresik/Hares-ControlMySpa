from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging
import asyncio

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Vytvořit entitu pro targetDesiredTemp
    entities = [SpaTargetDesiredTempNumber(shared_data, device_info)]
    async_add_entities(entities, True)

    _LOGGER.debug("START Number control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaTargetDesiredTempNumber(NumberEntity):
    """Entity pro nastavení požadované teploty vířivky s debounce logikou."""

    _attr_has_entity_name = True
    _attr_mode = "box"  # ✅ místo deprecated 'mode'
    native_unit_of_measurement = UnitOfTemperature.CELSIUS  # ✅ nové API
    _attr_icon = "mdi:thermometer-water"
    _attr_should_poll = False
    _attr_translation_key = "target_desired_temperature"

    # ✅ pouze moderní "native_" atributy
    native_step = 0.5
    native_min_value = 10.0
    native_max_value = 40.0

    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._attr_unique_id = "spa_target_desired_temperature"
        self._state = None

        # debounce mechanismus
        self._debounce_delay = 2.0
        self._debounce_task = None
        self._pending_value = None
        self._is_processing = False

    async def async_update(self):
        """Aktualizace hodnoty z datového zdroje."""
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("targetDesiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)
                _LOGGER.debug(
                    "Aktualizována cílová teplota: %s °C", self._state
                )

    @property
    def native_value(self) -> float | None:
        """Vrací aktuální hodnotu."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Dodatečné atributy entity."""
        return {
            "debounce_delay": self._debounce_delay,
            "pending_value": self._pending_value,
            "is_processing": self._is_processing,
        }

    async def async_set_native_value(self, value: float):
        """Nastavení nové hodnoty s debounce mechanismem."""
        if not (self.native_min_value <= value <= self.native_max_value):
            _LOGGER.error(
                "Value %s is out of range (%.1f–%.1f)",
                value,
                self.native_min_value,
                self.native_max_value,
            )
            return

        # Zrušit případný předchozí plánovaný úkol
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            _LOGGER.debug("Zrušeno předchozí zpožděné nastavení hodnoty")

        self._pending_value = value
        _LOGGER.debug(
            "Naplánováno nastavení teploty %s °C za %.1f s",
            value,
            self._debounce_delay,
        )

        self._debounce_task = asyncio.create_task(self._delayed_set_value())

    async def _delayed_set_value(self):
        """Zpožděné nastavení hodnoty (debounce)."""
        try:
            await asyncio.sleep(self._debounce_delay)
            if self._pending_value is not None:
                value = self._pending_value
                self._pending_value = None
                await self._debounced_set_value(value)
        except asyncio.CancelledError:
            _LOGGER.debug("Zpožděné nastavení bylo zrušeno")
        except Exception as e:
            _LOGGER.exception("Chyba v zpožděném nastavení: %s", e)

    async def _debounced_set_value(self, value: float):
        """Skutečné nastavení hodnoty po debounce zpoždění."""
        if self._is_processing:
            _LOGGER.debug(
                "Přeskočeno nastavení hodnoty %s °C — již probíhá zpracování",
                value,
            )
            return

        self._is_processing = True
        try:
            self._shared_data.pause_updates()
            fahrenheit_temp = round(value * 9.0 / 5.0 + 32, 1)
            success = await self._shared_data._client.setTemp(fahrenheit_temp)

            if success:
                self._state = value
                _LOGGER.info("Nastavena cílová teplota na %s °C", value)
            else:
                _LOGGER.error(
                    "Failed to set target temperature to %s °C", value
                )

            await self._shared_data.async_force_update()

        except Exception as e:
            _LOGGER.exception("Chyba při nastavování teploty: %s", e)
        finally:
            self._shared_data.resume_updates()
            self._is_processing = False

    def set_debounce_delay(self, delay: float):
        """Změní zpoždění debounce mechanismu."""
        if delay < 0:
            _LOGGER.warning("Delay cannot be negative, setting to 0 s")
            delay = 0.0

        self._debounce_delay = delay
        _LOGGER.info("Nastaveno nové zpoždění debounce na %.1f s", delay)
        self.async_write_ha_state()

