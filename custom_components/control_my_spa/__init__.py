import logging
import voluptuous as vol
from datetime import timedelta
from .const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.service import async_register_admin_service
from .ControlMySpa import ControlMySpa
from .SpaData import SpaData  
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
	Platform.SELECT,
	Platform.SENSOR,
    Platform.NUMBER ,
]

# async def async_setup(hass, config):
#     return True

async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug('options_update_listener', config_entry.data)
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    username = config_entry.data["username"]
    password = config_entry.data["password"]
    minUpdate = config_entry.data.get("updateintervalminutes", 2)
    _LOGGER.info("Aktuální lokalizace uživatele: %s", hass.config.language)

    # translations = await hass.helpers.translation.async_get_translations(hass.config.language, "entity")
    # light_translation = translations.get("component.control_my_spa.entity.select.light.name", "Překlad nenalezen")
    # _LOGGER.info("Překlad pro 'light': %s", light_translation)
    # _LOGGER.info("Dostupné překlady: %s", translations)

    spa_client = ControlMySpa(username, password)
    await spa_client.init()

    # Inicializace SpaData
    balboa_data = SpaData(spa_client, hass)
    await balboa_data.update()  # První aktualizace dat
    balboa_data.start_periodic_update(timedelta(minutes=minUpdate))  # Pravidelná aktualizace

    _LOGGER.info("ControlMySpa INIT async_setup_entry. Interval:%s, %s", minUpdate)

    if not balboa_data:
        _LOGGER.error("Failed to initialize ControlMySpa client")
        return False

    device_info = {
        "identifiers": {(DOMAIN, balboa_data.data["serialNumber"])},  # Unikátní identifikátor zařízení
        "name": "Spa",
        "manufacturer": "Balboa",
        "model": "Spa Model Unknown",
        "sw_version": balboa_data.data["controllerSoftwareVersion"],
        "serial_number": balboa_data.data["serialNumber"]
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": spa_client,
        "data": balboa_data,
        "device_info": device_info
    }

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    # Odregistrovat platformy
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)