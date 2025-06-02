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
        self._update_interval = None  # Handler pro interval
        self._is_updating = False  # Příznak zda běží aktualizace
        self._last_interval = None  # Poslední použitý interval

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)
        await self._notify_subscribers()  # Notifikace odběratelů

    def start_periodic_update(self, interval):
        """Spustí pravidelnou aktualizaci dat."""
        self._last_interval = interval
        self._is_updating = True
        self._update_interval = async_track_time_interval(self._hass, self._periodic_update, interval)

    def pause_updates(self):
        """Pozastaví pravidelnou aktualizaci dat."""
        if self._update_interval is not None:
            self._update_interval()  # Zrušení intervalu
            self._update_interval = None
            self._is_updating = False
            _LOGGER.debug("Periodic updates paused")
            return True
        return False

    def resume_updates(self):
        """Obnoví pravidelnou aktualizaci dat."""
        if not self._is_updating and self._last_interval is not None:
            self.start_periodic_update(self._last_interval)
            _LOGGER.debug("Periodic updates resumed")
            return True
        return False

    @property
    def is_updating(self):
        """Vrací informaci, zda probíhá pravidelná aktualizace."""
        return self._is_updating

    async def _periodic_update(self, _):
        """Interní metoda pro pravidelnou aktualizaci."""
        await self.update()

    def register_subscriber(self, subscriber):
        """Registrace odběratele."""
        self._subscribers.append(subscriber)

    async def _notify_subscribers(self):
        """Notifikace všech odběratelů."""
        for subscriber in self._subscribers:
            try:
                if hasattr(subscriber, 'hass'):
                    await subscriber.async_update()
                    subscriber.async_write_ha_state()  # zajisti ulozeni hodnoty do HA
                else:
                    _LOGGER.warning("Subscriber %s has no hass attribute initialized", subscriber)
            except Exception as e:
                _LOGGER.error("Error notifying subscriber %s: %s", subscriber, e)

    async def async_force_update(self):
        """Vynutí okamžitou aktualizaci dat."""
        await self.update()

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data
