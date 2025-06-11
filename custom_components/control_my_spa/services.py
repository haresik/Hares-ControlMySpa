"""Služby pro Control My Spa integraci."""
import logging
import voluptuous as vol
from datetime import datetime
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, translation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components import persistent_notification

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_services(hass: HomeAssistant) -> None:
    """Nastavení služeb pro Control My Spa."""
    
    async def handle_update_time(call: ServiceCall) -> None:
        """Obsluha služby pro aktualizaci času."""
        
        # Získání všech instancí integrace
        for entry_id, entry_data in hass.data[DOMAIN].items():
            client = entry_data.get("client")
            shared_data = entry_data.get("data")
            
            if client and shared_data and shared_data.data:
                try:
                    # Získání aktuálního času ze spa před aktualizací
                    current_spa_time = shared_data.data.get("time", "Není k dispozici")
                    
                    # Aktualizace času
                    now = datetime.now()
                    date_str = now.strftime("%Y-%m-%d")  # Formát YYYY-MM-DD
                    time_str = now.strftime("%H:%M")     # Formát HH:MM (24h)
                    
                    # Volání metody setTime s aktuálním časem
                    await client.setTime(date_str, time_str, True)  # True pro 24h formát
                    _LOGGER.info("Čas úspěšně aktualizován z %s na %s %s", current_spa_time, date_str, time_str)
                    
                    # Načtení překladů
                    translations = await translation.async_get_translations(
                        hass,
                        hass.config.language,
                        "notification"
                    )
                    
                    # Získání překladů pro notifikaci
                    title = translations.get(
                        f"component.{DOMAIN}.notification.time_update.title",
                        "Aktualizace času vířivky !!!"
                    )
                    message = translations.get(
                        f"component.{DOMAIN}.notification.time_update.message",
                        "Čas vířivky byl úspěšně aktualizován z {old_time} na {new_time} !!!"
                    ).format(old_time=current_spa_time, new_time=time_str)
                    
                    # Vytvoření notifikace o úspěšné aktualizaci
                    persistent_notification.async_create(
                        hass,
                        message,
                        title=title,
                        notification_id="control_my_spa_time_update"
                    )
                    
                    # Pro debug
                    _LOGGER.debug("Dostupné překlady: %s", translations)
                    
                except Exception as e:
                    _LOGGER.error("Chyba při aktualizaci času: %s", str(e))
                    raise HomeAssistantError(f"Chyba při aktualizaci času: {str(e)}")

    # Registrace služby
    hass.services.async_register(
        DOMAIN,
        "update_time",
        handle_update_time
    )

async def async_unload_services(hass: HomeAssistant) -> None:
    """Odebrání služeb při odstranění integrace."""
    hass.services.async_remove(DOMAIN, "update_time") 