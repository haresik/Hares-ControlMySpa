"""Pump switch entity."""

from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaPumpSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count, unique_id_suffix=""):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro pump, výchozí hodnoty jsou OFF a HIGH
        self._available_values = pump_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = "OFF"  # Pevná hodnota pro vypnuto
        self._on_value = "HIGH"  # Pevná hodnota pro zapnuto
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
        # Pokud je hodnota 'LOW'
        if value == "LOW":
            # Pokud mezi dostupnými není MED ani HIGH ani HI → nastav OFF
            if "MED" not in self._available_values and "HIGH" not in self._available_values and "HI" not in self._available_values:
                return True
            # Pokud není MED, ale je HIGH → nastav HIGH
            elif "MED" not in self._available_values and ("HIGH" in self._available_values or "HI" in self._available_values):
                return False
            # Pokud je MED → nastav MED
            elif "MED" in self._available_values:
                return False
            else:
                return True
        # Pokud je hodnota 'MED', ověřit zda je HIGH v availableValues
        elif value == "MED":
            if "HIGH" in self._available_values:
                return False
            else:
                return True
        else:
            return value == self._on_value

    async def async_update(self):
        data = self._shared_data.data
        if data:
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], pump["value"])
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
                    "Successfully %s pump %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._pump_data["port"],
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump %s was not %s. Expected state: %s (%s), Current state: %s (%s)%s",
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

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn on pump %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._on_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])

            # První pokus
            success = await self._try_set_pump_state(device_number, self._off_value)

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn off pump %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._off_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()
