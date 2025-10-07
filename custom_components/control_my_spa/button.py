"""Implementace tlačítek pro Control My Spa."""
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Nastavení tlačítek pro Control My Spa."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    device_info = data["device_info"]

    async_add_entities([SpaUpdateTimeButton(hass, device_info)], True)

class SpaUpdateTimeButton(ButtonEntity):
    """Tlačítko pro aktualizaci času v Control My Spa."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, device_info):
        """Inicializace tlačítka."""
        self.hass = hass
        self._attr_device_info = device_info
        self._attr_unique_id = "button.spa_update_time"
        self._attr_translation_key = "update_time"
        self._attr_icon = "mdi:clock-outline"
        self.entity_id = self._attr_unique_id

    async def async_press(self) -> None:
        """Zpracování stisku tlačítka."""
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "update_time",
                {},
                blocking=True
            )
            _LOGGER.info("Služba pro aktualizaci času byla úspěšně zavolána")
        except Exception as e:
            _LOGGER.error("Error calling time update service: %s", str(e)) 