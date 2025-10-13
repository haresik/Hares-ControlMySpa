"""Base class for all select entities."""

from homeassistant.components.select import SelectEntity


class SpaSelectBase(SelectEntity):
    """Base class for all spa select entities."""
    
    _attr_has_entity_name = True
