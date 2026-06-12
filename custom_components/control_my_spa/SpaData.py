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
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def unregister_subscriber(self, subscriber):
        """Odregistrace odběratele."""
        try:
            self._subscribers.remove(subscriber)
        except ValueError:
            pass

    def clear_subscribers(self):
        """Odstraní všechny odběratele."""
        self._subscribers.clear()

    async def _notify_subscribers(self):
        """Notifikace všech odběratelů."""
        for subscriber in self._subscribers:
            try:
                if hasattr(subscriber, 'hass') and subscriber.hass is not None:
                    await subscriber.async_update()
                    subscriber.async_write_ha_state()  # zajisti ulozeni hodnoty do HA
                else:
                    _LOGGER.debug("Skipping subscriber %s - hass not available", subscriber)
            except Exception as e:
                _LOGGER.error("Error notifying subscriber %s: %s", subscriber, e)

    async def async_force_update(self):
        """Vynutí okamžitou aktualizaci dat."""
        await self.update()

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data

    @property
    def is_remote_control_allowed(self) -> bool:
        """Vzdálené ovládání povoleno jen když je vana online a panel není zamčen."""
        data = self._data
        if not data:
            return False
        if not data.get("isOnline", False):
            return False
        if data.get("panelLock", False):
            return False
        return True
