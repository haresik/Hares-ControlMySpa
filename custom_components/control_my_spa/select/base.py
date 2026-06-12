"""Base class for all select entities."""

from homeassistant.components.select import SelectEntity
from ..entity import SpaSubscriberMixin


class SpaSelectBase(SpaSubscriberMixin, SelectEntity):
    """Base class for all spa select entities."""
    
    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        if getattr(self, "_is_processing", False):
            return False
        return self._shared_data.is_remote_control_allowed
