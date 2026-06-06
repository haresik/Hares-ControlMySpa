from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
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

    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT" and
        len(component.get("availableValues", ["OFF", "HIGH"])) == 2
    ]
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    filters = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "FILTER"
    ]

    _LOGGER.debug(
        "Filtered components for Switch - Lights: %d, Pumps: %d, Pumps Low: %d, Blowers: %d, Filters: %d",
        len(lights),
        len(pumps),
        0,
        len(blowers),
        len(filters)
    )

    entities = [SpaLightSwitch(shared_data, device_info, unique_id_suffix, light, len(lights)) for light in lights]
    entities += [SpaPumpSwitch(shared_data, device_info, pump, len(pumps), unique_id_suffix) for pump in pumps]
    entities += [SpaBlowerSwitch(shared_data, device_info, unique_id_suffix, blower, len(blowers)) for blower in blowers]

    if len(filters) >= 2:
        entities.append(SpaFilter2Switch(shared_data, device_info, unique_id_suffix, client))

    tzl_zones = shared_data.data.get("tzlZones", [])
    if tzl_zones:
        entities.append(SpaTzlPowerSwitch(shared_data, device_info, unique_id_suffix, client))

    entities.append(SpaPanelLockSwitch(shared_data, device_info, unique_id_suffix, client))

    async_add_entities(entities, True)
    _LOGGER.debug("START Switch control_my_spa")

    for entity in entities:
        shared_data.register_subscriber(entity)
        _LOGGER.debug("Created Switch (%s) (%s)", entity._attr_unique_id, entity.entity_id)


class SpaSwitchBase(SwitchEntity):
    _attr_has_entity_name = True


class SpaLightSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, unique_id_suffix, light_data, light_count):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightbulb"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_light"
            if light_count == 1 or light_data['port'] is None
            else f"switch.spa_light_{int(light_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = f"light" if light_count == 1 or light_data['port'] == None else f"light_{int(light_data['port']) + 1}"
        self.entity_id = self._attr_unique_id
        self._available_values = light_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = self._available_values[0]
        self._on_value = self._available_values[-1]
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        if self.is_on:
            return "mdi:lightbulb-on"
        else:
            return "mdi:lightbulb"

    def _get_light_state(self, data):
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
        self._is_processing = True
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
                    "Successfully %s light %s%s",
                    "turned on" if target_state == self._on_value else "turned off",
                    self._light_data["port"],
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Light %s was not %s. Expected: %s, Got: %s%s",
                    self._light_data["port"],
                    "turned on" if target_state == self._on_value else "turned off",
                    target_state,
                    new_state,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._light_data["port"])
            success = await self._try_set_light_state(device_number, self._on_value)
            if not success:
                _LOGGER.info("Retrying light on %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._on_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
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
            success = await self._try_set_light_state(device_number, self._off_value)
            if not success:
                _LOGGER.info("Retrying light off %s", self._light_data["port"])
                success = await self._try_set_light_state(device_number, self._off_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for light: %s", self._light_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off light (port %s): %s", self._light_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()


class SpaPumpSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count, unique_id_suffix=""):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        self._available_values = pump_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = "OFF"
        self._on_value = "HIGH"
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        else:
            return "mdi:weather-windy"

    def _calculate_is_on_state(self, value: str) -> bool:
        if not value:
            return False
        if value == "LOW":
            if "MED" not in self._available_values and "HIGH" not in self._available_values and "HI" not in self._available_values:
                return True
            elif "MED" not in self._available_values and ("HIGH" in self._available_values or "HI" in self._available_values):
                return False
            elif "MED" in self._available_values:
                return False
            else:
                return True
        elif value == "MED":
            if "HIGH" in self._available_values:
                return False
            else:
                return True
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
        self._is_processing = True
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
            expected_is_on = self._calculate_is_on_state(target_state)
            actual_is_on = self._calculate_is_on_state(new_state) if new_state else False
            if expected_is_on == actual_is_on:
                self._attr_is_on = actual_is_on
                _LOGGER.info(
                    "Successfully %s pump %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._pump_data["port"],
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump %s was not %s. Expected: %s (%s), Got: %s (%s)%s",
                    self._pump_data["port"],
                    "turned on" if expected_is_on else "turned off",
                    target_state, expected_is_on,
                    new_state, actual_is_on,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            success = await self._try_set_pump_state(device_number, self._on_value)
            if not success:
                _LOGGER.info("Retrying pump on %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._on_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
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
            success = await self._try_set_pump_state(device_number, self._off_value)
            if not success:
                _LOGGER.info("Retrying pump off %s", self._pump_data["port"])
                success = await self._try_set_pump_state(device_number, self._off_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()


class SpaPumpLowSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, pump_data, pump_count, unique_id_suffix=""):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-windy"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_low_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"switch.spa_low_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "low_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"low_pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        self._available_values = pump_data.get("availableValues", ["LOW", "HIGH"])
        if "LOW" in self._available_values:
            self._off_value = "LOW"
        elif "MED" in self._available_values:
            self._off_value = "MED"
        else:
            self._off_value = self._available_values[0] if self._available_values else "OFF"
        if "HIGH" in self._available_values or "HI" in self._available_values:
            self._on_value = "HIGH"
        elif "MED" in self._available_values:
            self._on_value = "MED"
        else:
            self._on_value = self._available_values[-1] if self._available_values else "HIGH"
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        else:
            return "mdi:weather-windy"

    def _calculate_is_on_state(self, value: str) -> bool:
        if not value:
            return False
        return value == self._on_value

    async def async_update(self):
        data = self._shared_data.data
        if data:
            pump = next(
                (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            _LOGGER.debug("Updated Pump Low %s: %s", self._pump_data["port"], pump["value"] if pump else "None")
            if pump:
                self._attr_is_on = self._calculate_is_on_state(pump["value"])
            else:
                self._attr_is_on = False

    async def _try_set_pump_state(self, device_number: int, target_state: str, is_retry: bool = False) -> bool:
        self._is_processing = True
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
            expected_is_on = self._calculate_is_on_state(target_state)
            actual_is_on = self._calculate_is_on_state(new_state) if new_state else False
            if expected_is_on == actual_is_on:
                self._attr_is_on = actual_is_on
                _LOGGER.info(
                    "Successfully %s pump low %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._pump_data["port"],
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Pump Low %s was not %s. Expected: %s (%s), Got: %s (%s)%s",
                    self._pump_data["port"],
                    "turned on" if expected_is_on else "turned off",
                    target_state, expected_is_on,
                    new_state, actual_is_on,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            success = await self._try_set_pump_state(device_number, self._on_value)
            if not success:
                _LOGGER.info("First attempt to turn on pump low %s failed", self._pump_data["port"])
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump low: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning on pump low (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._pump_data["port"])
            success = await self._try_set_pump_state(device_number, self._off_value)
            if not success:
                _LOGGER.info("First attempt to turn off pump low %s failed", self._pump_data["port"])
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for pump low: %s", self._pump_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off pump low (port %s): %s", self._pump_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()


class SpaBlowerSwitch(SpaSwitchBase):
    def __init__(self, shared_data, device_info, unique_id_suffix, blower_data, blower_count):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_device_info = device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_should_poll = False
        base_id = (
            f"switch.spa_blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"switch.spa_blower_{int(blower_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "blower"
            if blower_count == 1 or blower_data['port'] is None
            else f"blower_{int(blower_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id
        self._available_values = blower_data.get("availableValues", ["OFF", "HIGH"])
        self._off_value = "OFF"
        self._on_value = "HIGH"
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        else:
            return "mdi:weather-dust"

    def _calculate_is_on_state(self, value: str) -> bool:
        if not value:
            return False
        if value == "LOW":
            if "MED" not in self._available_values and "HIGH" not in self._available_values and "HI" not in self._available_values:
                return False
            elif "MED" not in self._available_values and ("HIGH" in self._available_values or "HI" in self._available_values):
                return True
            elif "MED" in self._available_values:
                return True
            else:
                return False
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
        self._is_processing = True
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
            expected_is_on = self._calculate_is_on_state(target_state)
            actual_is_on = self._calculate_is_on_state(new_state) if new_state else False
            if expected_is_on == actual_is_on:
                self._attr_is_on = actual_is_on
                _LOGGER.info(
                    "Successfully %s blower %s%s",
                    "turned on" if expected_is_on else "turned off",
                    self._blower_data["port"],
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Blower %s was not %s. Expected: %s (%s), Got: %s (%s)%s",
                    self._blower_data["port"],
                    "turned on" if expected_is_on else "turned off",
                    target_state, expected_is_on,
                    new_state, actual_is_on,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            device_number = int(self._blower_data["port"])
            success = await self._try_set_blower_state(device_number, self._on_value)
            if not success:
                _LOGGER.info("Retrying blower on %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._on_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
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
            success = await self._try_set_blower_state(device_number, self._off_value)
            if not success:
                _LOGGER.info("Retrying blower off %s", self._blower_data["port"])
                success = await self._try_set_blower_state(device_number, self._off_value, True)
            await self._shared_data.async_force_update()
        except ValueError:
            _LOGGER.error("Invalid port value for blower: %s", self._blower_data["port"])
        except Exception as e:
            _LOGGER.error("Error turning off blower (port %s): %s", self._blower_data["port"], str(e))
            raise
        finally:
            self._shared_data.resume_updates()


class SpaTzlPowerSwitch(SpaSwitchBase):
    """Switch for TZL/Chromazone lighting power."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = f"switch.spa_tzl_power{unique_id_suffix}"
        self._attr_translation_key = "tzl_power"
        self._attr_icon = "mdi:lightbulb-group"
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        if self.is_on:
            return "mdi:lightbulb-group"
        else:
            return "mdi:lightbulb-group-off"

    def _get_tzl_power_state(self, data):
        if not data:
            return False
        tzl_zones = data.get("tzlZones", [])
        if not tzl_zones:
            return False
        return any(zone.get("state") != "OFF" for zone in tzl_zones)

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_tzl_power_state(data)
            _LOGGER.debug("Updated TZL Power: %s", self._attr_is_on)

    async def _try_set_tzl_power_state(self, power_state: str, is_retry: bool = False) -> bool:
        self._is_processing = True
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
                    "Successfully %s TZL lights%s",
                    "turned on" if power_state == "ON" else "turned off",
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "TZL lights were not %s. Expected: %s, Got: %s%s",
                    "turned on" if power_state == "ON" else "turned off",
                    expected_state, new_state,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_tzl_power_state("ON")
            if not success:
                _LOGGER.info("Retrying TZL lights on")
                success = await self._try_set_tzl_power_state("ON", True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning on TZL lights: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_tzl_power_state("OFF")
            if not success:
                _LOGGER.info("Retrying TZL lights off")
                success = await self._try_set_tzl_power_state("OFF", True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off TZL lights: %s", str(e))
        finally:
            self._shared_data.resume_updates()


class SpaFilter2Switch(SpaSwitchBase):
    """Switch for second filter."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._attr_entity_category = EntityCategory.CONFIG
        self._client = client
        self._attr_unique_id = f"switch.spa_filter_2{unique_id_suffix}"
        self._attr_translation_key = "filter_2"
        self._attr_icon = "mdi:water-sync"
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        if self.is_on:
            return "mdi:water-sync"
        else:
            return "mdi:water-remove"

    def _get_filter2_state(self, data):
        if not data:
            return False
        filter_comp = next(
            (
                comp
                for comp in data["components"]
                if comp["componentType"] == "FILTER" and comp["port"] == "1"
            ),
            None,
        )
        if filter_comp:
            return filter_comp["value"] != "DISABLED"
        return False

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_filter2_state(data)
            _LOGGER.debug("Updated Filter 2: %s", self._attr_is_on)

    async def _try_set_filter2_state(self, state: str, is_retry: bool = False) -> bool:
        self._is_processing = True
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
                    "Successfully %s filter 2%s",
                    "turned on" if state == "ON" else "turned off",
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Filter 2 was not %s. Expected: %s, Got: %s%s",
                    "turned on" if state == "ON" else "turned off",
                    expected_state, new_state,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_filter2_state("ON")
            if not success:
                _LOGGER.info("Retrying filter 2 on")
                success = await self._try_set_filter2_state("ON", True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning on filter 2: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_filter2_state("OFF")
            if not success:
                _LOGGER.info("Retrying filter 2 off")
                success = await self._try_set_filter2_state("OFF", True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error turning off filter 2: %s", str(e))
        finally:
            self._shared_data.resume_updates()


class SpaPanelLockSwitch(SpaSwitchBase):
    """Switch to lock/unlock the physical spa control panel."""

    def __init__(self, shared_data, device_info, unique_id_suffix, client):
        self._shared_data = shared_data
        self._attr_device_info = device_info
        self._client = client
        self._attr_unique_id = f"switch.spa_panel_lock{unique_id_suffix}"
        self._attr_translation_key = "panel_lock"
        self._attr_icon = "mdi:lock"
        self._attr_entity_category = EntityCategory.CONFIG
        self._is_processing = False

    @property
    def available(self) -> bool:
        return not self._is_processing

    @property
    def icon(self):
        if self._is_processing:
            return "mdi:sync"
        if self.is_on:
            return "mdi:lock"
        else:
            return "mdi:lock-open"

    def _get_panel_lock_state(self, data):
        """Read panel lock state from spa data payload."""
        if not data:
            return False
        return bool(data.get("isPanelLocked", False))

    async def async_update(self):
        data = self._shared_data.data
        if data:
            self._attr_is_on = self._get_panel_lock_state(data)
            _LOGGER.debug("Updated Panel Lock: %s", self._attr_is_on)

    async def _try_set_panel_lock(self, locked: bool, is_retry: bool = False) -> bool:
        """Attempt to set panel lock state with response verification."""
        self._is_processing = True
        self.async_write_ha_state()
        try:
            response_data = await self._client.setPanelLock(locked)
            if response_data is None:
                _LOGGER.warning("setPanelLock(%s) returned None", locked)
                return False
            
            # ACK Check: Read the server response payload to ensure state changed successfully
            new_state = self._get_panel_lock_state(response_data)
            if new_state == locked:
                self._attr_is_on = new_state
                _LOGGER.info(
                    "Successfully %s panel lock%s",
                    "engaged" if locked else "released",
                    " (retry)" if is_retry else ""
                )
                return True
            else:
                _LOGGER.warning(
                    "Panel lock modification rejected by cloud endpoint. Expected: %s, Got: %s%s",
                    locked,
                    new_state,
                    " (retry)" if is_retry else ""
                )
                return False
        finally:
            self._is_processing = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        """Lock the panel."""
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_panel_lock(True)
            if not success:
                _LOGGER.info("Retrying panel lock engage")
                success = await self._try_set_panel_lock(True, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error engaging panel lock: %s", str(e))
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs):
        """Unlock the panel."""
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_panel_lock(False)
            if not success:
                _LOGGER.info("Retrying panel lock release")
                success = await self._try_set_panel_lock(False, True)
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error releasing panel lock: %s", str(e))
        finally:
            self._shared_data.resume_updates()
