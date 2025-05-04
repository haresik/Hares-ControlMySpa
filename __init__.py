import logging
import voluptuous as vol
from .const import DOMAIN
from homeassistant.helpers.service import async_register_admin_service
from .ControlMySpa import ControlMySpa

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass, config):
    return True

async def async_setup_entry(hass, config_entry):
    username = config_entry.data["username"]
    password = config_entry.data["password"]

    spa_client = ControlMySpa(username, password)
    await spa_client.init()
    balboa_data = await spa_client.getSpa()

    _LOGGER.info(f"ControlMySpa INIT async_setup_entry {balboa_data}")
        
    if not balboa_data:
        _LOGGER.error("Failed to initialize ControlMySpa client")
        return False

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": spa_client,
        "data": balboa_data
    }

    # Registrace služby pro zmìnu tempRange
    async def handle_set_temp_range(call):
        temp_range = call.data.get("temp_range")
        if temp_range not in ["HIGH", "LOW"]:
            _LOGGER.error("Invalid temp_range value: %s", temp_range)
            return

        client = hass.data[DOMAIN][config_entry.entry_id]["client"]
        success = await client.setTempRange(temp_range == "HIGH")
        if success:
            _LOGGER.info("Successfully set tempRange to %s", temp_range)
        else:
            _LOGGER.error("Failed to set tempRange to %s", temp_range)

    hass.services.async_register(
        DOMAIN,
        "set_temp_range",
        handle_set_temp_range,
        schema=vol.Schema({
            vol.Required("temp_range"): vol.In(["HIGH", "LOW"]),
        }),
    )

    # Moderní zpùsob – nespouští deprecated warning
    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor", "select"]) 
    return True

async def async_unload_entry(hass, config_entry):
    return await hass.config_entries.async_forward_entry_unload(config_entry, "sensor", "select")
