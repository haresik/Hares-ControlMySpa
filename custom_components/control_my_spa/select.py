from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny PUMP komponenty s více než dvěma hodnotami
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP" and 
        len(component.get("availableValues", [])) > 2
    ]
    # Najít všechny BLOWER komponenty s více než dvěma hodnotami
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER" and 
        len(component.get("availableValues", [])) > 2
    ]
    # Najít všechny LIGHT komponenty s více než dvěma hodnotami
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT" and 
        len(component.get("availableValues", [])) > 2
    ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Select - Lights: %d, Pumps: %d, Blowers: %d",
        len(lights),
        len(pumps),
        len(blowers)
    )

    entities = []
    entities = [SpaPumpSelect(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSelect(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    entities += [SpaLightSelect(shared_data, device_info, light, len(lights)) for light in lights]
    entities.append(SpaTempRangeSelect(shared_data, device_info))  # Přidat entitu
    entities.append(SpaHeaterModeSelect(shared_data, device_info))  # Přidat entitu pro heater mode

    async_add_entities(entities, True)
    _LOGGER.debug("START Select control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Select (%s) (%s) ", entity._attr_unique_id, entity.entity_id)

class SpaSelectBase(SelectEntity):
    _attr_has_entity_name = True

class SpaTempRangeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:pool-thermometer"
        self._attr_unique_id = f"select.spa_temperature_range"
        self._attr_translation_key = f"temperature_range"
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
        return "mdi:pool-thermometer"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_current_option = data.get("tempRange")
            _LOGGER.debug("Updated tempRange: %s", self._attr_current_option)

    async def _try_set_temp_range(self, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení teplotního rozsahu s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            response_data = await self._shared_data._client.setTempRange(target_state == "HIGH")
            new_state = response_data.get("tempRange")
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaven teplotní rozsah na %s%s",
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Teplotní rozsah nebyl nastaven. Očekávaný stav: %s, Aktuální stav: %s%s",
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna hodnoty tempRange a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            
            # První pokus
            success = await self._try_set_temp_range(option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit teplotní rozsah na %s", option)
                success = await self._try_set_temp_range(option, True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Chyba při nastavování teplotního rozsahu na %s: %s", option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaPumpSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_options = pump_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_unique_id = f"select.spa_pump" if pump_count == 1 or pump_data['port'] == None else f"select.spa_pump_{int(pump_data['port']) + 1}"
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
                self._attr_current_option = pump["value"]
                _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], self._attr_current_option)

    async def _try_set_pump_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu čerpadla s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            response_data = await self._shared_data._client.setJetState(device_number, target_state)
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
                    "Čerpadlo %s nebylo nastaveno. Očekávaný stav: %s, Aktuální stav: %s%s",
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
            _LOGGER.error("Neplatná hodnota portu pro čerpadlo: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při nastavování čerpadla (port %s) na %s: %s", self._pump_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaLightSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_options = light_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_unique_id = f"select.spa_light" if light_count == 1 or light_data['port'] == None else f"select.spa_light_{int(light_data['port']) + 1}"
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
                    "Světlo %s nebylo nastaveno. Očekávaný stav: %s, Aktuální stav: %s%s",
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
            _LOGGER.error("Neplatná hodnota portu pro světlo: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při nastavování světla (port %s) na %s: %s", self._light_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaBlowerSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_options = blower_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = f"select.spa_blower" if blower_count == 1 or blower_data['port'] == None else f"select.spa_blower_{int(blower_data['port']) + 1}"
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
                    "Vzduchovač %s nebyl nastaven. Očekávaný stav: %s, Aktuální stav: %s%s",
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
            _LOGGER.error("Neplatná hodnota portu pro vzduchovač: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při nastavování vzduchovače (port %s) na %s: %s", self._blower_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaHeaterModeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_options = ["READY", "REST", "READY_IN_REST"]  
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:radiator"
        self._attr_unique_id = f"select.spa_heater_mode"
        self._attr_translation_key = f"heater_mode"
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
        return "mdi:radiator"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_current_option = data.get("heaterMode")
            _LOGGER.debug("Updated heaterMode: %s", self._attr_current_option)

    async def _try_set_heater_mode(self, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení režimu ohřevu s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            response_data = await self._shared_data._client.setHeaterMode(target_state)
            new_state = response_data.get("heaterMode")
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaven režim ohřevu na %s%s",
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Režim ohřevu nebyl nastaven. Očekávaný stav: %s, Aktuální stav: %s%s",
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna hodnoty heater mode a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            
            # První pokus
            success = await self._try_set_heater_mode(option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit režim ohřevu na %s", option)
                success = await self._try_set_heater_mode(option, True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Chyba při nastavování režimu ohřevu na %s: %s", option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()
