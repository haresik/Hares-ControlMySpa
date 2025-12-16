"""Sensor entities for ControlMySpa integration."""

from homeassistant.core import HomeAssistant
from ..const import DOMAIN
from .base import SpaSensorBase
from .temperature import SpaTemperatureSensor, SpaDesiredTemperatureSensor
from .components import (
    SpaCirculationPumpSensor,
    SpaFilterSensor,
    SpaOzoneSensor,
    SpaHeaterSensor
)
from .energy import (
    SpaHeaterEnergySensor,
    SpaPumpEnergySensor,
    SpaBlowerEnergySensor,
    SpaCirculationPumpEnergySensor
)
import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    # client = data["client"]
    shared_data = data["data"]
    device_info = data["device_info"]
    unique_id_suffix = data["unique_id_suffix"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Získat konfiguraci z options (pro výkon heateru)
    config_options = config_entry.options or {}
    
    # Najít všechny CIRCULATION_PUMP komponenty
    circulation_pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "CIRCULATION_PUMP"
    ]
    # Najít všechny PUMP komponenty (pro switch a energy senzory)
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty (pro energy senzory)
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]
    # Najít všechny OZONE komponenty
    ozones = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "OZONE"
    ]
    # Najít všechny HEATER komponenty
    heaters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "HEATER"
    ]
    
    # Pokud nejsou nalezeny žádné HEATER komponenty, vytvoř výchozí
    if len(heaters) == 0:
        heaters = [{
            "name": "HEATER",
            "componentType": "HEATER",
            "value": "OFF",
            "port": "0",
        }]
    
    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])

    # Vytvořit entity pro každou CIRCULATION_PUMP
    entities = [SpaCirculationPumpSensor(shared_data, device_info, unique_id_suffix, pump, len(circulation_pumps)) for pump in circulation_pumps]
    entities.append(SpaTemperatureSensor(shared_data, device_info, unique_id_suffix))  # Aktuální teplota
    entities.append(SpaDesiredTemperatureSensor(shared_data, device_info, unique_id_suffix))  # Požadovaná teplota
    entities += [SpaFilterSensor(shared_data, device_info, unique_id_suffix, filter_data, len(filters)) for filter_data in filters]
    entities += [SpaOzoneSensor(shared_data, device_info, unique_id_suffix, ozone_data, len(ozones)) for ozone_data in ozones]
    entities += [SpaHeaterSensor(shared_data, device_info, unique_id_suffix, heater_data, len(heaters)) for heater_data in heaters]
    
    # Vytvořit energy senzory pro heatery (pro Energy Dashboard - kWh)
    entities += [SpaHeaterEnergySensor(shared_data, device_info, unique_id_suffix, heater_data, len(heaters), config_options) for heater_data in heaters]
    
    # Vytvořit energy senzory pro pumpy (pro Energy Dashboard - kWh)
    entities += [SpaPumpEnergySensor(shared_data, device_info, unique_id_suffix, pump_data, len(pumps), config_options) for pump_data in pumps]
    
    # Vytvořit energy senzory pro blowers (pro Energy Dashboard - kWh)
    entities += [SpaBlowerEnergySensor(shared_data, device_info, unique_id_suffix, blower_data, len(blowers), config_options) for blower_data in blowers]
    
    # Vytvořit energy senzory pro circulation pumps (pro Energy Dashboard - kWh)
    entities += [SpaCirculationPumpEnergySensor(shared_data, device_info, unique_id_suffix, pump_data, len(circulation_pumps), config_options) for pump_data in circulation_pumps]

    async_add_entities(entities, True)
    _LOGGER.debug("START Śensor control_my_spa")
    
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

__all__ = [
    "SpaSensorBase",
    "SpaTemperatureSensor",
    "SpaDesiredTemperatureSensor",
    "SpaCirculationPumpSensor",
    "SpaFilterSensor",
    "SpaOzoneSensor",
    "SpaHeaterSensor",
    "SpaHeaterEnergySensor",
    "SpaPumpEnergySensor",
    "SpaBlowerEnergySensor",
    "SpaCirculationPumpEnergySensor",
    "async_setup_entry",
]

