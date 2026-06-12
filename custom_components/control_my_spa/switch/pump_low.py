"""Low pump switch entity."""

from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaPumpLowSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count, unique_id_suffix=""):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_low_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_low_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "low_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"low_pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro pump, výchozí hodnoty jsou OFF a HIGH
        self._available_values = pump_data.get("availableValues", ["LOW", "HIGH"])
        # Nastavení _off_value: LOW má nižší stav, pokud tam je MED
        if "LOW" in self._available_values:
            self._off_value = "LOW"
        elif "MED" in self._available_values:
            self._off_value = "MED"
        else:
            self._off_value = self._available_values[0] if self._available_values else "OFF"
        # Nastavení _on_value: nejvyšší dostupná hodnota z MED nebo HIGH
        if "HIGH" in self._available_values or "HI" in self._available_values:
            self._on_value = "HIGH"
        elif "MED" in self._available_values:
            self._on_value = "MED"
        else:
            self._on_value = self._available_values[-1] if self._available_values else "HIGH"
        self._is_processing = False  # Příznak zpracování

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        else:
            return "mdi:weather-windy"

    def _calculate_is_on_state(self, value: str) -> bool:
        """Vypočítá stav is_on na základě hodnoty podle pravidel."""
        if not value:
            return False
        # Pokud je hodnota rovna _on_value (HIGH nebo MED), pak je to ON
        return value == self._on_value

    async def async_update(self):
        data = self._shared_data.data
        if data:
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            _LOGGER.debug("Updated Pump Low %s: %s", self._pump_data["port"], pump["value"] if pump else "None")
            if pump:
                self._attr_is_on = self._calculate_is_on_state(pump["value"])
            else:
                self._attr_is_on = False

    async def _try_set_pump_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu čerpadla s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()

        try:
            response_data = await self._shared_data._client.setJetState(device_number, target_state)
            if response_data is None:
                _LOGGER.warning("Function setJetState, parameter %s is not supported", target_state)
                return False

            pump = next(
                (comp for comp in response_data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            new_state = pump["value"] if pump else None

            # Převést stavy na boolean hodnoty
            expected_is_on = self._calculate_is_on_state(target_state)
            actual_is_on = self._calculate_is_on_state(new_state) if new_state else False

            if expected_is_on == actual_is_on:
                self._attr_is_on = actual_is_on
                _LOGGER.info(
                    "Successfully %s pump Low %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._pump_data["port"],
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump Low %s was not %s. Expected state: %s (%s), Current state: %s (%s)%s",
                    self._pump_data["port"],
                    "turned on" if expected_is_on else "turned off",
                    target_state,
                    expected_is_on,
                    new_state,
                    actual_is_on,
                    " (2nd attempt)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])

            # První pokus
            success = await self._try_set_pump_state(device_number, self._on_value)

            # Logování pokud první pokus selhal (bez druhého pokusu)
            if not success:
                _LOGGER.info("First attempt to turn on pump Low %s failed", self._pump_data["port"])

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump Low: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on pump Low (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])

            # První pokus
            success = await self._try_set_pump_state(device_number, self._off_value)

            # Logování pokud první pokus selhal (bez druhého pokusu)
            if not success:
                _LOGGER.info("First attempt to turn off pump Low %s failed", self._pump_data["port"])

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump Low: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump Low (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()
