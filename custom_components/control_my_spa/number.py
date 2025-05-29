from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfTemperature
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False

    # Vytvořit entitu pro targetDesiredTemp
    entities = [SpaTargetDesiredTempNumber(shared_data, device_info)]
    async_add_entities(entities, True)

    _LOGGER.debug("START Number control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaTargetDesiredTempNumber(NumberEntity):
    _attr_has_entity_name = True

    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self.mode = "box"
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_step = 0.5  # Krok v Celsiu
        self._attr_min_value = 10.0  # Minimální hodnota v Celsiu
        self._attr_max_value = 40.0  # Maximální hodnota v Celsiu
        self.native_step=0.5
        self.native_min_value=10.0
        self.native_max_value=40.0
        self._attr_device_info = device_info
        self._state = None
        self._attr_icon = "mdi:thermometer-water"
        self._attr_unique_id = f"number.spa_target_desired_temperature"
        self._attr_translation_key = f"target_desired_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        """Aktualizace hodnoty z datového zdroje."""
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("targetDesiredTemp")
            if fahrenheit_temp is not None:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated target desired temperature (Celsius): %s", self._state)

    async def async_set_value(self, value: float):
        """Nastavení nové hodnoty."""
        if self._attr_min_value <= value <= self._attr_max_value:
            fahrenheit_temp = round(value * 9.0 / 5.0 + 32, 1)  # Převod na Fahrenheit
            success = await self._shared_data._client.setTemp(fahrenheit_temp)
            if success:
                self._state = value
                _LOGGER.info("Successfully set target desired temperature to %s °C", value)
            else:
                _LOGGER.error("Failed to set target desired temperature to %s °C", value)
            await self._shared_data.async_force_update()
        else:
            _LOGGER.error("Value %s is out of range (%s - %s)", value, self._attr_min_value, self._attr_max_value)


    @property
    def native_value(self):
        """Vrací aktuální hodnotu."""
        return self._state
