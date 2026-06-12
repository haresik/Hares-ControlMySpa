"""TZL-related switch entities."""

from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaTzlPowerSwitch(SpaSwitchBase):
    """Přepínač pro zapnutí/vypnutí TZL světel."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        """Inicializace TZL přepínače."""
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = f"switch.spa_tzl_power{unique_id_suffix}"
        self._attr_translation_key = "tzl_power"
        self._attr_icon = "mdi:lightbulb-group"
        self._is_processing = False

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        if self.is_on:
            return "mdi:lightbulb-group"
        else:
            return "mdi:lightbulb-group-off"

    def _get_tzl_power_state(self, data):
        """Získá stav TZL světel z dat."""
        if not data:
            return False
        tzl_zones = data.get("tzlZones", [])
        if not tzl_zones:
            return False
        # Přepínač je ON, pokud alespoň jedna zóna není ve stavu OFF
        return any(zone.get("state") != "OFF" for zone in tzl_zones)

    async def async_update(self):
        """Aktualizace stavu přepínače."""
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_tzl_power_state(data)
            _LOGGER.debug("Updated TZL Power: %s", self._attr_is_on)

    async def _try_set_tzl_power_state(self, power_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu TZL světel s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()

        try:
            response_data = await self._client.setChromazonePower(power_state)
            if response_data is None:
                _LOGGER.warning("Function setChromazonePower, parameter %s is not supported", power_state)
                return False

            new_state = self._get_tzl_power_state(response_data)
            expected_state = (power_state == "ON")

            if new_state == expected_state:
                self._attr_is_on = expected_state
                _LOGGER.info(
                    "Successfully %s TZL lights%s",
                    "turned on" if power_state == "ON" else "turned off",
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "TZL lights were not %s. Expected state: %s, Current state: %s%s",
                    "turned on" if power_state == "ON" else "turned off",
                    expected_state,
                    new_state,
                    " (2nd attempt)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        """Zapnutí TZL světel."""
        try:
            self._shared_data.pause_updates()

            # První pokus
            success = await self._try_set_tzl_power_state("ON")

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn on TZL lights")
                success = await self._try_set_tzl_power_state("ON", True)

            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning on TZL lights: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        """Vypnutí TZL světel."""
        try:
            self._shared_data.pause_updates()

            # První pokus
            success = await self._try_set_tzl_power_state("OFF")

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn off TZL lights")
                success = await self._try_set_tzl_power_state("OFF", True)

            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off TZL lights: %s", str(e))
        finally:
            self._shared_data.resume_updates()
