"""Base class for all sensor entities."""

from homeassistant.components.sensor import SensorEntity


class SpaSensorBase(SensorEntity):
    """Base class for all spa sensor entities."""
    
    _attr_has_entity_name = True

