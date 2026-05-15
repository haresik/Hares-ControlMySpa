"""C8Z Chromazone select entities a stub volání API."""

from __future__ import annotations
import logging
from typing import Any
from .base import SpaSelectBase

_LOGGER = logging.getLogger(__name__)

# --- API zápis (ControlMySpa → /spa-commands/c8zone/state) ------------------------------


async def c8z_set_heater(shared_data: Any, option: str) -> dict | None:
    """Odešle c8zHeater na API. Vrací stav spa z getSpa() nebo None při chybě."""
    return await shared_data._client.setC8zHeaterState(option)


async def c8z_set_mode(shared_data: Any, option: str) -> dict | None:
    """Odešle c8zMode na API. Vrací stav spa z getSpa() nebo None při chybě."""
    return await shared_data._client.setC8zModeState(option)


async def c8z_set_speed(shared_data: Any, option: str) -> dict | None:
    """Odešle c8zSpeed na API. Vrací stav spa z getSpa() nebo None při chybě."""
    return await shared_data._client.setC8zSpeedState(option)


# --- Čtení stavu ----------------------------------------------------------------------


def _read_c8z_dict(shared_data: Any) -> dict | None:
    """Vrátí slovník c8zCurrentState nebo None, pokud chybí nebo není dict."""
    data = shared_data.data
    if not data:
        return None
    c8z = data.get("c8zCurrentState")
    if not isinstance(c8z, dict):
        if c8z is not None:
            _LOGGER.debug("c8zCurrentState není dict, ignoruji: %r", type(c8z).__name__)
        return None
    return c8z


def _new_state_from_response(response_data: dict | None, field: str) -> str | None:
    """Z odpovědi API vytáhne hodnotu pole z vnořeného c8zCurrentState."""
    if not isinstance(response_data, dict):
        return None
    c8z = response_data.get("c8zCurrentState")
    if not isinstance(c8z, dict):
        return None
    val = c8z.get(field)
    return val if isinstance(val, str) else None


# --- Entity ---------------------------------------------------------------------------


class SpaC8zHeaterSelect(SpaSelectBase):
    """Výběr režimu ohřevu C8Z (c8zHeater)."""

    _FIELD = "c8zHeater"

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        # Hodnoty API c8zHeater (heaterState)
        self._attr_options = [
            "C8Z_HEATER_AUTO",
            "C8Z_HEATER_CONTINUOUS",
            "C8Z_HEATER_M7",
            "C8Z_HEATER_DISABLED",
        ]
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:heat-pump"
        self._attr_unique_id = f"select.spa_c8z_heater{unique_id_suffix}"
        self._attr_translation_key = "c8z_heater"
        self.entity_id = self._attr_unique_id
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        return "mdi:heat-pump"

    async def async_update(self):
        c8z = _read_c8z_dict(self._shared_data)
        if not c8z:
            self._attr_current_option = None
            return
        val = c8z.get(self._FIELD)
        self._attr_current_option = val if val in self._attr_options else None
        _LOGGER.debug("Aktualizace C8Z heater select: %s", self._attr_current_option)

    async def _try_set(self, option: str, is_retry: bool = False) -> bool:
        self._is_processing = True
        self.async_write_ha_state()
        try:
            response_data = await c8z_set_heater(self._shared_data, option)
            if response_data is None:
                return False
            new_state = _new_state_from_response(response_data, self._FIELD)
            if new_state == option:
                self._attr_current_option = option
                _LOGGER.info(
                    "C8Z heater nastaven na %s%s",
                    option,
                    " (2. pokus)" if is_retry else "",
                )
                return True
            _LOGGER.warning(
                "C8Z heater se nepodařilo nastavit. Očekáváno: %s, vráceno: %s%s",
                option,
                new_state,
                " (2. pokus)" if is_retry else "",
            )
            return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        if option not in self._attr_options:
            return
        try:
            self._shared_data.pause_updates()
            success = await self._try_set(option)
            if not success:
                _LOGGER.info("Opakuji nastavení C8Z heater na %s", option)
                await self._try_set(option, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Chyba při nastavení C8Z heater na %s: %s", option, e)
        finally:
            self._shared_data.resume_updates()


class SpaC8zModeSelect(SpaSelectBase):
    """Výběr režimu C8Z (c8zMode)."""

    _FIELD = "c8zMode"

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._attr_options = [
            "C8Z_MODE_HEAT",
            "C8Z_MODE_BOTH",
            "C8Z_MODE_COOL",
            "C8Z_MODE_DISABLED",
        ]
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:heat-pump-outline"
        self._attr_unique_id = f"select.spa_c8z_mode{unique_id_suffix}"
        self._attr_translation_key = "c8z_mode"
        self.entity_id = self._attr_unique_id
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        return "mdi:heat-pump-outline"

    async def async_update(self):
        c8z = _read_c8z_dict(self._shared_data)
        if not c8z:
            self._attr_current_option = None
            return
        val = c8z.get(self._FIELD)
        self._attr_current_option = val if val in self._attr_options else None
        _LOGGER.debug("Aktualizace C8Z mode select: %s", self._attr_current_option)

    async def _try_set(self, option: str, is_retry: bool = False) -> bool:
        self._is_processing = True
        self.async_write_ha_state()
        try:
            response_data = await c8z_set_mode(self._shared_data, option)
            if response_data is None:
                return False
            new_state = _new_state_from_response(response_data, self._FIELD)
            if new_state == option:
                self._attr_current_option = option
                _LOGGER.info(
                    "C8Z mode nastaven na %s%s",
                    option,
                    " (2. pokus)" if is_retry else "",
                )
                return True
            _LOGGER.warning(
                "C8Z mode se nepodařilo nastavit. Očekáváno: %s, vráceno: %s%s",
                option,
                new_state,
                " (2. pokus)" if is_retry else "",
            )
            return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        if option not in self._attr_options:
            return
        try:
            self._shared_data.pause_updates()
            success = await self._try_set(option)
            if not success:
                _LOGGER.info("Opakuji nastavení C8Z mode na %s", option)
                await self._try_set(option, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Chyba při nastavení C8Z mode na %s: %s", option, e)
        finally:
            self._shared_data.resume_updates()


class SpaC8zSpeedSelect(SpaSelectBase):
    """Výběr rychlosti C8Z (c8zSpeed)."""

    _FIELD = "c8zSpeed"

    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._attr_options = [
            "C8Z_SPEED_SMART",
            "C8Z_SPEED_POWERFUL",
            "C8Z_SPEED_SILENT",
        ]
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:fan"
        self._attr_unique_id = f"select.spa_c8z_speed{unique_id_suffix}"
        self._attr_translation_key = "c8z_speed"
        self.entity_id = self._attr_unique_id
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        return "mdi:fan"

    async def async_update(self):
        c8z = _read_c8z_dict(self._shared_data)
        if not c8z:
            self._attr_current_option = None
            return
        val = c8z.get(self._FIELD)
        self._attr_current_option = val if val in self._attr_options else None
        _LOGGER.debug("Aktualizace C8Z speed select: %s", self._attr_current_option)

    async def _try_set(self, option: str, is_retry: bool = False) -> bool:
        self._is_processing = True
        self.async_write_ha_state()
        try:
            response_data = await c8z_set_speed(self._shared_data, option)
            if response_data is None:
                return False
            new_state = _new_state_from_response(response_data, self._FIELD)
            if new_state == option:
                self._attr_current_option = option
                _LOGGER.info(
                    "C8Z speed nastaven na %s%s",
                    option,
                    " (2. pokus)" if is_retry else "",
                )
                return True
            _LOGGER.warning(
                "C8Z speed se nepodařilo nastavit. Očekáváno: %s, vráceno: %s%s",
                option,
                new_state,
                " (2. pokus)" if is_retry else "",
            )
            return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        if option not in self._attr_options:
            return
        try:
            self._shared_data.pause_updates()
            success = await self._try_set(option)
            if not success:
                _LOGGER.info("Opakuji nastavení C8Z speed na %s", option)
                await self._try_set(option, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Chyba při nastavení C8Z speed na %s: %s", option, e)
        finally:
            self._shared_data.resume_updates()
