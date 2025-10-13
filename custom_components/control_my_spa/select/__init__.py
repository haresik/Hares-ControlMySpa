"""Select entities for ControlMySpa integration."""

from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.helpers import translation
from ..const import DOMAIN
from .base import SpaSelectBase
from .temperature import SpaTempRangeSelect, SpaHeaterModeSelect
from .components import SpaPumpSelect, SpaLightSelect, SpaBlowerSelect
from .filter import SpaFilterTimeSelect, SpaFilterDurationSelect
from .tzl import (
    SpaTzlZoneModeSelect,
    SpaTzlZoneColorSelect,
    SpaTzlZoneIntensitySelect,
    SpaTzlZoneSpeedSelect
)
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny PUMP komponenty s více než dvěma hodnotami
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP" and 
        len(component.get("availableValues", [])) > 2
    ]
    # Najít všechny BLOWER komponenty s více než dvěma hodnotami
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER" and 
        len(component.get("availableValues", [])) > 2
    ]
    # Najít všechny LIGHT komponenty s více než dvěma hodnotami
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT" and 
        len(component.get("availableValues", [])) > 2
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Select - Lights: %d, Pumps: %d, Blowers: %d, Filters: %d",
        len(lights),
        len(pumps),
        len(blowers),
        len(filters)
    )

    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])
    tzl_colors = shared_data.data.get("tzlColors", [])

    entities = []
    entities = [SpaPumpSelect(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSelect(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    entities += [SpaLightSelect(shared_data, device_info, light, len(lights)) for light in lights]
    entities += [SpaFilterTimeSelect(shared_data, device_info, filter_data, len(filters)) for filter_data in filters]
    entities += [SpaFilterDurationSelect(shared_data, device_info, filter_data, len(filters)) for filter_data in filters]
    entities.append(SpaTempRangeSelect(shared_data, device_info, hass))  # Přidat entitu
    entities.append(SpaHeaterModeSelect(shared_data, device_info))  # Přidat entitu pro heater mode
    entities += [SpaTzlZoneModeSelect(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneColorSelect(shared_data, device_info, tzl_zone_data, tzl_colors, len(tzl_zones), hass) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneIntensitySelect(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneSpeedSelect(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]

    async_add_entities(entities, True)
    _LOGGER.debug("START Select control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Select (%s) (%s) ", entity._attr_unique_id, entity.entity_id)

__all__ = [
    "SpaSelectBase",
    "SpaTempRangeSelect",
    "SpaHeaterModeSelect",
    "SpaPumpSelect",
    "SpaLightSelect",
    "SpaBlowerSelect",
    "SpaFilterTimeSelect",
    "SpaFilterDurationSelect",
    "SpaTzlZoneModeSelect",
    "SpaTzlZoneColorSelect",
    "SpaTzlZoneIntensitySelect",
    "SpaTzlZoneSpeedSelect",
    "async_setup_entry",
]
