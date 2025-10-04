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
    #entities += [SpaTzlZoneColorSelect(shared_data, device_info, tzl_zone_data, tzl_colors, len(tzl_zones)) for tzl_zone_data in tzl_zones]

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
                        _LOGGER.warning("Chyba při porovnávání teplot: %s", str(e))

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


class SpaTzlZoneColorSelect(SpaSelectBase):
    _attr_has_entity_name = True

    def __init__(self, shared_data, device_info, tzl_zone_data, tzl_colors, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._tzl_colors = tzl_colors
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
        
        for color in self._tzl_colors:
            color_id = color.get("colorId")
            red = color.get("red", 0)
            green = color.get("green", 0)
            blue = color.get("blue", 0)
            
            # Vytvořit název barvy
            color_name = self._get_color_name(red, green, blue)
            option_label = f"{color_name} (RGB: {red},{green},{blue})"
            
            options.append(option_label)
            
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
            language = self.hass.config.language
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

    async def async_select_option(self, option: str):
        if option == "OFF":
            _LOGGER.debug(f"Turning off TZL zone {self._tzl_zone_data['zoneId']}")
            # Zde by mělo být volání API pro vypnutí zóny
            # await self._shared_data.async_set_tzl_zone_color(
            #     self._tzl_zone_data["zoneId"], 0, 0, 0, "OFF"
            # )
        else:
            # Najít odpovídající barvu podle option (formát: "Název (RGB: r,g,b)")
            if " (RGB: " in option:
                # Extrahovat RGB hodnoty z option
                rgb_part = option.split(" (RGB: ")[1].rstrip(")")
                try:
                    red, green, blue = map(int, rgb_part.split(","))
                    _LOGGER.debug(f"Setting TZL zone {self._tzl_zone_data['zoneId']} to RGB {red},{green},{blue}")
                    # Zde by mělo být volání API pro nastavení barvy
                    # await self._shared_data.async_set_tzl_zone_color(
                    #     self._tzl_zone_data["zoneId"], red, green, blue, "NORMAL"
                    # )
                except ValueError:
                    _LOGGER.error(f"Invalid RGB format in option: {option}")
            else:
                _LOGGER.error(f"Unknown option format: {option}")
        
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
                current_hex = self._rgb_to_hex(red, green, blue)
                
                # Vytvořit seznam dostupných barev
                available_colors = []
                for color in self._tzl_colors:
                    color_name = self._get_color_name(
                        color.get("red", 0), 
                        color.get("green", 0), 
                        color.get("blue", 0)
                    )
                    available_colors.append({
                        "color_id": color.get("colorId"),
                        "name": color_name,
                        "rgb": [color.get("red", 0), color.get("green", 0), color.get("blue", 0)],
                        "hex": self._rgb_to_hex(color.get("red", 0), color.get("green", 0), color.get("blue", 0))
                    })
                
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "zone_id": tzl_zone.get("zoneId"),
                    "current_state": tzl_zone.get("state"),
                    "current_rgb": [red, green, blue],
                    "current_color_name": current_color_name,
                    "current_hex": current_hex,
                    "available_colors": available_colors,
                }
                return attrs
