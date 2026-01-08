from homeassistant.components.fan import FanEntity, FanEntityFeature
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    unique_id_suffix = data["unique_id_suffix"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny PUMP komponenty s přesně třemi hodnotami (OFF, LOW, HIGH)
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP" and 
        len(component.get("availableValues", [])) >= 2 and
        any(val in component.get("availableValues", []) for val in ["LOW", "MED"])
    ]

    # Logování informací o filtrování
    _LOGGER.debug(
        "Filtered components for Fan - Pumps with 3 states: %d",
        len(pumps)
    )

    entities = [SpaPumpFan(shared_data, device_info, unique_id_suffix, pump, len(pumps)) for pump in pumps]
    
    async_add_entities(entities, True)
    _LOGGER.debug("START Fan control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Fan (%s) (%s)", entity._attr_unique_id, entity.entity_id)

class SpaPumpFan(FanEntity):
    """Fan entity pro PUMP komponenty se 3 stavy (OFF, LOW, HIGH)."""
    
    _attr_has_entity_name = True
    _attr_supported_features = FanEntityFeature.PRESET_MODE | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def __init__(self, shared_data, device_info, unique_id_suffix, pump_data, pump_count):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:fan"
        self._attr_should_poll = False
        base_id = (
            f"fan.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"fan.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        
        # Nastavení preset modes podle dostupných hodnot
        self._available_values = pump_data.get("availableValues", ["OFF", "HIGH"])
        # Zjistit, zda je podporován stav OFF
        self._supports_off = "OFF" in self._available_values
        # Vytvořit seznam preset modes z dostupných hodnot
        # OFF nikdy nezobrazovat v seznamu výběru (je dostupný jen přes tlačítko vypnout)
        if self._supports_off:
            # Pokud OFF je podporován, zobrazit všechny ostatní stavy
            preset_modes_list = [val for val in self._available_values if val != "OFF"]
        else:
            # Pokud OFF není podporován, LOW reprezentuje vypnutý stav, takže ho také nezobrazovat
            # V seznamu budou jen aktivní stavy (HIGH, případně MED)
            preset_modes_list = [val for val in self._available_values if val != "LOW"]
        self._attr_preset_modes = preset_modes_list
        self._attr_preset_mode = None
        self._is_processing = False  # Příznak zpracování

    @property
    def available(self) -> bool:
        """Indikuje, zda je entita dostupná pro ovládání."""
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"  # Ikona pro zpracování
        # Pokud není OFF podporován, LOW reprezentuje vypnutý stav
        if not self._supports_off and self._attr_preset_mode == "LOW":
            return "mdi:fan-off"
        if self._attr_preset_mode == "OFF":
            return "mdi:fan-off"
        elif self._attr_preset_mode == "LOW":
            return "mdi:fan-speed-1"
        elif self._attr_preset_mode == "MED":
            return "mdi:fan-speed-2"
        elif self._attr_preset_mode in ["HIGH", "HI"]:
            return "mdi:fan-speed-3"
        else:
            return "mdi:fan"

    @property
    def is_on(self) -> bool:
        """Vrátí True pokud není ve stavu OFF (nebo pokud není OFF podporován, pak pokud je HIGH)."""
        if not self._attr_preset_mode:
            return False
        if self._supports_off:
            return self._attr_preset_mode != "OFF"
        else:
            return self._attr_preset_mode in ["HIGH", "HI"]

    def _get_pump_state(self, data):
        """Získá stav pumpy z dat."""
        if not data:
            return None
        pump = next(
            (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
            None
        )
        return pump["value"] if pump else None

    async def async_update(self):
        """Aktualizace stavu fan entity."""
        data = self._shared_data.data
        if data:
            pump_state = self._get_pump_state(data)
            if pump_state is not None:
                # Mapování stavu na preset mode
                if pump_state in self._available_values:
                    self._attr_preset_mode = pump_state
                else:
                    # Pokud není OFF podporován, použít LOW jako výchozí stav
                    self._attr_preset_mode = "LOW" if not self._supports_off else "OFF"
                _LOGGER.debug("Updated Pump Fan %s: %s", self._pump_data["port"], pump_state)
            else:
                # Pokud není OFF podporován, použít LOW jako výchozí stav
                self._attr_preset_mode = "LOW" if not self._supports_off else "OFF"

    def _get_next_higher_state(self, current_state: str) -> str:
        """Získá další vyšší stav podle logiky."""
        available = self._available_values
        # Pokud není OFF podporován, použít LOW místo OFF
        off_state = "LOW" if not self._supports_off else "OFF"
        
        if current_state == "OFF":
            # Aktuální stav je OFF, chci zapnout
            if "LOW" not in available:
                # Neobsahuje LOW
                if "MED" not in available:
                    # Neobsahuje MED → HIGH
                    return "HIGH" if "HIGH" in available or "HI" in available else off_state
                else:
                    # Obsahuje MED → MED
                    return "MED"
            else:
                # Obsahuje LOW → LOW
                return "LOW"
        
        elif current_state == "LOW":
            # Aktuální stav je LOW, chci vyšší
            if not self._supports_off:
                # Pokud není OFF podporován, LOW je nejnižší stav, takže přejít na HIGH
                return "HIGH" if "HIGH" in available or "HI" in available else "LOW"
            if "MED" not in available:
                # Neobsahuje MED
                if "HIGH" not in available and "HI" not in available:
                    # Neobsahuje HIGH/HI → OFF
                    return "OFF"
                else:
                    # Obsahuje HIGH → HIGH
                    return "HIGH" if "HIGH" in available else "HI"
            else:
                # Obsahuje MED → MED
                return "MED"
        
        elif current_state == "MED":
            # Aktuální stav je MED, chci vyšší
            if "HIGH" not in available and "HI" not in available:
                # Neobsahuje HIGH → OFF nebo LOW
                return off_state
            else:
                # Obsahuje HIGH → HIGH
                return "HIGH" if "HIGH" in available else "HI"
        
        elif current_state in ["HIGH", "HI"]:
            # Aktuální stav je HIGH, chci vyšší → cyklické přepínání na OFF nebo LOW
            return off_state
        
        # Výchozí: pokud není rozpoznán stav, vrať OFF nebo LOW
        return off_state

    def _get_next_lower_state(self, current_state: str) -> str:
        """Získá další nižší stav podle logiky."""
        available = self._available_values
        # Pokud není OFF podporován, použít LOW místo OFF
        off_state = "LOW" if not self._supports_off else "OFF"
        
        if current_state in ["HIGH", "HI"]:
            # Aktuální stav je HIGH, chci nižší
            if "MED" in available:
                return "MED"
            elif "LOW" in available:
                return "LOW"
            else:
                return off_state
        
        elif current_state == "MED":
            # Aktuální stav je MED, chci nižší
            if "LOW" in available:
                return "LOW"
            else:
                return off_state
        
        elif current_state == "LOW":
            # Aktuální stav je LOW, chci nižší → OFF nebo zůstat na LOW pokud není OFF podporován
            if not self._supports_off:
                # Pokud není OFF podporován, LOW je nejnižší stav
                return "LOW"
            return "OFF"
        
        # Výchozí: pokud je OFF nebo neznámý stav, vrať OFF nebo LOW
        return off_state

    async def _try_set_pump_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení stavu pumpy s možností opakování."""
        self._is_processing = True  # Zneplatnění ovládání
        self.async_write_ha_state()
        
        try:
            response_data = await self._shared_data._client.setJetState(device_number, target_state)
            if response_data is None:
                _LOGGER.warning("Function setJetState, parameter %s is not supported", target_state)
                return False
            new_state = self._get_pump_state(response_data)
            
            if new_state == target_state:
                self._attr_preset_mode = target_state
                _LOGGER.info(
                    "Úspěšně nastavena pumpa %s na %s%s",
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
            self._is_processing = False  # Obnovení ovládání
            self.async_write_ha_state()

    async def async_turn_on(self, speed: str = None, percentage: int = None, preset_mode: str = None, **kwargs):
        """Zapnutí fan entity."""
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            
            # Získat aktuální stav
            current_state = self._attr_preset_mode or ("LOW" if not self._supports_off else "OFF")
            
            # Pokud je zadán preset_mode, použít ho
            if preset_mode:
                target_state = preset_mode
            # Pokud není zadán preset_mode, použít chytrou logiku pro další vyšší stav
            else:
                target_state = self._get_next_higher_state(current_state)
            
            # Odeslání požadavku
            success = await self._try_set_pump_state(device_number, target_state)
            
            # Aktualizace dat pro ověření stavu
            await self._shared_data.async_force_update()
            
            # Ověření nastavené hodnoty a logování stavu
            if not success:
                current_state = self._get_pump_state(self._shared_data.data)
                if current_state == target_state:
                    self._attr_preset_mode = target_state
                    _LOGGER.info(
                        "Pumpa %s byla nastavena na %s (ověřeno po aktualizaci)",
                        self._pump_data["port"],
                        target_state
                    )
                else:
                    _LOGGER.warning(
                        "Pumpa %s nebyla nastavena. Očekávaný stav: %s, Aktuální stav: %s",
                        self._pump_data["port"],
                        target_state,
                        current_state
                    )
        except ValueError as ve:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        """Vypnutí fan entity."""
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            
            # Pokud není OFF podporován, použít LOW místo OFF
            target_state = "LOW" if not self._supports_off else "OFF"
            
            # Odeslání požadavku
            success = await self._try_set_pump_state(device_number, target_state)
            
            # Aktualizace dat pro ověření stavu
            await self._shared_data.async_force_update()
            
            # Ověření nastavené hodnoty a logování stavu
            if not success:
                current_state = self._get_pump_state(self._shared_data.data)
                if current_state == target_state:
                    self._attr_preset_mode = target_state
                    _LOGGER.info(
                        "Pumpa %s byla vypnuta (ověřeno po aktualizaci)",
                        self._pump_data["port"]
                    )
                else:
                    _LOGGER.warning(
                        "Pumpa %s nebyla vypnuta. Aktuální stav: %s",
                        self._pump_data["port"],
                        current_state
                    )
        except ValueError as ve:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    def _get_target_state_for_preset(self, current_state: str, desired_preset: str) -> str:
        """Získá cílový stav pro přechod z aktuálního stavu na požadovaný preset mode."""
        available = self._available_values
        
        # Pokud chceme vypnout, vrať OFF nebo LOW pokud není OFF podporován
        if desired_preset == "OFF":
            return "LOW" if not self._supports_off else "OFF"
        
        # Pokud je aktuální stav stejný jako požadovaný, vrať aktuální
        if current_state == desired_preset or (current_state in ["HIGH", "HI"] and desired_preset in ["HIGH", "HI"]):
            return current_state
        
        # Pokud chceme vyšší stav než aktuální
        if desired_preset in ["HIGH", "HI"]:
            return self._get_next_higher_state(current_state)
        elif desired_preset == "MED":
            # Pokud chceme MED a aktuálně jsme na nižší úrovni, použij chytrou logiku pro vyšší
            if current_state == "OFF" or current_state == "LOW":
                return self._get_next_higher_state(current_state)
            # Pokud jsme na vyšší úrovni a chceme MED, vrať MED přímo
            elif current_state in ["HIGH", "HI"]:
                return "MED" if "MED" in available else self._get_next_lower_state(current_state)
            else:
                return "MED"
        elif desired_preset == "LOW":
            # Pokud chceme LOW a aktuálně jsme OFF, použij chytrou logiku pro zapnutí
            if current_state == "OFF":
                return self._get_next_higher_state(current_state)
            # Pokud jsme na vyšší úrovni a chceme LOW, vrať LOW přímo
            elif current_state in ["HIGH", "HI", "MED"]:
                return "LOW" if "LOW" in available else self._get_next_lower_state(current_state)
            else:
                return "LOW"
        
        # Výchozí: vrať požadovaný preset_mode
        return desired_preset

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Nastavení preset mode."""
        if preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Invalid preset mode: %s", preset_mode)
            return
        
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            
            # Získat aktuální stav
            current_state = self._attr_preset_mode or ("LOW" if not self._supports_off else "OFF")
            
            # Určit cílový stav podle chytré logiky
            target_state = self._get_target_state_for_preset(current_state, preset_mode)
            
            # Odeslání požadavku
            success = await self._try_set_pump_state(device_number, target_state)
            
            # Aktualizace dat pro ověření stavu
            await self._shared_data.async_force_update()
            
            # Ověření nastavené hodnoty a logování stavu
            if not success:
                current_state = self._get_pump_state(self._shared_data.data)
                if current_state == target_state:
                    self._attr_preset_mode = target_state
                    _LOGGER.info(
                        "Pumpa %s byla nastavena na %s (ověřeno po aktualizaci)",
                        self._pump_data["port"],
                        target_state
                    )
                else:
                    _LOGGER.warning(
                        "Pumpa %s nebyla nastavena. Očekávaný stav: %s, Aktuální stav: %s",
                        self._pump_data["port"],
                        target_state,
                        current_state
                    )
        except ValueError as ve:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error setting preset mode for pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()
