"""Switch entities for ControlMySpa integration."""

from ..const import DOMAIN
from .base import SpaSwitchBase
from .components import SpaLightSwitch, SpaBlowerSwitch
from .pump import SpaPumpSwitch
from .pump_low import SpaPumpLowSwitch
from .filter import SpaFilter2Switch
from .tzl import SpaTzlPowerSwitch
from .panel import SpaPanelLockSwitch
import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    unique_id_suffix = data["unique_id_suffix"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny LIGHT komponenty s přesně dvěma hodnotami
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT" and
        len(component.get("availableValues", ["OFF", "HIGH"])) == 2
    ]
    # Najít všechny PUMP komponenty s přesně dvěma hodnotami
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]
    # Najít všechny PUMP komponenty s LOW nebo MED hodnotami (pro SpaPumpLowSwitch)
    # pumps_low = [
    #     component for component in shared_data.data["components"]
    #     if component["componentType"] == "PUMP" and
    #     len(component.get("availableValues", [])) >= 2 and
    #     any(val in component.get("availableValues", []) for val in ["LOW", "MED"])
    # ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Switch - Lights: %d, Pumps: %d, Pumps Low: %d, Blowers: %d, Filters: %d",
        len(lights),
        len(pumps),
        0,
        len(blowers),
        len(filters)
    )

    entities = [SpaLightSwitch(shared_data, device_info, unique_id_suffix, light, len(lights)) for light in lights]
    entities += [SpaPumpSwitch(shared_data, device_info, pump, len(pumps), unique_id_suffix) for pump in pumps]
    # entities += [SpaPumpLowSwitch(shared_data, device_info, pump, len(pumps_low), unique_id_suffix) for pump in pumps_low]
    entities += [SpaBlowerSwitch(shared_data, device_info, unique_id_suffix, blower, len(blowers)) for blower in blowers]

    # Přidání switch pro druhý filtr pouze pokud existují dva filtry
    if len(filters) >= 2:
        entities.append(SpaFilter2Switch(shared_data, device_info, unique_id_suffix, client))

    # Přidání TZL přepínače pouze pokud jsou k dispozici TZL zóny
    tzl_zones = shared_data.data.get("tzlZones", [])
    if tzl_zones:
        entities.append(SpaTzlPowerSwitch(shared_data, device_info, unique_id_suffix, client))

    entities.append(SpaPanelLockSwitch(shared_data, device_info, unique_id_suffix, client))

    async_add_entities(entities, True)
    _LOGGER.debug("START Switch control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Switch (%s) (%s)", entity._attr_unique_id, entity.entity_id)


__all__ = [
    "SpaSwitchBase",
    "SpaLightSwitch",
    "SpaPumpSwitch",
    "SpaPumpLowSwitch",
    "SpaBlowerSwitch",
    "SpaFilter2Switch",
    "SpaTzlPowerSwitch",
    "SpaPanelLockSwitch",
    "async_setup_entry",
]
