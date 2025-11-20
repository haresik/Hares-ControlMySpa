"""TZL (Therapeutic Zone Lighting) related select entities."""

from .base import SpaSelectBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaTzlZoneModeSelect(SpaSelectBase):
    """Select entity for TZL zone mode."""
    
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
            # Pro NORMAL se volá setChromazoneColor s color_id=0
            if target_state == "NORMAL":
                response_data = await self._shared_data._client.setChromazoneColor(
                    0, 
                    self._tzl_zone_data["zoneId"]
                )
                
                if response_data is None:
                    _LOGGER.warning("Function setChromazoneColor, parameter 0 is not supported")
                    return False
            else:
                # Pro ostatní stavy se volá setChromazoneFunction
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
    """Select entity for TZL zone color."""
    
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
            # Kontrola, jestli se změnily tzl_colors
            current_tzl_colors = data.get("tzlColors", [])
            if current_tzl_colors != self._tzl_colors:
                _LOGGER.info("TZL colors changed, reloading color options for zone %s", self._tzl_zone_data["zoneId"])
                self._tzl_colors = current_tzl_colors
                self._options = self._create_color_options()
                self._attr_options = self._options
                self.async_write_ha_state()
            
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
    """Select entity for TZL zone intensity."""
    
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

class SpaTzlZoneSpeedSelect(SpaSelectBase):
    """Select entity for TZL zone speed."""
    
    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_options = ["0", "1", "2", "3", "4", "5"]  # Rychlost 0-5
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:speedometer"
        self._attr_unique_id = (
            f"select.spa_tzl_zone_speed"
            if count_tzl_zones == 1
            else f"select.spa_tzl_zone_speed_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_zone_speed"
            if count_tzl_zones == 1
            else f"tzl_zone_speed_{tzl_zone_data['zoneId']}"
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
        return "mdi:speedometer"

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
                speed = tzl_zone.get("speed", 0)
                self._attr_current_option = str(speed)
                _LOGGER.debug("Updated TZL Zone Speed %s: %s", self._tzl_zone_data["zoneId"], speed)

    async def _try_set_tzl_zone_speed(self, speed: int, is_retry: bool = False) -> bool:
        """Pokus o nastavení rychlosti TZL zóny s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            # Volání API pro nastavení rychlosti TZL zóny
            response_data = await self._shared_data._client.setChromazoneSpeed(
                speed, 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneSpeed, parameter %s is not supported", speed)
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
                new_speed = tzl_zone.get("speed") if tzl_zone else None
                
                if new_speed == speed:
                    self._attr_current_option = str(speed)
                    _LOGGER.info(
                        "Úspěšně nastavena rychlost TZL zóny %s na %s%s",
                        self._tzl_zone_data["zoneId"],
                        speed,
                        " (2. pokus)" if is_retry else ""
                    )
                    return True
                else:
                    _LOGGER.warning(
                        "TZL zone %s was not set to correct speed. Expected: %s, Current: %s%s",
                        self._tzl_zone_data["zoneId"],
                        speed,
                        new_speed,
                        " (2. pokus)" if is_retry else ""
                    )
                    return False
            else:
                _LOGGER.error("No API response for TZL zone %s", self._tzl_zone_data["zoneId"])
                return False
            
        except Exception as e:
            _LOGGER.error(
                "Error setting TZL zone speed %s to %s: %s",
                self._tzl_zone_data["zoneId"],
                speed,
                str(e)
            )
            return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna rychlosti TZL zóny a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            speed = int(option)
            
            # První pokus
            success = await self._try_set_tzl_zone_speed(speed)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit rychlost TZL zóny %s na %s", self._tzl_zone_data["zoneId"], speed)
                success = await self._try_set_tzl_zone_speed(speed, True)
                
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid speed value: %s", option)
        except Exception as e:
            _LOGGER.error("Error setting TZL zone speed (ID %s) to %s: %s", self._tzl_zone_data["zoneId"], option, str(e))
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
                    "speed": tzl_zone.get("speed"),
                }
                return attrs
