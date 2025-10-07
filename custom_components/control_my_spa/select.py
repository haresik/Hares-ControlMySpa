from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.helpers import translation
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

    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])
    tzl_colors = shared_data.data.get("tzlColors", [])

    entities = []
    entities = [SpaPumpSelect(shared_data, device_info, pump, len(pumps)) for pump in pumps]
    entities += [SpaBlowerSelect(shared_data, device_info, blower, len(blowers)) for blower in blowers]
    entities += [SpaLightSelect(shared_data, device_info, light, len(lights)) for light in lights]
    entities.append(SpaTempRangeSelect(shared_data, device_info, hass))  # Přidat entitu
    entities.append(SpaHeaterModeSelect(shared_data, device_info))  # Přidat entitu pro heater mode
    entities += [SpaTzlZoneModeSelect(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneColorSelect(shared_data, device_info, tzl_zone_data, tzl_colors, len(tzl_zones), hass) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneIntensitySelect(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]

    async_add_entities(entities, True)
    _LOGGER.debug("START Select control_my_spa")

    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Select (%s) (%s) ", entity._attr_unique_id, entity.entity_id)

class SpaSelectBase(SelectEntity):
    _attr_has_entity_name = True

class SpaTempRangeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, hass):
        self._shared_data = shared_data
        self._hass = hass  # Uložit hass objekt pro notifikace
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
            if response_data is None:
                _LOGGER.warning("Function setTempRange, parameter %s is not supported", target_state)
                return False
            new_state = response_data.get("tempRange")
            
            if new_state == target_state:
                self._attr_current_option = target_state
                _LOGGER.info(
                    "Úspěšně nastaven teplotní rozsah na %s%s",
                    target_state,
                    " (2. pokus)" if is_retry else ""
                )

                # Porovnat hodnotu z sensor.spa_desired_temperature s novou hodnotou desiredTemp
                if target_state == "HIGH":
                    try:
                        # Získat aktuální hodnotu z sensor.spa_desired_temperature
                        desired_temp_sensor = self._hass.states.get("sensor.spa_desired_temperature")
                        current_high_range_temp = None
                        
                        if desired_temp_sensor and desired_temp_sensor.state not in ["unavailable", "unknown"]:
                            # Zkusit získat poslední hodnotu pro HIGH rozsah z atributů
                            high_range_attr = desired_temp_sensor.attributes.get("high_range_value")
                            if high_range_attr is not None:
                                current_high_range_temp = float(high_range_attr)
                                _LOGGER.debug("Using high range value from attributes: %s", current_high_range_temp)
                        
                        # Získat novou hodnotu desiredTemp z odpovědi
                        new_desired_temp_f = response_data.get("desiredTemp")
                        if new_desired_temp_f is not None and current_high_range_temp is not None:
                            new_desired_temp_c = round((new_desired_temp_f - 32) * 5.0 / 9.0, 1)
                            
                            # Porovnat hodnoty
                            if abs(current_high_range_temp - new_desired_temp_c) > 0.1:  # Tolerance 0.1°C
                                # Vytvořit notifikaci
                                notification_title = "Změna požadované teploty v HIGH rozsahu"
                                notification_message = (
                                    f"Požadovaná teplota v HIGH rozsahu se změnila!\n"
                                    f"Předchozí hodnota: {current_high_range_temp}°C\n"
                                    f"Nová hodnota: {new_desired_temp_c}°C\n"
                                    f"Rozdíl: {new_desired_temp_c - current_high_range_temp:+.1f}°C"
                                )
                                
                                # Odeslat notifikaci
                                persistent_notification.async_create(
                                    self._hass,
                                    notification_message,
                                    title=notification_title,
                                    notification_id=f"spa_temp_change_{int(self._hass.time.time())}"
                                )
                                
                                _LOGGER.info(
                                    "Notifikace odeslána: Změna požadované teploty v HIGH rozsahu z %s°C na %s°C",
                                    current_high_range_temp,
                                    new_desired_temp_c
                                )
                    except (ValueError, AttributeError) as e:
                        _LOGGER.warning("Error comparing temperatures: %s", str(e))

                return True
            else:
                _LOGGER.warning(
                    "Temperature range was not set. Expected state: %s, Current state: %s%s",
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
            _LOGGER.error("Error setting temperature range to %s: %s", option, str(e))
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

class SpaHeaterModeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_options = ["READY", "REST", "READY_REST"]  
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
            if response_data is None:
                _LOGGER.warning("Function setHeaterMode, parameter %s is not supported", target_state)
                return False

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
                    "Heater mode was not set. Expected state: %s, Current state: %s%s",
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
            _LOGGER.error("Error setting heater mode to %s: %s", option, str(e))


class SpaTzlZoneModeSelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_options = ["OFF", "PARTY", "RELAX", "WHEEL", "NORMAL"]  # Pevné možnosti
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_unique_id = (
            f"select.spa_tzl_zone_mode"
            if count_tzl_zones == 1
            else f"select.spa_tzl_zone_mode_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_zone_mode"
            if count_tzl_zones == 1
            else f"tzl_zone_mode_{tzl_zone_data['zoneId']}"
        )
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
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                self._attr_current_option = tzl_zone["state"]
                _LOGGER.debug("Updated TZL Zone Mode %s: %s", self._tzl_zone_data["zoneId"], self._attr_current_option)

    async def _try_set_tzl_zone_mode(self, target_state: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení režimu TZL zóny s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            # Volání API pro nastavení stavu TZL zóny
            response_data = await self._shared_data._client.setChromazoneFunction(
                target_state, 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneFunction, parameter %s is not supported", target_state)
                return False
            
            if response_data:
                # Najít odpovídající TZL zone v odpovědi
                tzl_zone = next(
                    (
                        zone
                        for zone in response_data.get("tzlZones", [])
                        if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                    ),
                    None,
                )
                new_state = tzl_zone["state"] if tzl_zone else None
                
                if new_state == target_state:
                    self._attr_current_option = target_state
                    _LOGGER.info(
                        "Úspěšně nastavena TZL zóna %s na režim %s%s",
                        self._tzl_zone_data["zoneId"],
                        target_state,
                        " (2. pokus)" if is_retry else ""
                    )
                    return True
                else:
                    _LOGGER.warning(
                        "TZL zone %s was not set. Expected state: %s, Current state: %s%s",
                        self._tzl_zone_data["zoneId"],
                        target_state,
                        new_state,
                        " (2. pokus)" if is_retry else ""
                    )
                    return False
            else:
                _LOGGER.error("No API response for TZL zone %s", self._tzl_zone_data["zoneId"])
                return False
            
        except Exception as e:
            _LOGGER.error(
                "Error setting TZL zone %s to %s: %s",
                self._tzl_zone_data["zoneId"],
                target_state,
                str(e)
            )
            return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna režimu TZL zóny a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            
            # První pokus
            success = await self._try_set_tzl_zone_mode(option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit TZL zónu %s na %s", self._tzl_zone_data["zoneId"], option)
                success = await self._try_set_tzl_zone_mode(option, True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error setting TZL zone (ID %s) to %s: %s", self._tzl_zone_data["zoneId"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    @property
    def extra_state_attributes(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "zone_id": tzl_zone.get("zoneId"),
                }
                return attrs


class SpaTzlZoneColorSelect(SpaSelectBase):
    _attr_has_entity_name = True

    def __init__(self, shared_data, device_info, tzl_zone_data, tzl_colors, count_tzl_zones, hass):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._tzl_colors = tzl_colors
        self._hass = hass
        self._attr_device_info = device_info
        self._attr_should_poll = False
        self._current_option = None
        self._attr_icon = "mdi:palette"
        self._attr_unique_id = (
            f"select.spa_tzl_color_select"
            if count_tzl_zones == 1
            else f"select.spa_tzl_color_select_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_color_select"
            if count_tzl_zones == 1
            else f"tzl_color_select_{tzl_zone_data['zoneId']}"
        )
        self.entity_id = self._attr_unique_id
        self._options = self._create_color_options()

    def _create_color_options(self):
        """Vytvoří seznam možností barev z tzlColors."""
        options = ["OFF"]  # Vždy přidat možnost vypnutí
        self._color_options_data = {"OFF": {"color_id": None, "rgb": (0,0,0), "name": "OFF"}}
        
        for color in self._tzl_colors:
            color_id = color.get("colorId")
            red = color.get("red", 0)
            green = color.get("green", 0)
            blue = color.get("blue", 0)
            
            # Vytvořit název barvy
            color_name = self._get_color_name(red, green, blue)
            option_label = f"{color_name} (RGB: {red},{green},{blue})"
            
            options.append(option_label)
            self._color_options_data[option_label] = {
                "color_id": color_id,
                "rgb": (red, green, blue),
                "name": color_name
            }
            
        return options

    def _get_localized_color(self, color_key, language):
        """Vrátí lokalizovaný název barvy s emoji."""
        colors = {
            "white": {
                "cs": "⚪ Bílá",
                "en": "⚪ White", 
                "de": "⚪ Weiß"
            },
            "red": {
                "cs": "🔴 Červená",
                "en": "🔴 Red",
                "de": "🔴 Rot"
            },
            "green": {
                "cs": "🟢 Zelená",
                "en": "🟢 Green",
                "de": "🟢 Grün"
            },
            "blue": {
                "cs": "🔵 Modrá",
                "en": "🔵 Blue",
                "de": "🔵 Blau"
            },
            "yellow": {
                "cs": "🟡 Žlutá",
                "en": "🟡 Yellow",
                "de": "🟡 Gelb"
            },
            "purple": {
                "cs": "🟣 Fialová",
                "en": "🟣 Purple",
                "de": "🟣 Lila"
            },
            "cyan": {
                "cs": "🔵 Azurová",
                "en": "🔵 Cyan",
                "de": "🔵 Cyan"
            },
            "black": {
                "cs": "⚫ Černá",
                "en": "⚫ Black",
                "de": "⚫ Schwarz"
            },
            "light_gray": {
                "cs": "⚪ Světle šedá",
                "en": "⚪ Light Gray",
                "de": "⚪ Hellgrau"
            },
            "dark_gray": {
                "cs": "⚫ Tmavě šedá",
                "en": "⚫ Dark Gray",
                "de": "⚫ Dunkelgrau"
            },
            "light_red": {
                "cs": "🔴 Světle červená",
                "en": "🔴 Light Red",
                "de": "🔴 Hellrot"
            },
            "light_green": {
                "cs": "🟢 Světle zelená",
                "en": "🟢 Light Green",
                "de": "🟢 Hellgrün"
            },
            "light_blue": {
                "cs": "🔵 Světle modrá",
                "en": "🔵 Light Blue",
                "de": "🔵 Hellblau"
            },
            "light_yellow": {
                "cs": "🟡 Světle žlutá",
                "en": "🟡 Light Yellow",
                "de": "🟡 Hellgelb"
            },
            "light_purple": {
                "cs": "🟣 Světle fialová",
                "en": "🟣 Light Purple",
                "de": "🟣 Helllila"
            },
            "light_cyan": {
                "cs": "🔵 Světle azurová",
                "en": "🔵 Light Cyan",
                "de": "🔵 Hellcyan"
            },
            "orange": {
                "cs": "🟠 Oranžová",
                "en": "🟠 Orange",
                "de": "🟠 Orange"
            },
            "lime": {
                "cs": "🟢 Limetková",
                "en": "🟢 Lime",
                "de": "🟢 Limette"
            },
            "mint": {
                "cs": "🟢 Mátová",
                "en": "🟢 Mint",
                "de": "🟢 Minze"
            },
            "pink": {
                "cs": "🩷 Růžová",
                "en": "🩷 Pink",
                "de": "🩷 Rosa"
            },
            "magenta": {
                "cs": "🟣 Magenta",
                "en": "🟣 Magenta",
                "de": "🟣 Magenta"
            },
            "dark_pink": {
                "cs": "🩷 Tmavě růžová",
                "en": "🩷 Dark Pink",
                "de": "🩷 Dunkelrosa"
            }
        }
        
        return colors.get(color_key, {}).get(language, colors[color_key]["cs"])

    def _get_color_name(self, red, green, blue):
        """Vrátí název barvy na základě RGB hodnot."""
        # Získat aktuální jazyk Home Assistant
        try:
            language = self._hass.config.language
        except:
            language = "cs"  # Fallback na češtinu
        
        # Základní barvy (přesné shody)
        if red == 255 and green == 255 and blue == 255:
            return self._get_localized_color("white", language)
        elif red == 255 and green == 0 and blue == 0:
            return self._get_localized_color("red", language)
        elif red == 0 and green == 255 and blue == 0:
            return self._get_localized_color("green", language)
        elif red == 0 and green == 0 and blue == 255:
            return self._get_localized_color("blue", language)
        elif red == 255 and green == 255 and blue == 0:
            return self._get_localized_color("yellow", language)
        elif red == 255 and green == 0 and blue == 255:
            return self._get_localized_color("purple", language)
        elif red == 0 and green == 255 and blue == 255:
            return self._get_localized_color("cyan", language)
        elif red == 0 and green == 0 and blue == 0:
            return self._get_localized_color("black", language)
        
        # Rozšířené barvy (přibližné shody)
        elif red > 200 and green > 200 and blue > 200:
            return self._get_localized_color("light_gray", language)
        elif red < 50 and green < 50 and blue < 50:
            return self._get_localized_color("dark_gray", language)
        elif red > 200 and green < 100 and blue < 100:
            return self._get_localized_color("light_red", language)
        elif red < 100 and green > 200 and blue < 100:
            return self._get_localized_color("light_green", language)
        elif red < 100 and green < 100 and blue > 200:
            return self._get_localized_color("light_blue", language)
        elif red > 200 and green > 200 and blue < 100:
            return self._get_localized_color("light_yellow", language)
        elif red > 200 and green < 100 and blue > 200:
            return self._get_localized_color("light_purple", language)
        elif red < 100 and green > 200 and blue > 200:
            return self._get_localized_color("light_cyan", language)
        
        # Smíšené barvy
        elif red > 150 and green > 100 and blue < 100:
            return self._get_localized_color("orange", language)
        elif red > 100 and green > 150 and blue < 100:
            return self._get_localized_color("lime", language)
        elif red < 100 and green > 150 and blue > 100:
            return self._get_localized_color("mint", language)
        elif red > 100 and green < 100 and blue > 150:
            return self._get_localized_color("pink", language)
        elif red > 150 and green < 100 and blue > 100:
            return self._get_localized_color("magenta", language)
        
        # Specifické barvy z TZL
        elif red == 177 and green == 0 and blue == 255:
            return self._get_localized_color("dark_pink", language)
        elif red == 255 and green == 0 and blue == 92:
            return self._get_localized_color("pink", language)
        elif red == 83 and green == 106 and blue == 255:
            return self._get_localized_color("light_blue", language)
        
        # Pro ostatní barvy použít RGB hodnoty
        else:
            return f"RGB({red},{green},{blue})"

    def _rgb_to_hex(self, red, green, blue):
        """Převede RGB hodnoty na hex kód barvy."""
        return f"#{red:02x}{green:02x}{blue:02x}".upper()


    @property
    def options(self):
        return self._options

    @property
    def current_option(self):
        return self._current_option

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                state = tzl_zone.get("state", "OFF")
                red = tzl_zone.get("red", 0)
                green = tzl_zone.get("green", 0)
                blue = tzl_zone.get("blue", 0)
                
                # Prioritně najít shodu s definovanými barvami
                found_match = False
                for color in self._tzl_colors:
                    if (color.get("red") == red and 
                        color.get("green") == green and 
                        color.get("blue") == blue):
                        color_name = self._get_color_name(red, green, blue)
                        self._current_option = f"{color_name} (RGB: {red},{green},{blue})"
                        found_match = True
                        break
                
                # Pokud se nenašla shoda a barva je černá (0,0,0) a stav je OFF, nastavit na OFF
                if not found_match and red == 0 and green == 0 and blue == 0 and state == "OFF":
                    self._current_option = "OFF"
                elif not found_match:
                    # Pokud se nenašla shoda, ale barva není černá, zobrazit RGB hodnoty
                    color_name = self._get_color_name(red, green, blue)
                    self._current_option = f"{color_name} (RGB: {red},{green},{blue})"
                
                _LOGGER.debug("Updated TZL Color Select %s: %s (RGB: %s,%s,%s)", 
                             self._tzl_zone_data["zoneId"], self._current_option, red, green, blue)

    async def _try_set_tzl_zone_off(self, is_retry: bool = False) -> bool:
        """Pokus o vypnutí TZL zóny s možností opakování."""
        try:
            response_data = await self._shared_data._client.setChromazoneFunction(
                "OFF", 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneFunction (OFF), parameter is not supported")
                return False
            
            if response_data:
                # Najít odpovídající TZL zone v odpovědi
                tzl_zone = next(
                    (
                        zone
                        for zone in response_data.get("tzlZones", [])
                        if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                    ),
                    None,
                )
                new_state = tzl_zone["state"] if tzl_zone else None
                
                if new_state == "OFF":
                    self._current_option = "OFF"
                    _LOGGER.info(
                        "Úspěšně vypnuta TZL zóna %s%s",
                        self._tzl_zone_data["zoneId"],
                        " (2. pokus)" if is_retry else ""
                    )
                    return True
                else:
                    _LOGGER.warning(
                        "TZL zone %s was not turned off. Expected state: OFF, Current state: %s%s",
                        self._tzl_zone_data["zoneId"],
                        new_state,
                        " (2. pokus)" if is_retry else ""
                    )
                    return False
            else:
                _LOGGER.error("No API response for turning off TZL zone %s", self._tzl_zone_data["zoneId"])
                return False
                
        except Exception as e:
            _LOGGER.error(
                "Error turning off TZL zone %s: %s",
                self._tzl_zone_data["zoneId"],
                str(e)
            )
            return False

    async def _try_set_tzl_zone_color(self, color_id: int, is_retry: bool = False) -> bool:
        """Pokus o nastavení barvy TZL zóny s možností opakování."""
        try:
            response_data = await self._shared_data._client.setChromazoneColor(
                color_id, 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneColor, parameter %s is not supported", color_id)
                return False
            
            if response_data:
                # Najít odpovídající TZL zone v odpovědi
                tzl_zone = next(
                    (
                        zone
                        for zone in response_data.get("tzlZones", [])
                        if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                    ),
                    None,
                )
                
                if tzl_zone:
                    # Zkontrolovat, jestli se barva nastavila správně
                    red = tzl_zone.get("red", 0)
                    green = tzl_zone.get("green", 0)
                    blue = tzl_zone.get("blue", 0)
                    
                    # Najít očekávanou barvu podle color_id
                    expected_color = None
                    for color in self._tzl_colors:
                        if color.get("colorId") == color_id:
                            expected_color = color
                            break
                    
                    if expected_color:
                        expected_red = expected_color.get("red", 0)
                        expected_green = expected_color.get("green", 0)
                        expected_blue = expected_color.get("blue", 0)
                        
                        if (red == expected_red and green == expected_green and blue == expected_blue):
                            # Aktualizovat current_option
                            color_name = self._get_color_name(red, green, blue)
                            self._current_option = f"{color_name} (RGB: {red},{green},{blue})"
                            
                            _LOGGER.info(
                                "Úspěšně nastavena barva TZL zóny %s na color_id %s%s",
                                self._tzl_zone_data["zoneId"],
                                color_id,
                                " (2. pokus)" if is_retry else ""
                            )
                            return True
                        else:
                            _LOGGER.warning(
                                "TZL zone %s was not set to correct color. Expected: RGB(%s,%s,%s), Current: RGB(%s,%s,%s)%s",
                                self._tzl_zone_data["zoneId"],
                                expected_red, expected_green, expected_blue,
                                red, green, blue,
                                " (2. pokus)" if is_retry else ""
                            )
                            return False
                    else:
                        _LOGGER.warning("Expected color not found for color_id %s", color_id)
                        return False
                else:
                    _LOGGER.error("TZL zone %s was not found in response", self._tzl_zone_data["zoneId"])
                    return False
            else:
                _LOGGER.error("No API response for setting TZL zone color %s", self._tzl_zone_data["zoneId"])
                return False
                
        except Exception as e:
            _LOGGER.error(
                "Error setting TZL zone color %s to color_id %s: %s",
                self._tzl_zone_data["zoneId"],
                color_id,
                str(e)
            )
            return False

    async def async_select_option(self, option: str):
        try:
            self._shared_data.pause_updates()
            
            if option == "OFF":
                # První pokus pro vypnutí
                success = await self._try_set_tzl_zone_off()
                
                # Druhý pokus pokud první selhal
                if not success:
                    _LOGGER.info("Zkouším znovu vypnout TZL zónu %s", self._tzl_zone_data["zoneId"])
                    success = await self._try_set_tzl_zone_off(True)
            else:
                # Najít odpovídající barvu podle option v dictionary
                if option in self._color_options_data:
                    color_data = self._color_options_data[option]
                    color_id = color_data["color_id"]
                    
                    if color_id is not None:
                        # První pokus pro nastavení barvy
                        success = await self._try_set_tzl_zone_color(color_id)
                        
                        # Druhý pokus pokud první selhal
                        if not success:
                            _LOGGER.info("Zkouším znovu nastavit barvu TZL zóny %s na color_id %s", 
                                       self._tzl_zone_data["zoneId"], color_id)
                            success = await self._try_set_tzl_zone_color(color_id, True)
                    else:
                        _LOGGER.error(f"Color_id is None for option: {option}")
                else:
                    _LOGGER.error(f"Unknown option: {option}")
            
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error setting TZL color (ID %s) to %s: %s", 
                         self._tzl_zone_data["zoneId"], option, str(e))
        finally:
            self._shared_data.resume_updates()
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                red = tzl_zone.get("red", 0)
                green = tzl_zone.get("green", 0)
                blue = tzl_zone.get("blue", 0)
                current_color_name = self._get_color_name(red, green, blue)
                
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "zone_id": tzl_zone.get("zoneId"),
                    "current_rgb": [red, green, blue],
                    "current_color_name": current_color_name,
                }
                return attrs


class SpaTzlZoneIntensitySelect(SpaSelectBase):
    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]  # Intenzita 0-8
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:brightness-6"
        self._attr_unique_id = (
            f"select.spa_tzl_zone_intensity"
            if count_tzl_zones == 1
            else f"select.spa_tzl_zone_intensity_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_zone_intensity"
            if count_tzl_zones == 1
            else f"tzl_zone_intensity_{tzl_zone_data['zoneId']}"
        )
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
        return "mdi:brightness-6"

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                intensity = tzl_zone.get("intensity", 0)
                self._attr_current_option = str(intensity)
                _LOGGER.debug("Updated TZL Zone Intensity %s: %s", self._tzl_zone_data["zoneId"], intensity)

    async def _try_set_tzl_zone_intensity(self, intensity: int, is_retry: bool = False) -> bool:
        """Pokus o nastavení intenzity TZL zóny s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            # Volání API pro nastavení intenzity TZL zóny
            response_data = await self._shared_data._client.setChromazoneBrightness(
                intensity, 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneBrightness, parameter %s is not supported", intensity)
                return False
            
            if response_data:
                # Najít odpovídající TZL zone v odpovědi
                tzl_zone = next(
                    (
                        zone
                        for zone in response_data.get("tzlZones", [])
                        if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                    ),
                    None,
                )
                new_intensity = tzl_zone.get("intensity") if tzl_zone else None
                
                if new_intensity == intensity:
                    self._attr_current_option = str(intensity)
                    _LOGGER.info(
                        "Úspěšně nastavena intenzita TZL zóny %s na %s%s",
                        self._tzl_zone_data["zoneId"],
                        intensity,
                        " (2. pokus)" if is_retry else ""
                    )
                    return True
                else:
                    _LOGGER.warning(
                        "TZL zone %s was not set to correct intensity. Expected: %s, Current: %s%s",
                        self._tzl_zone_data["zoneId"],
                        intensity,
                        new_intensity,
                        " (2. pokus)" if is_retry else ""
                    )
                    return False
            else:
                _LOGGER.error("No API response for TZL zone %s", self._tzl_zone_data["zoneId"])
                return False
            
        except Exception as e:
            _LOGGER.error(
                "Error setting TZL zone intensity %s to %s: %s",
                self._tzl_zone_data["zoneId"],
                intensity,
                str(e)
            )
            return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna intenzity TZL zóny a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            intensity = int(option)
            
            # První pokus
            success = await self._try_set_tzl_zone_intensity(intensity)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit intenzitu TZL zóny %s na %s", self._tzl_zone_data["zoneId"], intensity)
                success = await self._try_set_tzl_zone_intensity(intensity, True)
                
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid intensity value: %s", option)
        except Exception as e:
            _LOGGER.error("Error setting TZL zone intensity (ID %s) to %s: %s", self._tzl_zone_data["zoneId"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    @property
    def extra_state_attributes(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající TZL zone podle zoneId
            tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            if tzl_zone:
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "zone_id": tzl_zone.get("zoneId"),
                    "intensity": tzl_zone.get("intensity"),
                }
                return attrs
 # type: ignore