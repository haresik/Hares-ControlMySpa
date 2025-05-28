from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode
)
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

    entities = [SpaClimate(shared_data, device_info)]
    async_add_entities(entities, True)
    _LOGGER.debug("START Climate control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaClimate(ClimateEntity):
    _attr_has_entity_name = True

    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:hot-tub"
        self._attr_unique_id = "climate.spa_thermostat"
        self.entity_id = self._attr_unique_id
        self._attr_translation_key = f"thermostat"
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 10.0
        self._attr_max_temp = 40.0
        self._attr_should_poll = False
        self._attr_target_temperature_step = 0.5
        self._current_temperature = None
        self._target_temperature = None
        self._desired_temperature = None

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Aktuální teplota
            current_f = data.get("currentTemp")
            if current_f is not None:
                self._current_temperature = round((current_f - 32) * 5.0 / 9.0, 1)
            # Požadovaná teplota
            desired_f = data.get("desiredTemp")
            if desired_f is not None:
                self._desired_temperature = round((desired_f - 32) * 5.0 / 9.0, 1)
            # Cílená teplota (target)
            target_f = data.get("targetDesiredTemp")
            if target_f is not None:
                self._target_temperature = round((target_f - 32) * 5.0 / 9.0, 1)
            _LOGGER.debug("Climate update: current=%s, desired=%s, target=%s", self._current_temperature, self._desired_temperature, self._target_temperature)

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def target_temperature(self):
        # Vrací aktuální cílenou teplotu (targetDesiredTemp)
        return self._target_temperature

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_action(self):
        if (
            self._current_temperature is not None
            and self._desired_temperature is not None
        ):
            if self._current_temperature < self._desired_temperature:
                return "heating"
            else:
                return "idle"
        return None
   
    @property
    def hvac_mode(self):
        return HVACMode.HEAT

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT]

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.warning("Nepodporovaný režim: %s", hvac_mode)
        self.async_write_ha_state()

    @property
    def min_temp(self):
        return 10.0

    @property
    def max_temp(self):
        return 40.0

    async def async_set_temperature(self, **kwargs):
        value = kwargs.get("temperature")
        if value is not None and self.min_temp <= value <= self.max_temp:
            fahrenheit_temp = round(value * 9.0 / 5.0 + 32, 1)
            success = await self._shared_data._client.setTemp(fahrenheit_temp)
            if success:
                self._target_temperature = value
                _LOGGER.info("Successfully set target temperature to %s °C", value)
            else:
                _LOGGER.error("Failed to set target temperature to %s °C", value)
            await self._shared_data.async_force_update()

    @property
    def extra_state_attributes(self):
        return {
            "desired_temperature": self._desired_temperature,
            "target_desired_temperature": self._target_temperature,
        }
