"""Pomocné funkce pro výběr a ověření SPA v config/options flow."""

import logging
import voluptuous as vol

from .ControlMySpa import ControlMySpa

_LOGGER = logging.getLogger(__name__)

SPA_ID_KEY = "spa_id"
SPA_ID_MANUAL_KEY = "spa_id_manual"


def format_spa_label(spa: dict) -> str:
    """Sestaví label sériovka + alias + _id, ať jde poznat novou vanu od staré."""
    spa_id = spa.get("_id") or ""
    serial = spa.get("serialNumber") or ""
    alias = (spa.get("alias") or "").strip()
    parts = [part for part in (serial, alias) if part]
    prefix = " ".join(parts) if parts else "SPA"
    return f"{prefix} ({spa_id})" if spa_id else prefix


def build_available_spas(spas: list | None, extra_spa_id: str | None = None) -> dict[str, str]:
    """Slovník spa_id -> label. extra_spa_id doplní uložené ID, pokud v listu chybí."""
    available: dict[str, str] = {}
    for spa in spas or []:
        spa_id = spa.get("_id")
        if spa_id:
            available[spa_id] = format_spa_label(spa)
    if extra_spa_id and extra_spa_id not in available:
        available[extra_spa_id] = f"{extra_spa_id} (current)"
    return available


def resolve_spa_id(user_input: dict | None) -> str | None:
    """Ruční pole má přednost před výběrem ze seznamu."""
    if not user_input:
        return None
    manual = (user_input.get(SPA_ID_MANUAL_KEY) or "").strip()
    if manual:
        return manual
    selected = user_input.get(SPA_ID_KEY)
    if selected:
        return str(selected).strip() or None
    return None


def spa_selection_schema_dict(
    available_spas: dict[str, str],
    current_spa_id: str | None = None,
) -> dict:
    """Schéma: dropdown když je seznam, vždy textové pole jako fallback."""
    schema: dict = {}
    if available_spas:
        default_id = current_spa_id if current_spa_id in available_spas else next(iter(available_spas))
        schema[vol.Required(SPA_ID_KEY, default=default_id)] = vol.In(available_spas)
        schema[vol.Optional(SPA_ID_MANUAL_KEY, default="")] = str
    else:
        default_manual = current_spa_id or ""
        schema[vol.Required(SPA_ID_MANUAL_KEY, default=default_manual)] = str
    return schema


def pop_spa_selection_fields(user_input: dict) -> dict:
    """Odstraní spa pole z options payloadu — spa_id patří do entry.data."""
    cleaned = dict(user_input)
    cleaned.pop(SPA_ID_KEY, None)
    cleaned.pop(SPA_ID_MANUAL_KEY, None)
    return cleaned


async def async_create_logged_in_client(username: str, password: str) -> ControlMySpa | None:
    """Vytvoří přihlášeného klienta, nebo None když login selže."""
    client = ControlMySpa(username, password)
    await client.init_session()
    if not await client.login():
        await client.close()
        return None
    return client


async def async_verify_spa_dashboard(client: ControlMySpa, spa_id: str) -> bool:
    """Ověří, že dashboard na dané spa_id vrací data."""
    if not spa_id:
        return False
    client.spaId = spa_id
    data = await client.getSpa()
    if not data:
        _LOGGER.error("Dashboard verification failed for spa_id %s", spa_id)
        return False
    return True
