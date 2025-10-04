from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import HomeAssistant
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    # client = data["client"]
    shared_data = data["data"]
    device_info = data["device_info"]
    client = data["client"]

    if not client.userInfo:
        _LOGGER.error("Failed to initialize ControlMySpa client (No userInfo)")
        return False
    if not shared_data.data:
        return False

    # Najít všechny CIRCULATION_PUMP komponenty
    circulation_pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "CIRCULATION_PUMP"
    ]
    # Najít všechny FILTER komponenty
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]
    # Najít všechny OZONE komponenty
    ozones = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "OZONE"
    ]
    
    # Najít všechny TZL zones
    tzl_zones = shared_data.data.get("tzlZones", [])

    # Vytvořit entity pro každou CIRCULATION_PUMP
    entities = [SpaCirculationPumpSensor(shared_data, device_info, pump, len(circulation_pumps)) for pump in circulation_pumps]
    entities.append(SpaTemperatureSensor(shared_data, device_info))  # Aktuální teplota
    entities.append(SpaDesiredTemperatureSensor(shared_data, device_info))  # Požadovaná teplota
    entities += [SpaFilterSensor(shared_data, device_info, filter_data, len(filters)) for filter_data in filters]
    entities += [SpaOzoneSensor(shared_data, device_info, ozone_data, len(ozones)) for ozone_data in ozones]
    entities += [SpaTzlZoneSensor(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]
    entities += [SpaTzlZoneRgbSensor(shared_data, device_info, tzl_zone_data, len(tzl_zones)) for tzl_zone_data in tzl_zones]

    async_add_entities(entities, True)
    _LOGGER.debug("START Śensor control_my_spa")
    
    # Pro všechny entity proveď registraci jako odběratel
    for entity in entities:
        shared_data.register_subscriber(entity)

class SpaSensorBase(SensorEntity):
    _attr_has_entity_name = True

class SpaTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_current_temperature"
        self._attr_translation_key = f"current_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("currentTemp")
            if fahrenheit_temp is not None and fahrenheit_temp != 0:
                self._state = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                _LOGGER.debug("Updated current temperature (Celsius): %s", self._state)

    @property
    def native_value(self):
        return self._state

class SpaDesiredTemperatureSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info):
        self._shared_data = shared_data
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._high_range_value = None  # Poslední hodnota pro HIGH rozsah
        self._low_range_value = None   # Poslední hodnota pro LOW rozsah
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = device_info
        self._attr_unique_id = f"sensor.spa_desired_temperature"
        self._attr_translation_key = f"desired_temperature"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            fahrenheit_temp = data.get("desiredTemp")
            temp_range = data.get("tempRange")
            
            if fahrenheit_temp is not None:
                celsius_temp = round((fahrenheit_temp - 32) * 5.0 / 9.0, 1)  # Převod na Celsia
                self._state = celsius_temp
                
                # Uložit hodnotu podle aktuálního rozsahu
                if temp_range == "HIGH":
                    self._high_range_value = celsius_temp
                    _LOGGER.debug("Updated desired temperature (Celsius): %s (HIGH range)", self._state)
                elif temp_range == "LOW":
                    self._low_range_value = celsius_temp
                    _LOGGER.debug("Updated desired temperature (Celsius): %s (LOW range)", self._state)
                else:
                    _LOGGER.debug("Updated desired temperature (Celsius): %s (unknown range: %s)", self._state, temp_range)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy entity."""
        attrs = {}
        if self._high_range_value is not None:
            attrs["high_range_value"] = self._high_range_value
        if self._low_range_value is not None:
            attrs["low_range_value"] = self._low_range_value
        return attrs

class SpaCirculationPumpSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, pump_data, count_pump):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-tornado"
        self._attr_unique_id = f"sensor.spa_circulation_pump" if count_pump == 1 or pump_data['port'] == None else f"sensor.spa_circulation_pump_{pump_data['port']}"
        self._attr_translation_key = f"circulation_pump" if count_pump == 1 or pump_data['port'] == None else f"spa_circulation_pump_{pump_data['port']}"
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        # Data jsou již aktualizována v async_setup_entry
        data = self._shared_data.data
        if data:
            # Najít odpovídající CIRCULATION_PUMP podle portu
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "CIRCULATION_PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            if pump:
                self._state = pump["value"]  # Stav čerpadla 
                _LOGGER.debug("Updated Circulation Pump %s: %s", self._pump_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

class SpaFilterSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, filter_data, count_filter):
        self._shared_data = shared_data
        self._filter_data = filter_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:water-sync"
        self._attr_unique_id = (
            f"sensor.spa_filter"
            if count_filter == 1 or filter_data['port'] is None
            else f"sensor.spa_filter_{int(filter_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "filter"
            if count_filter == 1 or filter_data['port'] is None
            else f"filter_{int(filter_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající FILTER podle portu
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            if filter_comp:
                self._state = filter_comp["value"]
                _LOGGER.debug("Updated Filter %s: %s", self._filter_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající FILTER podle portu
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            if filter_comp:
                attrs = {
                    "Start time": f"{filter_comp['hour']} : {str(filter_comp['minute']).zfill(2)}",
                    "Duration ": filter_comp["durationMinutes"],
                }
                return attrs

class SpaOzoneSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, ozone_data, count_ozone):
        self._shared_data = shared_data
        self._ozone_data = ozone_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-hazy"
        self._attr_unique_id = (
            f"sensor.spa_ozone"
            if count_ozone == 1 or ozone_data['port'] is None
            else f"sensor.spa_ozone_{int(ozone_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "ozone"
            if count_ozone == 1 or ozone_data['port'] is None
            else f"ozone_{int(ozone_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_update(self):
        data = self._shared_data.data
        if data:
            # Najít odpovídající OZONE podle portu
            ozone_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "OZONE" and comp["port"] == self._ozone_data["port"]
                ),
                None,
            )
            if ozone_comp:
                self._state = ozone_comp["value"]
                _LOGGER.debug("Updated Ozone %s: %s", self._ozone_data["port"], self._state)

    @property
    def native_value(self):
        return self._state

class SpaTzlZoneSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_unique_id = (
            f"sensor.spa_tzl_zone"
            if count_tzl_zones == 1
            else f"sensor.spa_tzl_zone_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_zone"
            if count_tzl_zones == 1
            else f"tzl_zone_{tzl_zone_data['zoneId']}"
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
                self._state = tzl_zone["state"]
                _LOGGER.debug("Updated TZL Zone %s: %s", self._tzl_zone_data["zoneId"], self._state)

    @property
    def native_value(self):
        return self._state

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
                    "intensity": tzl_zone.get("intensity"),
                    "speed": tzl_zone.get("speed"),
                    "red": tzl_zone.get("red"),
                    "green": tzl_zone.get("green"),
                    "blue": tzl_zone.get("blue"),
                }
                return attrs


class SpaTzlZoneRgbSensor(SpaSensorBase):
    def __init__(self, shared_data, device_info, tzl_zone_data, count_tzl_zones):
        self._shared_data = shared_data
        self._tzl_zone_data = tzl_zone_data
        self._attr_native_unit_of_measurement = None  # Jednotka není potřeba
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:palette"
        self._attr_unique_id = (
            f"sensor.spa_tzl_rgb"
            if count_tzl_zones == 1
            else f"sensor.spa_tzl_rgb_{tzl_zone_data['zoneId']}"
        )
        self._attr_translation_key = (
            "tzl_rgb"
            if count_tzl_zones == 1
            else f"tzl_rgb_{tzl_zone_data['zoneId']}"
        )
        self.entity_id = self._attr_unique_id

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
            return f"🎨 RGB({red},{green},{blue})"

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
                red = tzl_zone.get("red", 0)
                green = tzl_zone.get("green", 0)
                blue = tzl_zone.get("blue", 0)
                
                # Vytvořit popisný název barvy místo jen RGB hodnot
                color_name = self._get_color_name(red, green, blue)
                self._state = color_name
                
                _LOGGER.debug("Updated TZL RGB Sensor %s: %s", 
                             self._tzl_zone_data["zoneId"], color_name)

    @property
    def native_value(self):
        return self._state

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
                hex_color = f"#{red:02x}{green:02x}{blue:02x}".upper()
                
                attrs = {
                    "zone_name": tzl_zone.get("zoneName"),
                    "zone_id": tzl_zone.get("zoneId"),
                    "red": red,
                    "green": green,
                    "blue": blue,
                    "hex": hex_color,
                    "state": tzl_zone.get("state"),
                    "intensity": tzl_zone.get("intensity"),
                }
                return attrs
