"""Sdílený mixin pro entity odebírající aktualizace ze SpaData."""


class SpaSubscriberMixin:
    """Registrace a odregistrace odběru dat ze SpaData."""

    async def async_will_remove_from_hass(self) -> None:
        """Odregistruje entitu jako odběratele při odebrání z HA."""
        await super().async_will_remove_from_hass()
        shared_data = getattr(self, "_shared_data", None)
        if shared_data is not None:
            shared_data.unregister_subscriber(self)
