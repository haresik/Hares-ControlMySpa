from homeassistant.components.light import LightEntity, ColorMode, LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

def async_set_favorite_colors(hass: HomeAssistant, entity_id: str, colors: list[tuple[int, int, int]] | None) -> None:
    """Nastaví oblíbené barvy pro light entity pomocí entity registry options."""
    try:
        # Ošetřit None entity_id
        if entity_id is None:
            _LOGGER.warning("Entity ID is None, cannot set favorite colors")
            return
            
        entity = er.async_get(hass).async_get(entity_id)
        if entity is None:
            _LOGGER.warning("Entity ID %s is not valid", entity_id)
            return

        if (old_options := entity.options.get("light")) is None:
            if colors is None:
                return
            options = {}
        else:
            options = {k: v for k, v in old_options.items() if k != "favorite_colors"}
        
        if colors is not None:
            # Zkusit různé formáty pro oblíbené barvy
            options["favorite_colors"] = colors
            # Zkusit také alternativní formát
            options["supported_color_list"] = colors

        er.async_get(hass).async_update_entity_options(entity_id, "light", options)
        _LOGGER.info("Set favorite colors for %s: %s", entity_id, colors)
        _LOGGER.debug("Entity options after update: %s", options)
        
        # Debug: Zkontrolovat, zda se options skutečně nastavily
        updated_entity = er.async_get(hass).async_get(entity_id)
        if updated_entity:
            _LOGGER.debug("Updated entity options: %s", updated_entity.options.get("light", {}))
        
    except Exception as e:
        _LOGGER.error("Failed to set favorite colors for %s: %s", entity_id, e)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])

    # Vytvořit Light entity pro každou TZL zone
    entities = [SpaTzlZoneLight(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    # entities = []  # Prázdný seznam, protože Light entity jsou zakomentované

    async_add_entities(entities, True)
    _LOGGER.debug("START Light control_my_spa")
    
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaTzlZoneLight(LightEntity):
    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.RGB}  # RGB pro výběrové barvy (jas je součástí RGB)
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature(0)  # Žádné speciální funkce

    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_is_on = False
        self._attr_rgb_color = (0, 0, 0)  # RGB formát
        self._attr_brightness = 0
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_supported_color_list = []  # Oblíbené barvy z tzlColors
        self._attr_favorite_colors = []  # Alternativní atribut pro oblíbené barvy
        self.hass = None  # Bude nastaveno později
        self.entity_id = None  # Bude nastaveno později
        # Inicializovat oblíbené barvy hned při vytvoření
        _LOGGER.info("=== __init__ called for TZL Zone %s ===", tzl_zone_data["zoneId"])
        _LOGGER.debug("shared_data.data exists: %s", bool(shared_data.data))
        _LOGGER.debug("Initial _attr_supported_color_list: %s", self._attr_supported_color_list)
        if shared_data.data:
            _LOGGER.debug("Calling _update_favorite_colors from __init__")
            self._update_favorite_colors(shared_data.data)
        else:
            _LOGGER.warning("No shared_data.data available in __init__")
        
        # Debug: Zkontrolovat, zda se atribut nastavil
        _LOGGER.debug("After init, _attr_supported_color_list: %s", self._attr_supported_color_list)
        self._attr_unique_id = (
            f"light.spa_tzl_zone"
            if count_tzl_zones == 1
            else f"light.spa_tzl_zone_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_zone_light"
            if count_tzl_zones == 1
            else f"tzl_zone_light_{tzl_zone_data['zoneId']}"
        )
        self.entity_id = self._attr_unique_id
        _LOGGER.debug("Set entity_id in __init__: %s", self.entity_id)

    async def async_added_to_hass(self):
        """Called when entity is added to Home Assistant."""
        _LOGGER.debug("Entity added to hass: %s", self.entity_id)
        
        # Nastavit oblíbené barvy po přidání do hass
        if self._attr_supported_color_list and self.entity_id is not None:
            _LOGGER.debug("Setting favorite colors in async_added_to_hass: %s", self._attr_supported_color_list)
            async_set_favorite_colors(self.hass, self.entity_id, self._attr_supported_color_list)
        elif self._attr_supported_color_list and self.entity_id is None:
            _LOGGER.warning("Cannot set favorite colors - entity_id is None")
        else:
            _LOGGER.warning("No favorite colors to set in async_added_to_hass")

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
                # Nastavit stav světla - zapnuto pokud není OFF
                state = tzl_zone.get("state", "OFF")
                self._attr_is_on = state not in ["OFF", "DISABLED"]
                
                # Nastavit RGB barvu
                red = tzl_zone.get("red", 0)
                green = tzl_zone.get("green", 0)
                blue = tzl_zone.get("blue", 0)
                self._attr_rgb_color = (red, green, blue)
                
                # Nastavit jas (intensity 0-8 -> brightness 0-255) - pokud je vypnuto, jas = 0
                intensity = tzl_zone.get("intensity", 0)
                if self._attr_is_on and intensity > 0:
                    # Převést intensity (0-8) na brightness (0-255)
                    # intensity 0 = brightness 0 (vypnuto)
                    # intensity 1-8 = brightness 32-255 (lineární převod)
                    self._attr_brightness = int((intensity / 8) * 255)
                else:
                    self._attr_brightness = 0
                
                # Aktualizovat oblíbené barvy z tzlColors
                _LOGGER.debug("Calling _update_favorite_colors from async_update")
                self._update_favorite_colors(data)
                
                _LOGGER.debug("Updated TZL Zone Light %s: ON=%s, RGB=(%s,%s,%s), Brightness=%s", 
                             self._tzl_zone_data["zoneId"], self._attr_is_on, red, green, blue, self._attr_brightness)

    @property
    def is_on(self):
        return self._attr_is_on

    @property
    def rgb_color(self):
        return self._attr_rgb_color

    @property
    def brightness(self):
        return self._attr_brightness

    @property
    def supported_color_modes(self):
        """Vrátí podporované barevné módy - RGB pro výběrové barvy + jas."""
        return {ColorMode.RGB}

    @property
    def supported_features(self):
        """Vrátí podporované funkce."""
        return LightEntityFeature(0)

    # Odstraněna property metoda - Home Assistant čte přímo _attr_supported_color_list
    
    @property
    def favorite_colors(self):
        """Vrátí seznam oblíbených barev z tzlColors."""
        _LOGGER.debug("favorite_colors property called, returning: %s", self._attr_favorite_colors)
        return self._attr_favorite_colors

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
                # Získat dostupné barvy z tzlColors
                available_colors = []
                tzl_colors = data.get("tzlColors", [])
                for color in tzl_colors:
                    available_colors.append({
                        "color_id": color.get("colorId"),
                        "rgb": [color.get("red", 0), color.get("green", 0), color.get("blue", 0)],
                        "is_secondary": color.get("isSecondary", False)
                    })
                
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "speed": tzl_zone.get("speed"),
                    "zone_id": tzl_zone.get("zoneId"),
                    "available_colors": available_colors,
                    "current_state": tzl_zone.get("state"),
                    "favorite_colors": self._attr_supported_color_list,  # Oblíbené barvy pro custom cards
                    "supported_color_list": self._attr_supported_color_list,  # Alternativní název
                    "debug_supported_color_list": self._attr_supported_color_list,  # Debug info
                    "debug_color_modes": self._attr_supported_color_modes,  # Debug info
                }
                return attrs

    def _update_favorite_colors(self, data):
        """Aktualizuje seznam oblíbených barev z tzlColors."""
        _LOGGER.info("=== _update_favorite_colors called ===")
        _LOGGER.debug("Full data keys: %s", list(data.keys()) if data else "No data")
        
        tzl_colors = data.get("tzlColors", [])
        _LOGGER.debug("tzlColors found: %s items", len(tzl_colors))
        _LOGGER.debug("tzlColors content: %s", tzl_colors)
        
        favorite_colors = []
        
        for i, color in enumerate(tzl_colors):
            _LOGGER.debug("Processing color %s: %s", i, color)
            # Přidat RGB barvu do oblíbených (maximálně 8 barev)
            if len(favorite_colors) < 8:
                # Načíst skutečné barvy z tzlColors
                red = color.get("red", 0)
                green = color.get("green", 0)
                blue = color.get("blue", 0)
                
                # Použít formát jako v ukázkovém kódu: {"rgb_color": [R, G, B]}
                rgb_color_dict = {"rgb_color": [red, green, blue]}
                
                # Použít dict formát (jako v ukázkovém kódu)
                favorite_colors.append(rgb_color_dict)           
        
        self._attr_supported_color_list = favorite_colors
        self._attr_favorite_colors = favorite_colors  # Alternativní atribut
        
        # Nastavit oblíbené barvy pomocí entity registry (jako Scenery)
        if hasattr(self, 'hass') and hasattr(self, 'entity_id') and self.entity_id is not None:
            _LOGGER.debug("Calling async_set_favorite_colors from _update_favorite_colors")
            async_set_favorite_colors(self.hass, self.entity_id, favorite_colors)
        else:
            _LOGGER.warning("Cannot set favorite colors - hass: %s, entity_id: %s", 
                          hasattr(self, 'hass'), getattr(self, 'entity_id', 'NOT_SET'))
        
        _LOGGER.debug("Final favorite colors for TZL Zone %s: %s", 
                     self._tzl_zone_data["zoneId"], favorite_colors)
        _LOGGER.debug("Current _attr_supported_color_list: %s", self._attr_supported_color_list)
        _LOGGER.debug("Current _attr_favorite_colors: %s", self._attr_favorite_colors)
        
        # Zkusit také nastavit jako dict pro Home Assistant
        if hasattr(self, '_attr_supported_color_list'):
            _LOGGER.debug("_attr_supported_color_list exists and has value: %s", 
                        getattr(self, '_attr_supported_color_list', 'NOT_FOUND'))
        
        # Zkusit také přidat do extra_state_attributes pro debugging
        if not hasattr(self, '_debug_colors_set'):
            self._debug_colors_set = True
            _LOGGER.debug("Setting debug flag for colors")

    async def async_turn_on(self, **kwargs):
        """Zapnout světlo s možnými parametry jasu a výběrových barev."""
        data = self._shared_data.data
        if not data:
            _LOGGER.error("No data available for TZL zone control")
            return
            
        try:
            self._shared_data.pause_updates()
            
            # Získat dostupné barvy
            tzl_colors = data.get("tzlColors", [])
            available_rgb_colors = [
                (color.get("red", 0), color.get("green", 0), color.get("blue", 0))
                for color in tzl_colors
            ]
            
            _LOGGER.info("Turn on TZL Zone %s with params: %s", self._tzl_zone_data["zoneId"], kwargs)
            
            # Zkontrolovat aktuální stav zóny
            current_tzl_zone = next(
                (
                    zone
                    for zone in data.get("tzlZones", [])
                    if zone["zoneId"] == self._tzl_zone_data["zoneId"]
                ),
                None,
            )
            
            current_state = current_tzl_zone.get("state", "OFF") if current_tzl_zone else "OFF"
            _LOGGER.info("Current state of TZL Zone %s: %s", self._tzl_zone_data["zoneId"], current_state)
            
            # Zapnout zónu na režim NORMAL pouze pokud je aktuálně OFF
            if current_state == "OFF":
                _LOGGER.info("Zone is OFF, switching to NORMAL mode")
                response_data = await self._shared_data._client.setChromazoneFunction(
                    "NORMAL", 
                    self._tzl_zone_data["zoneId"]
                )
                
                if response_data is None:
                    _LOGGER.warning("Function setChromazoneFunction (NORMAL), parameter is not supported")
                    return
            else:
                _LOGGER.info("Zone is already ON (state: %s), skipping setChromazoneFunction", current_state)
            
            # Zpracovat jas - převést z Home Assistant brightness (0-255) na TZL intensity (0-8)
            if "brightness" in kwargs:
                brightness = kwargs["brightness"]
                # Převést brightness (0-255) na intensity (0-8)
                intensity = max(0, min(8, round(brightness * 8 / 255)))
                _LOGGER.info("Set brightness to: %s (intensity: %s)", brightness, intensity)
                
                # Nastavit intenzitu
                intensity_response = await self._shared_data._client.setChromazoneBrightness(
                    intensity, 
                    self._tzl_zone_data["zoneId"]
                )
                
                if intensity_response is None:
                    _LOGGER.warning("Function setChromazoneBrightness, parameter %s is not supported", intensity)
                else:
                    _LOGGER.info("Úspěšně nastavena intenzita TZL zóny %s na %s", self._tzl_zone_data["zoneId"], intensity)
            
            # Zpracovat barvu z výběrových barev
            if "rgb_color" in kwargs:
                rgb = kwargs["rgb_color"]
                # Najít odpovídající color_id pro danou RGB barvu
                color_id = None
                for color in tzl_colors:
                    if (color.get("red", 0) == rgb[0] and 
                        color.get("green", 0) == rgb[1] and 
                        color.get("blue", 0) == rgb[2]):
                        color_id = color.get("colorId")
                        break
                
                if color_id is not None:
                    _LOGGER.info("Set selected color to: %s (color_id: %s)", rgb, color_id)
                    
                    # Nastavit barvu
                    color_response = await self._shared_data._client.setChromazoneColor(
                        color_id, 
                        self._tzl_zone_data["zoneId"]
                    )
                    
                    if color_response is None:
                        _LOGGER.warning("Function setChromazoneColor, parameter %s is not supported", color_id)
                    else:
                        _LOGGER.info("Úspěšně nastavena barva TZL zóny %s na color_id %s", self._tzl_zone_data["zoneId"], color_id)
                else:
                    _LOGGER.warning("Selected color %s not found in available colors: %s", rgb, available_rgb_colors)
                    # Najít nejbližší dostupnou barvu
                    closest_color = self._find_closest_color(rgb, available_rgb_colors)
                    _LOGGER.info("Using closest available color: %s", closest_color)
                    
                    # Zkusit najít color_id pro nejbližší barvu
                    for color in tzl_colors:
                        if (color.get("red", 0) == closest_color[0] and 
                            color.get("green", 0) == closest_color[1] and 
                            color.get("blue", 0) == closest_color[2]):
                            color_id = color.get("colorId")
                            break
                    
                    if color_id is not None:
                        color_response = await self._shared_data._client.setChromazoneColor(
                            color_id, 
                            self._tzl_zone_data["zoneId"]
                        )
                        if color_response:
                            _LOGGER.info("Úspěšně nastavena nejbližší barva TZL zóny %s na color_id %s", self._tzl_zone_data["zoneId"], color_id)
            
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning on TZL zone %s: %s", self._tzl_zone_data["zoneId"], str(e))
        finally:
            self._shared_data.resume_updates()

    def _find_closest_color(self, target_rgb, available_colors):
        """Najde nejbližší dostupnou barvu k cílové barvě."""
        if not available_colors:
            return target_rgb
            
        min_distance = float('inf')
        closest_color = available_colors[0]
        
        for color in available_colors:
            # Vypočítat euklidovskou vzdálenost v RGB prostoru
            distance = sum((a - b) ** 2 for a, b in zip(target_rgb, color)) ** 0.5
            if distance < min_distance:
                min_distance = distance
                closest_color = color
                
        return closest_color

    async def async_turn_off(self, **kwargs):
        """Vypnout světlo."""
        try:
            self._shared_data.pause_updates()
            
            # Volání API pro vypnutí TZL zóny
            response_data = await self._shared_data._client.setChromazoneFunction(
                "OFF", 
                self._tzl_zone_data["zoneId"]
            )
            
            if response_data is None:
                _LOGGER.warning("Function setChromazoneFunction (OFF), parameter is not supported")
                return
            
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
                    _LOGGER.info("Úspěšně vypnuta TZL zóna %s", self._tzl_zone_data["zoneId"])
                else:
                    _LOGGER.warning(
                        "TZL zone %s was not turned off. Expected state: OFF, Current state: %s",
                        self._tzl_zone_data["zoneId"],
                        new_state
                    )
            else:
                _LOGGER.error("No API response for turning off TZL zone %s", self._tzl_zone_data["zoneId"])
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off TZL zone %s: %s", self._tzl_zone_data["zoneId"], str(e))
        finally:
            self._shared_data.resume_updates()