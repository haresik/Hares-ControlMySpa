"""Helper functions for ControlMySpa integration."""

import asyncio
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN

# Klíč v config_entry.data; prázdný string je validní hodnota (primární zóna)
UNIQUE_ID_SUFFIX_KEY = "unique_id_suffix"


def _entry_created_at(entry: ConfigEntry):
    """created_at s fallbackem, ať řazení nespadne na chybějícím atributu."""
    created = getattr(entry, "created_at", None)
    return created if created is not None else datetime.min


def make_safe_suffix(serial_number: str | None, *fallbacks: str | None) -> str:
    """Slugifikuje serial do validního object_id suffixu (_xxx).

    API vrací maskovaný serial s hvězdičkami (59304***2112270099),
    což v entity_id spadne na InvalidEntityFormatError.
    """
    for raw in (serial_number, *fallbacks):
        if not raw:
            continue
        safe = slugify(str(raw))
        if safe:
            return f"_{safe}"
    return ""


def _persist_suffix(hass: HomeAssistant, config_entry: ConfigEntry, suffix: str) -> None:
    """Uloží suffix do entry.data, včetně prázdného stringu pro primární zónu."""
    if UNIQUE_ID_SUFFIX_KEY in config_entry.data and config_entry.data[UNIQUE_ID_SUFFIX_KEY] == suffix:
        return
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, UNIQUE_ID_SUFFIX_KEY: suffix},
    )


async def get_unique_id_suffix(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    serial_number: str,
    spa_id: str | None = None,
) -> str:
    """Vrátí persistovaný nebo nově přiřazený unique_id suffix.

    První (nejstarší) config_entry má prázdný suffix, ať zůstanou existující entity.
    Další entry dostanou slugifikovaný _{serial}. Přiřazení se persistuje,
    takže se po restartu nepřehazuje.
    """
    if UNIQUE_ID_SUFFIX_KEY in config_entry.data:
        return config_entry.data[UNIQUE_ID_SUFFIX_KEY]

    domain_data = hass.data.setdefault(DOMAIN, {})
    lock = domain_data.setdefault("_suffix_lock", asyncio.Lock())

    async with lock:
        # Po nabytí locku znovu — jiná entry mohla mezitím persistovat primární suffix
        current = hass.config_entries.async_get_entry(config_entry.entry_id) or config_entry
        if UNIQUE_ID_SUFFIX_KEY in current.data:
            return current.data[UNIQUE_ID_SUFFIX_KEY]

        entries = hass.config_entries.async_entries(DOMAIN)
        primary_taken = any(
            e.entry_id != current.entry_id
            and UNIQUE_ID_SUFFIX_KEY in e.data
            and e.data[UNIQUE_ID_SUFFIX_KEY] == ""
            for e in entries
        )

        if not primary_taken:
            sorted_entries = sorted(
                entries,
                key=lambda e: (_entry_created_at(e), e.entry_id),
            )
            if sorted_entries and sorted_entries[0].entry_id == current.entry_id:
                suffix = ""
                _persist_suffix(hass, current, suffix)
                return suffix

        suffix = make_safe_suffix(serial_number, spa_id, current.entry_id)
        _persist_suffix(hass, current, suffix)
        return suffix
