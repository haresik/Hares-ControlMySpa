from homeassistant.helpers.event import async_track_time_interval
import logging

_LOGGER = logging.getLogger(__name__)

class SpaData:
    """Sdílený objekt pro uchování dat z webového dotazu."""
    def __init__(self, client, hass):
        self._client = client
        self._data = None
        self._hass = hass
        self._subscribers = []  # Seznam odběratelů

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)
        await self._notify_subscribers()  # Notifikace odběratelů

    def start_periodic_update(self, interval):
        """Spustí pravidelnou aktualizaci dat."""
        async_track_time_interval(self._hass, self._periodic_update, interval)

    async def _periodic_update(self, _):
        """Interní metoda pro pravidelnou aktualizaci."""
        await self.update()

    def register_subscriber(self, subscriber):
        """Registrace odběratele."""
        self._subscribers.append(subscriber)

    async def _notify_subscribers(self):
        """Notifikace všech odběratelů."""
        for subscriber in self._subscribers:
            if subscriber.hass:
                await subscriber.async_update()
                subscriber.async_write_ha_state() #zajisti ulozeni hodnoty do HA
            else:
                _LOGGER.warning("Subscriber %s has no hass attribute initialized", subscriber)

    async def async_force_update(self):
        await self.update()

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data
