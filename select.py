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

    # Vytvoření sdíleného objektu pro data
    shared_data = SpaData(client)

    async_add_entities(
        [
            SpaTempRangeSelect(shared_data),  # TempRange select entita
        ],
        True,
    )

class SpaData:
    """Sdílený objekt pro uchování dat z webového dotazu."""
    def __init__(self, client):
        self._client = client
        self._data = None

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data

class SpaTempRangeSelect(SelectEntity):
    def __init__(self, shared_data):
        self._shared_data = shared_data
        self._attr_name = "Spa Temperature Range"
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
        data = self._shared_data.data
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