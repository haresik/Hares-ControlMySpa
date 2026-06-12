"""Filter-related switch entities."""

from homeassistant.const import EntityCategory
from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaFilter2Switch(SpaSwitchBase):
    """Přepínač pro druhý filtr (spa_filter_2)."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        """Inicializace přepínače druhého filtru."""
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG  # sekce Nastavení na kartě zařízení
        self._client = client
        self._attr_unique_id = f"switch.spa_filter_2{unique_id_suffix}"
        self._attr_translation_key = "filter_2"
        self._attr_icon = "mdi:water-sync"
        self._is_processing = False

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        if self.is_on:
            return "mdi:water-sync"
        else:
            return "mdi:water-remove"

    def _get_filter2_state(self, data):
        """Získá stav druhého filtru z dat."""
        if not data:
            return False
        # Najít druhý filtr (port "1")
        filter_comp = next(
            (
                comp
                for comp in data["components"]
                if comp["componentType"] == "FILTER" and comp["port"] == "1"
            ),
            None,
        )
        if filter_comp:
            # Pokud je stav "DISABLED", switch je vypnutý, jinak zapnutý
            return filter_comp["value"] != "DISABLED"
        return False

    async def async_update(self):
        """Aktualizace stavu přepínače."""
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_filter2_state(data)
            _LOGGER.debug("Updated Filter 2: %s", self._attr_is_on)

    async def _try_set_filter2_state(self, state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu druhého filtru s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()

        try:
            response_data = await self._client.setFilter2Toggle(state)
            if response_data is None:
                _LOGGER.warning("Function setFilter2Toggle, parameter %s is not supported", state)
                return False

            new_state = self._get_filter2_state(response_data)
            expected_state = (state == "ON")

            if new_state == expected_state:
                self._attr_is_on = expected_state
                _LOGGER.info(
                    "Successfully %s filter 2%s",
                    "turned on" if state == "ON" else "turned off",
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Filter 2 was not %s. Expected state: %s, Current state: %s%s",
                    "turned on" if state == "ON" else "turned off",
                    expected_state,
                    new_state,
                    " (2nd attempt)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        """Zapnutí druhého filtru."""
        try:
            self._shared_data.pause_updates()

            # První pokus
            success = await self._try_set_filter2_state("ON")

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn on filter 2")
                success = await self._try_set_filter2_state("ON", True)

            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning on filter 2: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        """Vypnutí druhého filtru."""
        try:
            self._shared_data.pause_updates()

            # První pokus
            success = await self._try_set_filter2_state("OFF")

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn off filter 2")
                success = await self._try_set_filter2_state("OFF", True)

            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off filter 2: %s", str(e))
        finally:
            self._shared_data.resume_updates()
