"""Panel lock switch entity."""

from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaPanelLockSwitch(SpaSwitchBase):
    """Přepínač pro zamknutí/odemknutí fyzického ovládacího panelu vany."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = f"switch.spa_panel_lock{unique_id_suffix}"
        self._attr_translation_key = "panel_lock"
        self._attr_icon = "mdi:lock"
        self._attr_should_poll = False
        self._is_processing = False
        self.entity_id = "switch.spa_panel_lock"

    @property
    def available(self) -> bool:
        """Panel lock zůstane ovladatelný pro odemknutí na dálku."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        if self.is_on:
            return "mdi:lock"
        else:
            return "mdi:lock-open"

    def _get_panel_lock_state(self, data):
        """Získá stav zámku panelu z dat."""
        if not data:
            return False
        return bool(data.get("panelLock", False))

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_panel_lock_state(data)
            _LOGGER.debug("Updated Panel Lock: %s", self._attr_is_on)

    async def _try_set_panel_lock_state(self, locked: bool, is_retry: bool = False) -> bool:
        """Pokus o nastavení zámku panelu s možností opakování."""
        self._is_processing = True
        self.async_write_ha_state()

        try:
            response_data = await self._client.setPanelLock(locked)
            if response_data is None:
                _LOGGER.warning(
                    "Function setPanelLock, parameter %s is not supported",
                    locked,
                )
                return False

            new_state = self._get_panel_lock_state(response_data)
            if new_state == locked:
                self._attr_is_on = locked
                _LOGGER.info(
                    "Successfully %s panel%s",
                    "locked" if locked else "unlocked",
                    " (2nd attempt)" if is_retry else "",
                )
                return True

            _LOGGER.warning(
                "Panel was not %s. Expected state: %s, Current state: %s%s",
                "locked" if locked else "unlocked",
                locked,
                new_state,
                " (2nd attempt)" if is_retry else "",
            )
            return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        """Zamkne panel."""
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_panel_lock_state(True)
            if not success:
                _LOGGER.info("Retrying to engage panel lock")
                success = await self._try_set_panel_lock_state(True, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error engaging panel lock: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        """Odemkne panel."""
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_panel_lock_state(False)
            if not success:
                _LOGGER.info("Retrying to release panel lock")
                success = await self._try_set_panel_lock_state(False, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error releasing panel lock: %s", str(e))
        finally:
            self._shared_data.resume_updates()
