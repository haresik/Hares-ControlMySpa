"""Helper functions for ControlMySpa integration."""

from datetime import datetime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN


async def get_unique_id_suffix(hass: HomeAssistant, config_entry: ConfigEntry, serial_number: str) -> str:
    """
    Určí, zda použít prázdný suffix (první entry) nebo serial_number (další entry).
    
    První config_entry (podle data vytvoření created_at) zachová historii díky prázdnému suffixu.
    Další config_entry budou mít unikátní unique_id díky serial_number.
    
    Args:
        hass: Home Assistant instance
        config_entry: Aktuální config entry
        serial_number: Serial number zařízení
        
    Returns:
        Prázdný string "" pro první entry, nebo "_" + serial_number pro další
    """
    # Získat všechny config_entry pro DOMAIN
    entries = hass.config_entries.async_entries(DOMAIN)
    
    # Seřadit podle created_at (nejstarší na indexu 0)
    # Pokud created_at není k dispozici, použít datetime.min jako fallback
    sorted_entries = sorted(
        entries, 
        key=lambda e: e.created_at if hasattr(e, 'created_at') and e.created_at is not None else datetime.min
    )
    
    # Pokud je aktuální config_entry první → vrátit prázdný string
    if sorted_entries and sorted_entries[0].entry_id == config_entry.entry_id:
        return ""
    
    # Pokud není první → vrátit serial_number s prefixem "_"
    if serial_number:
        return f"_{serial_number}"
    else:
        # Pokud serial_number není k dispozici, použít entry_id jako fallback
        return f"_{config_entry.entry_id}"
