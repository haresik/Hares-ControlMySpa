"""Implementace tlačítek pro Control My Spa."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
import logging

# Čas vany se mění často — do recorderu ho neukládáme
_UNRECORDED_BUTTON_ATTRIBUTES = frozenset({"spa_time"})

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Nastavení tlačítek pro Control My Spa."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    device_info = data["device_info"]
    shared_data = data["data"]
    unique_id_suffix = data["unique_id_suffix"]

    # Seznam tlačítek k přidání
    buttons = [SpaUpdateTimeButton(hass, shared_data, device_info, unique_id_suffix)]
    
    # Kontrola, jestli jsou k dispozici TZL zóny
    if shared_data.data:
        tzl_zones = shared_data.data.get("tzlZones", [])
        #if tzl_zones:
        #    buttons.append(SpaTzlLightOffButton(hass, device_info, unique_id_suffix))

    async_add_entities(buttons, True)
    for button in buttons:
        shared_data.register_subscriber(button)

class SpaUpdateTimeButton(ButtonEntity):
    """Tlačítko pro aktualizaci času v Control My Spa."""

    _attr_has_entity_name = True
    _unrecorded_attributes = _UNRECORDED_BUTTON_ATTRIBUTES

    def __init__(self, hass: HomeAssistant, shared_data, device_info, unique_id_suffix):
        """Inicializace tlačítka."""
        self.hass = hass
        self._shared_data = shared_data
        self._attr_should_poll = False
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG  # sekce Nastavení na kartě zařízení
        self._attr_unique_id = f"button.spa_update_time{unique_id_suffix}"
        self._attr_translation_key = "update_time"
        self._attr_icon = "mdi:clock-outline"
        self.entity_id = self._attr_unique_id

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return self._shared_data.is_remote_control_allowed

    @property
    def extra_state_attributes(self) -> dict:
        """Aktuální čas panelu — jen pro zobrazení, ne do historie."""
        data = self._shared_data.data or {}
        return {"spa_time": data.get("time")}

    async def async_update(self):
        """Stav tlačítka se nemění, atribut spa_time se bere živě z dat."""
        return

    async def async_press(self) -> None:
        """Zpracování stisku tlačítka."""
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "update_time",
                {},
                blocking=True
            )
            _LOGGER.info("Time update service called successfully")
        except Exception as e:
            _LOGGER.error("Error calling time update service: %s", str(e))

class SpaTzlLightOffButton(ButtonEntity):
    """Tlačítko pro vypnutí TZL světel v Control My Spa."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, device_info, unique_id_suffix):
        """Inicializace tlačítka."""
        self.hass = hass
        self._attr_device_info = device_info
        self._attr_unique_id = f"button.spa_tzl_light_off{unique_id_suffix}"
        self._attr_translation_key = "tzl_light_off"
        self._attr_icon = "mdi:lightbulb-off"
        self.entity_id = self._attr_unique_id

    async def async_press(self) -> None:
        """Zpracování stisku tlačítka."""
        try:
            # Získání všech instancí integrace
            for entry_id, entry_data in self.hass.data[DOMAIN].items():
                client = entry_data.get("client")
                
                if client:
                    # Volání metody setChromazonePower s parametrem "OFF"
                    response = await client.setChromazonePower("OFF")
                    if response:
                        _LOGGER.info("TZL lights turned off successfully")
                    else:
                        _LOGGER.warning("Failed to turn off TZL lights")
                    break
        except Exception as e:
            _LOGGER.error("Error turning off TZL lights: %s", str(e)) 