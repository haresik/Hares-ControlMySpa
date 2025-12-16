"""Component-related select entities (pump, light, blower)."""

from .base import SpaSelectBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaPumpSelect(SpaSelectBase):
    """Select entity for spa pump."""
    
    def __init__(self, shared_data, device_info, unique_id_suffix, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_options = pump_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        base_id = f"select.spa_pump" if pump_count == 1 or pump_data['port'] == None else f"select.spa_pump_{int(pump_data['port']) + 1}"
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = f"pump" if pump_count == 1 or pump_data['port'] == None else f"pump_{int(pump_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        return "mdi:weather-windy"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající PUMP podle portu
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            if pump:
                pump_value = pump["value"]
                # Pokud je hodnota 'LOW'
                if pump_value == "LOW":
                    # Pokud mezi dostupnými není MED ani HIGH ani HI → nastav OFF
                    if "MED" not in self._attr_options and "HIGH" not in self._attr_options and "HI" not in self._attr_options:
                        self._attr_current_option = "OFF"
                    # Pokud není MED, ale je HIGH → nastav HIGH
                    elif "MED" not in self._attr_options and ("HIGH" in self._attr_options or "HI" in self._attr_options):
                        self._attr_current_option = "HIGH" if "HIGH" in self._attr_options else "HI"
                    # Pokud je MED → nastav MED
                    elif "MED" in self._attr_options:
                        self._attr_current_option = "MED"
                    else:
                        self._attr_current_option = pump_value
                # Pokud je hodnota 'MED', ověřit zda je HIGH v availableValues
                elif pump_value == "MED":
                    if "HIGH" in self._attr_options:
                        self._attr_current_option = "HIGH"
                    else:
                        self._attr_current_option = "OFF"
                else:
                    self._attr_current_option = pump_value
                _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], self._attr_current_option)

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
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaveno čerpadlo %s na %s%s",
                    self._pump_data["port"],
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump %s was not set. Expected state: %s, Current state: %s%s",
                    self._pump_data["port"],
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna hodnoty PUMP a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            
            # První pokus
            success = await self._try_set_pump_state(device_number, option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit čerpadlo %s na %s", self._pump_data["port"], option)
                success = await self._try_set_pump_state(device_number, option, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error setting pump (port %s) to %s: %s", self._pump_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaLightSelect(SpaSelectBase):
    """Select entity for spa light."""
    
    def __init__(self, shared_data, device_info, unique_id_suffix, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_options = light_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        base_id = f"select.spa_light" if light_count == 1 or light_data['port'] == None else f"select.spa_light_{int(light_data['port']) + 1}"
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        return "mdi:lightbulb"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající LIGHT podle portu
            light = next(
                (comp for comp in data["components"] if comp["componentType"] == "LIGHT" and comp["port"] == self._light_data["port"]),
                None
            )
            if light:
                self._attr_current_option = light["value"]
                _LOGGER.debug("Updated Light %s: %s", self._light_data["port"], self._attr_current_option)

    async def _try_set_light_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu světla s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            response_data = await self._shared_data._client.setLightState(device_number, target_state)
            if response_data is None:
                _LOGGER.warning("Function setLightState, parameter %s is not supported", target_state)
                return False
            light = next(
                (comp for comp in response_data["components"] if comp["componentType"] == "LIGHT" and comp["port"] == self._light_data["port"]),
                None
            )
            new_state = light["value"] if light else None
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaveno světlo %s na %s%s",
                    self._light_data["port"],
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Light %s was not set. Expected state: %s, Current state: %s%s",
                    self._light_data["port"],
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna hodnoty LIGHT a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            device_number = int(self._light_data["port"])
            
            # První pokus
            success = await self._try_set_light_state(device_number, option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit světlo %s na %s", self._light_data["port"], option)
                success = await self._try_set_light_state(device_number, option, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for light: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Error setting light (port %s) to %s: %s", self._light_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaBlowerSelect(SpaSelectBase):
    """Select entity for spa blower."""
    
    def __init__(self, shared_data, device_info, unique_id_suffix, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_options = blower_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        base_id = f"select.spa_blower" if blower_count == 1 or blower_data['port'] == None else f"select.spa_blower_{int(blower_data['port']) + 1}"
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = f"blower" if blower_count == 1 or blower_data['port'] == None else f"blower_{int(blower_data['port']) + 1}"
        self.entity_id = self._attr_unique_id 
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        return "mdi:weather-dust"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající BLOWER podle portu
            blower = next(
                (comp for comp in data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            if blower:
                self._attr_current_option = blower["value"]
                _LOGGER.debug("Updated Blower %s: %s", self._blower_data["port"], self._attr_current_option)

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
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaven vzduchovač %s na %s%s",
                    self._blower_data["port"],
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Blower %s was not set. Expected state: %s, Current state: %s%s",
                    self._blower_data["port"],
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna hodnoty BLOWER a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            device_number = int(self._blower_data["port"])
            
            # První pokus
            success = await self._try_set_blower_state(device_number, option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit vzduchovač %s na %s", self._blower_data["port"], option)
                success = await self._try_set_blower_state(device_number, option, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for blower: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Error setting blower (port %s) to %s: %s", self._blower_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()
