"""MicroSilk switch entity."""

import logging

from .base import SpaSwitchBase

_LOGGER = logging.getLogger(__name__)


class SpaMicrosilkSwitch(SpaSwitchBase):
    """Switch for the logical MicroSilk component reported by the spa."""

    def __init__(self, shared_data, device_info, unique_id_suffix, microsilk_data):
        self._shared_data = shared_data
        self._microsilk_data = microsilk_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:water-plus"
        self._attr_should_poll = False
        self._attr_unique_id = f"switch.spa_microsilk{unique_id_suffix}"
        self._attr_translation_key = "microsilk"
        self.entity_id = self._attr_unique_id
        available_values = microsilk_data.get("availableValues", ["OFF", "ON"])
        self._off_value = "OFF" if "OFF" in available_values else available_values[0]
        self._on_value = "ON" if "ON" in available_values else available_values[-1]
        self._is_processing = False

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        return "mdi:water-plus" if self.is_on else "mdi:water-minus"

    def _get_microsilk_state(self, data):
        """Return the current MicroSilk value from a dashboard response."""
        if not data:
            return None
        component = next(
            (
                comp
                for comp in data.get("components", [])
                if comp.get("componentType") == "MICROSILK"
            ),
            None,
        )
        return component.get("value") if component else None

    async def async_update(self):
        data = self._shared_data.data
        state = self._get_microsilk_state(data) if data else None
        self._attr_is_on = state == self._on_value
        if state is not None:
            _LOGGER.debug("Updated MicroSilk: %s", state)

    async def _try_set_microsilk_state(self, target_state: str, is_retry: bool = False) -> bool:
        self._is_processing = True
        self.async_write_ha_state()

        try:
            response_data = await self._shared_data._client.setMicrosilkState(target_state)
            if response_data is None:
                _LOGGER.warning(
                    "Function setMicrosilkState, parameter %s is not supported",
                    target_state,
                )
                return False

            new_state = self._get_microsilk_state(response_data)
            if new_state == target_state:
                self._attr_is_on = target_state == self._on_value
                _LOGGER.info(
                    "Successfully %s MicroSilk%s",
                    "turned on" if self._attr_is_on else "turned off",
                    " (2nd attempt)" if is_retry else "",
                )
                return True

            _LOGGER.warning(
                "MicroSilk was not set to %s. Current state: %s%s",
                target_state,
                new_state,
                " (2nd attempt)" if is_retry else "",
            )
            return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def _set_microsilk_state(self, target_state: str):
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_microsilk_state(target_state)
            if not success:
                _LOGGER.info("Retrying to set MicroSilk to %s", target_state)
                await self._try_set_microsilk_state(target_state, True)
            await self._shared_data.async_force_update()
        except Exception as err:
            _LOGGER.error("Error setting MicroSilk to %s: %s", target_state, err)
        finally:
            self._shared_data.resume_updates()

    async def async_turn_on(self, **kwargs):
        await self._set_microsilk_state(self._on_value)

    async def async_turn_off(self, **kwargs):
        await self._set_microsilk_state(self._off_value)
