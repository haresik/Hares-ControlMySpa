from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

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
    # entities = [SpaTzlZoneLight(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    entities = []  # Prázdný seznam, protože Light entity jsou zakomentované - JEN TEST !!!!!!!!!!!

    async_add_entities(entities, True)
    _LOGGER.debug("START Light control_my_spa")
    
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaTzlZoneLight(LightEntity):
    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = 0  # Žádné speciální funkce

    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_is_on = False
        self._attr_rgb_color = (0, 0, 0)
        self._attr_brightness = 0
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
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
                
                # Nastavit jas (intensity 0-255) - pokud je vypnuto, jas = 0
                intensity = tzl_zone.get("intensity", 0)
                self._attr_brightness = intensity if self._attr_is_on else 0
                
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
                }
                return attrs

    async def async_turn_on(self, **kwargs):
        """Zapnout světlo s možnými parametry barvy a jasu."""
        data = self._shared_data.data
        if not data:
            _LOGGER.error("No data available for TZL zone control")
            return
            
        # Získat dostupné barvy
        tzl_colors = data.get("tzlColors", [])
        available_rgb_colors = [
            (color.get("red", 0), color.get("green", 0), color.get("blue", 0))
            for color in tzl_colors
        ]
        
        # TODO: Implementovat volání API pro zapnutí TZL zóny
        _LOGGER.info("Turn on TZL Zone %s with params: %s", self._tzl_zone_data["zoneId"], kwargs)
        
        if "rgb_color" in kwargs:
            rgb = kwargs["rgb_color"]
            # Validovat barvu proti dostupným barvám
            if rgb in available_rgb_colors:
                _LOGGER.info("Set RGB color to: %s (validated)", rgb)
            else:
                _LOGGER.warning("RGB color %s not in available colors: %s", rgb, available_rgb_colors)
                # Najít nejbližší dostupnou barvu
                closest_color = self._find_closest_color(rgb, available_rgb_colors)
                _LOGGER.info("Using closest available color: %s", closest_color)
        
        if "brightness" in kwargs:
            brightness = kwargs["brightness"]
            _LOGGER.info("Set brightness to: %s", brightness)

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
        # TODO: Implementovat volání API pro vypnutí TZL zóny
        _LOGGER.info("Turn off TZL Zone %s", self._tzl_zone_data["zoneId"])