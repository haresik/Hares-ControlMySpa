"""Component-related switch entities (light, blower)."""

from .base import SpaSwitchBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaLightSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, unique_id_suffix, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_light"
            if light_count == 1 or light_data['port'] is None
            else f"switch.spa_light_{int(light_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro světlo, výchozí hodnoty jsou OFF a HIGH
        self._available_values = light_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = self._available_values[0]  # První hodnota pro vypnuto
        self._on_value = self._available_values[-1]  # Poslední hodnota pro zapnuto
        self._is_processing = False  # Příznak zpracování

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        if self.is_on:
            return "mdi:lightbulb-on"
        else:
            return "mdi:lightbulb"

    def _get_light_state(self, data):
        """Získá stav světla z dat."""
        if not data:
            return None
        light = next(
            (comp for comp in data["components"] if comp["componentType"] == "LIGHT" and comp["port"] == self._light_data["port"]),
            None
        )
        return light["value"] if light else None

    async def async_update(self):
        data = self._shared_data.data
        if data:
            light_state = self._get_light_state(data)
            if light_state is not None:
                self._attr_is_on = light_state == self._on_value
                _LOGGER.debug("Updated Light %s: %s", self._light_data["port"], light_state)
            else:
                self._attr_is_on = False

    async def _try_set_light_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu světla s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()

        try:
            response_data = await self._shared_data._client.setLightState(device_number, target_state)
            if response_data is None:
                _LOGGER.warning("Function setLightState, parameter %s is not supported", target_state)
                return False
            new_state = self._get_light_state(response_data)

            if new_state == target_state:
                self._attr_is_on = (target_state == self._on_value)
                _LOGGER.info(
                    "Successfully %s light %s%s",
                    "turned on" if target_state == self._on_value else "turned off",
                    self._light_data["port"],
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Light %s was not %s. Expected state: %s, Current state: %s%s",
                    self._light_data["port"],
                    "turned on" if target_state == self._on_value else "turned off",
                    target_state,
                    new_state,
                    " (2nd attempt)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._light_data["port"])

            # První pokus
            success = await self._try_set_light_state(device_number, self._on_value)

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn on light %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._on_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for light: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on light (port %s): %s", self._light_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._light_data["port"])

            # První pokus
            success = await self._try_set_light_state(device_number, self._off_value)

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn off light %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._off_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for light: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off light (port %s): %s", self._light_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()


class SpaBlowerSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, unique_id_suffix, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"switch.spa_blower_{int(blower_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"blower_{int(blower_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro blower, výchozí hodnoty jsou OFF a HIGH
        self._available_values = blower_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = "OFF"  # Pevná hodnota pro vypnuto
        self._on_value = "HIGH"  # Pevná hodnota pro zapnuto
        self._is_processing = False  # Příznak zpracování

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        else:
            return "mdi:weather-dust"

    def _calculate_is_on_state(self, value: str) -> bool:
        """Vypočítá stav is_on na základě hodnoty podle pravidel."""
        if not value:
            return False
        # Pokud je hodnota 'LOW'
        if value == "LOW":
            # Pokud mezi dostupnými není MED ani HIGH ani HI → nastav OFF
            if "MED" not in self._available_values and "HIGH" not in self._available_values and "HI" not in self._available_values:
                return False
            # Pokud není MED, ale je HIGH → nastav HIGH
            elif "MED" not in self._available_values and ("HIGH" in self._available_values or "HI" in self._available_values):
                return True
            # Pokud je MED → nastav MED
            elif "MED" in self._available_values:
                return True
            else:
                return False
        # Pokud je hodnota 'MED', ověřit zda je HIGH v availableValues
        elif value == "MED":
            if "HIGH" in self._available_values:
                return True
            else:
                return False
        else:
            return value == self._on_value

    async def async_update(self):
        data = self._shared_data.data
        if data:
            blower = next(
                (comp for comp in data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            _LOGGER.debug("Updated Blower %s: %s", self._blower_data["port"], blower["value"])
            if blower:
                self._attr_is_on = self._calculate_is_on_state(blower["value"])
            else:
                self._attr_is_on = False

    async def _try_set_blower_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu vzduchovače s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()

        try:
            response_data = await self._shared_data._client.setBlowerState(device_number, target_state)
            if response_data is None:
                _LOGGER.warning("Function setBlowerState, parameter %s is not supported", target_state)
                return False
            blower = next(
                (comp for comp in response_data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            new_state = blower["value"] if blower else None

            # Převést stavy na boolean hodnoty
            expected_is_on = self._calculate_is_on_state(target_state)
            actual_is_on = self._calculate_is_on_state(new_state) if new_state else False

            if expected_is_on == actual_is_on:
                self._attr_is_on = actual_is_on
                _LOGGER.info(
                    "Successfully %s blower %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._blower_data["port"],
                    " (2nd attempt)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Blower %s was not %s. Expected state: %s (%s), Current state: %s (%s)%s",
                    self._blower_data["port"],
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
            device_number = int(self._blower_data["port"])

            # První pokus
            success = await self._try_set_blower_state(device_number, self._on_value)

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn on blower %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._on_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for blower: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on blower (port %s): %s", self._blower_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._blower_data["port"])

            # První pokus
            success = await self._try_set_blower_state(device_number, self._off_value)

            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Retrying to turn off blower %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._off_value, True)

            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for blower: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off blower (port %s): %s", self._blower_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()
