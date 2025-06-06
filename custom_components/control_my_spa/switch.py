from ast import Await
from homeassistant.components.switch import SwitchEntity
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

    # Najít všechny LIGHT komponenty s přesně dvěma hodnotami
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT" and 
        len(component.get("availableValues", ["OFF", "HIGH"])) == 2
    ]
    # Najít všechny PUMP komponenty s přesně dvěma hodnotami
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP" and 
        len(component.get("availableValues", ["OFF", "HIGH"])) == 2
    ]
    # Najít všechny BLOWER komponenty s přesně dvěma hodnotami
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER" and 
        len(component.get("availableValues", ["OFF", "HIGH"])) == 2
    ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Switch - Lights: %d, Pumps: %d, Blowers: %d",
        len(lights),
        len(pumps),
        len(blowers)
    )

    entities = [SpaLightSwitch(shared_data, device_info, light, len(lights)) for light in lights]
    entities += [SpaPumpSwitch(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSwitch(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    
    async_add_entities(entities, True)
    _LOGGER.debug("START Switch control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Switch (%s) (%s)", entity._attr_unique_id, entity.entity_id)

class SpaSwitchBase(SwitchEntity):
    _attr_has_entity_name = True

class SpaLightSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_light"
            if light_count == 1 or light_data['port'] is None
            else f"switch.spa_light_{int(light_data['port']) + 1}"
        )
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro světlo, výchozí hodnoty jsou OFF a HIGH
        self._available_values = light_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = self._available_values[0]  # První hodnota pro vypnuto
        self._on_value = self._available_values[-1]  # Poslední hodnota pro zapnuto
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

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
            new_state = self._get_light_state(response_data)
            
            if new_state == target_state:
                self._attr_is_on = (target_state == self._on_value)
                _LOGGER.info(
                    "Úspěšně %s světlo %s%s",
                    "zapnuto" if target_state == self._on_value else "vypnuto",
                    self._light_data["port"],
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Světlo %s nebylo %s. Očekávaný stav: %s, Aktuální stav: %s%s",
                    self._light_data["port"],
                    "zapnuto" if target_state == self._on_value else "vypnuto",
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
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
                _LOGGER.info("Zkouším znovu zapnout světlo %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._on_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro světlo: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při zapínání světla (port %s): %s", self._light_data["port"], str(e))
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
                _LOGGER.info("Zkouším znovu vypnout světlo %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro světlo: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při vypínání světla (port %s): %s", self._light_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaPumpSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro pump, výchozí hodnoty jsou OFF a HIGH
        self._available_values = pump_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = self._available_values[0]  # První hodnota pro vypnuto
        self._on_value = self._available_values[-1]  # Poslední hodnota pro zapnuto
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        else:
            return "mdi:weather-windy"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            _LOGGER.debug("Updated Pump %s: %s", self._pump_data["port"], pump["value"])
            if pump:
                self._attr_is_on = pump["value"] == self._on_value
            else:
                self._attr_is_on = False

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
                self._attr_is_on = (target_state == self._on_value)
                _LOGGER.info(
                    "Úspěšně %s čerpadlo %s%s",
                    "zapnuto" if target_state == self._on_value else "vypnuto",
                    self._pump_data["port"],
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Čerpadlo %s nebylo %s. Očekávaný stav: %s, Aktuální stav: %s%s",
                    self._pump_data["port"],
                    "zapnuto" if target_state == self._on_value else "vypnuto",
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
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
                _LOGGER.info("Zkouším znovu zapnout čerpadlo %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._on_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro čerpadlo: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při zapínání čerpadla (port %s): %s", self._pump_data["port"], str(e))
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
                _LOGGER.info("Zkouším znovu vypnout čerpadlo %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro čerpadlo: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při vypínání čerpadla (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaBlowerSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_should_poll = False
        self._attr_unique_id = (
            f"switch.spa_blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"switch.spa_blower_{int(blower_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"blower_{int(blower_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        # Získání dostupných hodnot pro blower, výchozí hodnoty jsou OFF a HIGH
        self._available_values = blower_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = self._available_values[0]  # První hodnota pro vypnuto
        self._on_value = self._available_values[-1]  # Poslední hodnota pro zapnuto
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        else:
            return "mdi:weather-dust"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            blower = next(
                (comp for comp in data["components"] if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]),
                None
            )
            _LOGGER.debug("Updated Blower %s: %s", self._blower_data["port"], blower["value"])
            if blower:
                self._attr_is_on = blower["value"] == self._on_value
            else:
                self._attr_is_on = False

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
                self._attr_is_on = (target_state == self._on_value)
                _LOGGER.info(
                    "Úspěšně %s vzduchovač %s%s",
                    "zapnut" if target_state == self._on_value else "vypnut",
                    self._blower_data["port"],
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Vzduchovač %s nebyl %s. Očekávaný stav: %s, Aktuální stav: %s%s",
                    self._blower_data["port"],
                    "zapnut" if target_state == self._on_value else "vypnut",
                    target_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
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
                _LOGGER.info("Zkouším znovu zapnout vzduchovač %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._on_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro vzduchovač: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při zapínání vzduchovače (port %s): %s", self._blower_data["port"], str(e))
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
                _LOGGER.info("Zkouším znovu vypnout vzduchovač %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Neplatná hodnota portu pro vzduchovač: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Chyba při vypínání vzduchovače (port %s): %s", self._blower_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()
