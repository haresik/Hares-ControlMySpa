"""Base class for all switch entities."""

from homeassistant.components.switch import SwitchEntity
from ..entity import SpaSubscriberMixin


class SpaSwitchBase(SpaSubscriberMixin, SwitchEntity):
    """Base class for all spa switch entities."""

    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        if getattr(self, "_is_processing", False):
            return False
        if self._attr_translation_key == "panel_lock":
            return True
        return self._shared_data.is_remote_control_allowed
