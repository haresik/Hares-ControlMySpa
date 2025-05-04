from datetime import timedelta
from homeassistant.components.select import SelectEntity
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Nastavení intervalu aktualizace na 2 minuty
SCAN_INTERVAL = timedelta(minutes=2)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]
    async_add_entities(
        [
            SpaTempRangeSelect(client),  # TempRange select entita
        ],
        True,
    )


class SpaTempRangeSelect(SelectEntity):
    def __init__(self, client):
        self._client = client
        self._attr_name = "Spa Temperature Range"
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None

    async def async_update(self):
        """Načtení aktuální hodnoty tempRange ze zařízení."""
        data = await self._client.getSpa()
        if data:
            self._attr_current_option = data.get("tempRange")
            _LOGGER.debug("Updated tempRange: %s", self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty tempRange a odeslání do zařízení."""
        if option in self._attr_options:
            success = await self._client.setTempRange(option == "HIGH")
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set tempRange to %s", option)
            else:
                _LOGGER.error("Failed to set tempRange to %s", option)
 # type: ignore