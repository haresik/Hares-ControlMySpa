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


def summarize_owned_spas(spas: list | None) -> list[str]:
    """Krátký výpis van do logu: serial + _id, bez hesla a tokenu."""
    if spas is None:
        return []
    return [format_spa_label(spa) for spa in spas if isinstance(spa, dict)]


def log_spa_list(source: str, spas: list | None, extra_spa_id: str | None = None) -> None:
    """Zaloguje, co vrátilo /spas/owned a jaké ID je uložené."""
    if spas is None:
        _LOGGER.warning("%s: /spas/owned failed (None), stored spa_id=%s", source, extra_spa_id)
        return
    _LOGGER.info(
        "%s: /spas/owned returned %s spa(s): %s; stored spa_id=%s",
        source,
        len(spas),
        summarize_owned_spas(spas) or "(empty)",
        extra_spa_id,
    )


def build_available_spas(spas: list | None, extra_spa_id: str | None = None) -> dict[str, str]:
    """Slovník spa_id -> label. extra_spa_id doplní uložené ID, pokud v listu chybí."""
    available: dict[str, str] = {}
    for spa in spas or []:
        spa_id = spa.get("_id")
        if spa_id:
            available[spa_id] = format_spa_label(spa)
        else:
            _LOGGER.warning("Owned spa is missing _id: %s", spa)
    if extra_spa_id and extra_spa_id not in available:
        available[extra_spa_id] = f"{extra_spa_id} (current)"
        _LOGGER.info("Stored spa_id %s is not in /spas/owned, added as current option", extra_spa_id)
    return available


def resolve_spa_id(user_input: dict | None) -> str | None:
    """Ruční pole má přednost před výběrem ze seznamu."""
    if not user_input:
        return None
    manual = (user_input.get(SPA_ID_MANUAL_KEY) or "").strip()
    if manual:
        _LOGGER.info("Using manual spa_id=%s", manual)
        return manual
    selected = user_input.get(SPA_ID_KEY)
    if selected:
        spa_id = str(selected).strip() or None
        _LOGGER.info("Using selected spa_id=%s", spa_id)
        return spa_id
    _LOGGER.warning("No spa_id in user input (keys=%s)", list(user_input.keys()))
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
    _LOGGER.info("Logging in user=%s", username)
    client = ControlMySpa(username, password)
    await client.init_session()
    if not await client.login():
        _LOGGER.error("Login failed for user=%s", username)
        await client.close()
        return None
    _LOGGER.info("Login OK for user=%s", username)
    return client


async def async_verify_spa_dashboard(client: ControlMySpa, spa_id: str) -> bool:
    """Ověří, že dashboard na dané spa_id vrací data."""
    if not spa_id:
        _LOGGER.error("Dashboard verification skipped, spa_id is empty")
        return False
    _LOGGER.info("Verifying dashboard for spa_id=%s", spa_id)
    client.spaId = spa_id
    data = await client.getSpa()
    if not data:
        _LOGGER.error("Dashboard verification failed for spa_id %s", spa_id)
        return False
    _LOGGER.info(
        "Dashboard OK for spa_id=%s serial=%s online=%s",
        spa_id,
        data.get("serialNumber"),
        data.get("isOnline"),
    )
    return True
