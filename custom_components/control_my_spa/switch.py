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
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Switch - Lights: %d, Pumps: %d, Blowers: %d, Filters: %d",
        len(lights),
        len(pumps),
        len(blowers),
        len(filters)
    )

    entities = [SpaLightSwitch(shared_data, device_info, light, len(lights)) for light in lights]
    entities += [SpaPumpSwitch(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSwitch(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    
    # Přidání switch pro druhý filtr pouze pokud existují dva filtry
    if len(filters) >= 2:
        entities.append(SpaFilter2Switch(shared_data, device_info, client))
    
    # Přidání TZL přepínače pouze pokud jsou k dispozici TZL zóny
    tzl_zones = shared_data.data.get("tzlZones", [])
    if tzl_zones:
        entities.append(SpaTzlPowerSwitch(shared_data, device_info, client))
    
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
            if response_data is None:
                _LOGGER.warning("Function setLightState, parameter %s is not supported", target_state)
                return False
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
                    "Light %s was not %s. Expected state: %s, Current state: %s%s",
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
                _LOGGER.info("Zkouším znovu vypnout světlo %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for light: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off light (port %s): %s", self._light_data["port"], str(e))
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
        self._off_value = "OFF"  # Pevná hodnota pro vypnuto
        self._on_value = "HIGH"  # Pevná hodnota pro zapnuto
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
                    "Úspěšně %s čerpadlo %s%s",
                    "zapnuto" if expected_is_on else "vypnuto",
                    self._pump_data["port"],
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump %s was not %s. Expected state: %s (%s), Current state: %s (%s)%s",
                    self._pump_data["port"],
                    "zapnuto" if expected_is_on else "vypnuto",
                    target_state,
                    expected_is_on,
                    new_state,
                    actual_is_on,
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
                _LOGGER.info("Zkouším znovu vypnout čerpadlo %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump (port %s): %s", self._pump_data["port"], str(e))
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
        self._off_value = "OFF"  # Pevná hodnota pro vypnuto
        self._on_value = "HIGH"  # Pevná hodnota pro zapnuto
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
                    "Úspěšně %s vzduchovač %s%s",
                    "zapnut" if expected_is_on else "vypnut",
                    self._blower_data["port"],
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Blower %s was not %s. Expected state: %s (%s), Current state: %s (%s)%s",
                    self._blower_data["port"],
                    "zapnut" if expected_is_on else "vypnut",
                    target_state,
                    expected_is_on,
                    new_state,
                    actual_is_on,
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
                _LOGGER.info("Zkouším znovu vypnout vzduchovač %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._off_value, True)
                
            await self._shared_data.async_force_update()
        except ValueError as ve:
            _LOGGER.error("Invalid port value for blower: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off blower (port %s): %s", self._blower_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaTzlPowerSwitch(SpaSwitchBase):
    """Přepínač pro zapnutí/vypnutí TZL světel."""

    def __init__(self, shared_data, device_info, client):
        """Inicializace TZL přepínače."""
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = "switch.spa_tzl_power"
        self._attr_translation_key = "tzl_power"
        self._attr_icon = "mdi:lightbulb-group"
        self._is_processing = False

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing
        
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
                    "Úspěšně %s TZL světla%s",
                    "zapnuto" if power_state == "ON" else "vypnuto",
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "TZL světla nebyla %s. Očekávaný stav: %s, Aktuální stav: %s%s",
                    "zapnuto" if power_state == "ON" else "vypnuto",
                    expected_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
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
                _LOGGER.info("Zkouším znovu zapnout TZL světla")
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
                _LOGGER.info("Zkouším znovu vypnout TZL světla")
                success = await self._try_set_tzl_power_state("OFF", True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off TZL lights: %s", str(e))
        finally:
            self._shared_data.resume_updates()

class SpaFilter2Switch(SpaSwitchBase):
    """Přepínač pro druhý filtr (spa_filter_2)."""
    
    def __init__(self, shared_data, device_info, client):
        """Inicializace přepínače druhého filtru."""
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = "switch.spa_filter_2"
        self._attr_translation_key = "filter_2"
        self._attr_icon = "mdi:water-sync"
        self._is_processing = False

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing
        
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
                    "Úspěšně %s druhý filtr%s",
                    "zapnuto" if state == "ON" else "vypnuto",
                    " (2. pokus)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Druhý filtr nebyl %s. Očekávaný stav: %s, Aktuální stav: %s%s",
                    "zapnuto" if state == "ON" else "vypnuto",
                    expected_state,
                    new_state,
                    " (2. pokus)" if is_retry else ""
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
                _LOGGER.info("Zkouším znovu zapnout druhý filtr")
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
                _LOGGER.info("Zkouším znovu vypnout druhý filtr")
                success = await self._try_set_filter2_state("OFF", True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off filter 2: %s", str(e))
        finally:
            self._shared_data.resume_updates()
