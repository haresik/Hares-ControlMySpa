"""Energy sensor entities for Energy Dashboard."""

from datetime import datetime
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.restore_state import RestoreEntity
from .base import SpaSensorBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaHeaterEnergySensor(SpaSensorBase, RestoreEntity):
    """Senzor pro energii heateru (kWh) - používá se pro Energy Dashboard."""
    def __init__(self, shared_data, device_info, heater_data, count_heater, config_options):
        self._shared_data = shared_data
        self._heater_data = heater_data
        self._config_options = config_options
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._total_energy_kwh = 0.0  # Celková spotřeba v kWh
        self._last_update_time = None
        self._last_heater_state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightning-bolt-circle"
        
        # Určit port pro získání konfiguračního výkonu
        heater_port = heater_data.get('port')
        if heater_port is None or count_heater == 1:
            config_key = "heater_1_power_watts"
        else:
            port_num = int(heater_port) + 1
            config_key = f"heater_{port_num}_power_watts"
        
        # Načíst výkon z konfigurace (výchozí 3000 W)
        self._heater_power_watts = config_options.get(config_key, 2800)
        
        self._attr_unique_id = (
            f"sensor.{self._attr_device_info['serial_number']}_spa_heater_energy"
            if count_heater == 1 or heater_data['port'] is None
            else f"sensor.{self._attr_device_info['serial_number']}_spa_heater_energy_{int(heater_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "heater_energy"
            if count_heater == 1 or heater_data['port'] is None
            else f"heater_energy_{int(heater_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_added_to_hass(self):
        """Obnovit stav po restartu Home Assistant."""
        await super().async_added_to_hass()
        
        # Obnovit předchozí stav z databáze
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable", None):
            try:
                # Obnovit uloženou hodnotu energie
                restored_value = float(last_state.state)
                self._total_energy_kwh = restored_value
                _LOGGER.info("Restored Heater Energy %s: %s kWh from previous session", 
                           self._heater_data["port"], round(self._total_energy_kwh, 3))
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore energy value for heater %s: %s", 
                              self._heater_data["port"], last_state.state)
        
        # Obnovit také čas posledního update (pokud je dostupný v atributech)
        if last_state is not None and last_state.attributes:
            last_update_str = last_state.attributes.get("last_update_time")
            if last_update_str:
                try:
                    self._last_update_time = datetime.fromisoformat(last_update_str)
                    self._last_heater_state = last_state.attributes.get("last_heater_state", "OFF")
                except (ValueError, TypeError):
                    pass

    async def async_update(self):
        data = self._shared_data.data
        current_time = datetime.now()
        
        if data:
            # Najít odpovídající HEATER podle portu
            heater_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "HEATER" and comp["port"] == self._heater_data["port"]
                ),
                None,
            )
            
            current_heater_state = heater_comp["value"] if heater_comp else "OFF"
            is_heater_on = current_heater_state != "OFF" and current_heater_state != "WAITING"
            
            # Pokud máme předchozí update, počítat spotřebu
            if self._last_update_time is not None:
                time_delta = current_time - self._last_update_time
                hours_elapsed = time_delta.total_seconds() / 3600.0
                
                # Pokud byl heater zapnutý během tohoto období, přidat spotřebu
                if self._last_heater_state is not None and self._last_heater_state != "OFF":
                    # Přidat spotřebu: výkon (W) * čas (h) / 1000 = kWh
                    energy_added = (self._heater_power_watts * hours_elapsed) / 1000.0
                    self._total_energy_kwh += energy_added
                    _LOGGER.debug("Heater Energy %s: Added %s kWh (power: %s W, time: %s h)", 
                                 self._heater_data["port"], round(energy_added, 6), 
                                 self._heater_power_watts, round(hours_elapsed, 4))
            
            # Aktualizovat čas a stav
            self._last_update_time = current_time
            self._last_heater_state = current_heater_state
            
            _LOGGER.debug("Updated Heater Energy %s: %s kWh (state: %s)", 
                         self._heater_data["port"], round(self._total_energy_kwh, 3), current_heater_state)
        else:
            # Pokud nejsou dostupná data, inicializovat čas (ale neresetovat energii)
            if self._last_update_time is None:
                self._last_update_time = current_time
                self._last_heater_state = "OFF"

    @property
    def native_value(self):
        return round(self._total_energy_kwh, 3)

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy pro uložení stavu."""
        attrs = {}
        if self._last_update_time is not None:
            attrs["last_update_time"] = self._last_update_time.isoformat()
        if self._last_heater_state is not None:
            attrs["last_heater_state"] = self._last_heater_state
        return attrs


class SpaPumpEnergySensor(SpaSensorBase, RestoreEntity):
    """Senzor pro energii pumpy (kWh) - používá se pro Energy Dashboard."""
    def __init__(self, shared_data, device_info, pump_data, count_pump, config_options):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._config_options = config_options
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._total_energy_kwh = 0.0  # Celková spotřeba v kWh
        self._last_update_time = None
        self._last_pump_state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightning-bolt-circle"
        
        # Určit port pro získání konfiguračního výkonu
        pump_port = pump_data.get('port')
        if pump_port is None or count_pump == 1:
            config_key = "pump_1_power_watts"
        else:
            port_num = int(pump_port) + 1
            config_key = f"pump_{port_num}_power_watts"
        
        # Načíst výkon z konfigurace (výchozí 2000 W)
        self._pump_power_watts = config_options.get(config_key, 2200)
        
        self._attr_unique_id = (
            f"sensor.{self._attr_device_info['serial_number']}_spa_pump_energy"
            if count_pump == 1 or pump_data['port'] is None
            else f"sensor.{self._attr_device_info['serial_number']}_spa_pump_energy_{int(pump_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "pump_energy"
            if count_pump == 1 or pump_data['port'] is None
            else f"pump_energy_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_added_to_hass(self):
        """Obnovit stav po restartu Home Assistant."""
        await super().async_added_to_hass()
        
        # Obnovit předchozí stav z databáze
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable", None):
            try:
                # Obnovit uloženou hodnotu energie
                restored_value = float(last_state.state)
                self._total_energy_kwh = restored_value
                _LOGGER.info("Restored Pump Energy %s: %s kWh from previous session", 
                           self._pump_data["port"], round(self._total_energy_kwh, 3))
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore energy value for pump %s: %s", 
                              self._pump_data["port"], last_state.state)
        
        # Obnovit také čas posledního update (pokud je dostupný v atributech)
        if last_state is not None and last_state.attributes:
            last_update_str = last_state.attributes.get("last_update_time")
            if last_update_str:
                try:
                    self._last_update_time = datetime.fromisoformat(last_update_str)
                    self._last_pump_state = last_state.attributes.get("last_pump_state", "OFF")
                except (ValueError, TypeError):
                    pass

    async def async_update(self):
        data = self._shared_data.data
        current_time = datetime.now()
        
        if data:
            # Najít odpovídající PUMP podle portu
            pump_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]
                ),
                None,
            )
            
            current_pump_state = pump_comp["value"] if pump_comp else "OFF"
            
            # Pokud máme předchozí update, počítat spotřebu
            if self._last_update_time is not None:
                time_delta = current_time - self._last_update_time
                hours_elapsed = time_delta.total_seconds() / 3600.0
                
                # Pokud byla pumpa zapnutá během tohoto období (není OFF), přidat spotřebu
                if self._last_pump_state is not None and self._last_pump_state != "OFF":
                    # Přidat spotřebu: výkon (W) * čas (h) / 1000 = kWh
                    energy_added = (self._pump_power_watts * hours_elapsed) / 1000.0
                    self._total_energy_kwh += energy_added
                    _LOGGER.debug("Pump Energy %s: Added %s kWh (power: %s W, time: %s h, total: %s kWh)", 
                                 self._pump_data["port"], round(energy_added, 6), 
                                 self._pump_power_watts, round(hours_elapsed, 4), round(self._total_energy_kwh, 3))
            
            # Aktualizovat čas a stav
            self._last_update_time = current_time
            self._last_pump_state = current_pump_state
            
            _LOGGER.debug("Updated Pump Energy %s: %s kWh (state: %s)", 
                         self._pump_data["port"], round(self._total_energy_kwh, 3), current_pump_state)
        else:
            # Pokud nejsou dostupná data, inicializovat čas (ale neresetovat energii)
            if self._last_update_time is None:
                self._last_update_time = current_time
                self._last_pump_state = "OFF"

    @property
    def native_value(self):
        return round(self._total_energy_kwh, 3)

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy pro uložení stavu."""
        attrs = {}
        if self._last_update_time is not None:
            attrs["last_update_time"] = self._last_update_time.isoformat()
        if self._last_pump_state is not None:
            attrs["last_pump_state"] = self._last_pump_state
        return attrs


class SpaBlowerEnergySensor(SpaSensorBase, RestoreEntity):
    """Senzor pro energii bloweru (kWh) - používá se pro Energy Dashboard."""
    def __init__(self, shared_data, device_info, blower_data, count_blower, config_options):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._config_options = config_options
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._total_energy_kwh = 0.0  # Celková spotřeba v kWh
        self._last_update_time = None
        self._last_blower_state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightning-bolt-circle"
        
        # Určit port pro získání konfiguračního výkonu
        blower_port = blower_data.get('port')
        if blower_port is None or count_blower == 1:
            config_key = "blower_1_power_watts"
        else:
            port_num = int(blower_port) + 1
            config_key = f"blower_{port_num}_power_watts"
        
        # Načíst výkon z konfigurace (výchozí 1500 W)
        self._blower_power_watts = config_options.get(config_key, 900)
        
        self._attr_unique_id = (
            f"sensor.{self._attr_device_info['serial_number']}_spa_blower_energy"
            if count_blower == 1 or blower_data['port'] is None
            else f"sensor.{self._attr_device_info['serial_number']}_spa_blower_energy_{int(blower_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "blower_energy"
            if count_blower == 1 or blower_data['port'] is None
            else f"blower_energy_{int(blower_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_added_to_hass(self):
        """Obnovit stav po restartu Home Assistant."""
        await super().async_added_to_hass()
        
        # Obnovit předchozí stav z databáze
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable", None):
            try:
                # Obnovit uloženou hodnotu energie
                restored_value = float(last_state.state)
                self._total_energy_kwh = restored_value
                _LOGGER.info("Restored Blower Energy %s: %s kWh from previous session", 
                           self._blower_data["port"], round(self._total_energy_kwh, 3))
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore energy value for blower %s: %s", 
                              self._blower_data["port"], last_state.state)
        
        # Obnovit také čas posledního update (pokud je dostupný v atributech)
        if last_state is not None and last_state.attributes:
            last_update_str = last_state.attributes.get("last_update_time")
            if last_update_str:
                try:
                    self._last_update_time = datetime.fromisoformat(last_update_str)
                    self._last_blower_state = last_state.attributes.get("last_blower_state", "OFF")
                except (ValueError, TypeError):
                    pass

    async def async_update(self):
        data = self._shared_data.data
        current_time = datetime.now()
        
        if data:
            # Najít odpovídající BLOWER podle portu
            blower_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "BLOWER" and comp["port"] == self._blower_data["port"]
                ),
                None,
            )
            
            current_blower_state = blower_comp["value"] if blower_comp else "OFF"
            
            # Pokud máme předchozí update, počítat spotřebu
            if self._last_update_time is not None:
                time_delta = current_time - self._last_update_time
                hours_elapsed = time_delta.total_seconds() / 3600.0
                
                # Pokud byl blower zapnutý během tohoto období (není OFF), přidat spotřebu
                if self._last_blower_state is not None and self._last_blower_state != "OFF":
                    # Přidat spotřebu: výkon (W) * čas (h) / 1000 = kWh
                    energy_added = (self._blower_power_watts * hours_elapsed) / 1000.0
                    self._total_energy_kwh += energy_added
                    _LOGGER.debug("Blower Energy %s: Added %s kWh (power: %s W, time: %s h)", 
                                 self._blower_data["port"], round(energy_added, 6), 
                                 self._blower_power_watts, round(hours_elapsed, 4))
            
            # Aktualizovat čas a stav
            self._last_update_time = current_time
            self._last_blower_state = current_blower_state
            
            _LOGGER.debug("Updated Blower Energy %s: %s kWh (state: %s)", 
                         self._blower_data["port"], round(self._total_energy_kwh, 3), current_blower_state)
        else:
            # Pokud nejsou dostupná data, inicializovat čas (ale neresetovat energii)
            if self._last_update_time is None:
                self._last_update_time = current_time
                self._last_blower_state = "OFF"

    @property
    def native_value(self):
        return round(self._total_energy_kwh, 3)

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy pro uložení stavu."""
        attrs = {}
        if self._last_update_time is not None:
            attrs["last_update_time"] = self._last_update_time.isoformat()
        if self._last_blower_state is not None:
            attrs["last_blower_state"] = self._last_blower_state
        return attrs


class SpaCirculationPumpEnergySensor(SpaSensorBase, RestoreEntity):
    """Senzor pro energii circulation pumpu (kWh) - používá se pro Energy Dashboard."""
    def __init__(self, shared_data, device_info, pump_data, count_pump, config_options):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._config_options = config_options
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._total_energy_kwh = 0.0  # Celková spotřeba v kWh
        self._last_update_time = None
        self._last_pump_state = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:lightning-bolt-circle"
        
        # Určit port pro získání konfiguračního výkonu
        pump_port = pump_data.get('port')
        if pump_port is None or count_pump == 1:
            config_key = "circulation_pump_1_power_watts"
        else:
            port_num = int(pump_port) + 1
            config_key = f"circulation_pump_{port_num}_power_watts"
        
        # Načíst výkon z konfigurace (výchozí 500 W)
        self._circulation_pump_power_watts = config_options.get(config_key, 400)
        
        self._attr_unique_id = (
            f"sensor.{self._attr_device_info['serial_number']}_spa_circulation_pump_energy"
            if count_pump == 1 or pump_data['port'] is None
            else f"sensor.{self._attr_device_info['serial_number']}_spa_circulation_pump_energy_{int(pump_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "circulation_pump_energy"
            if count_pump == 1 or pump_data['port'] is None
            else f"circulation_pump_energy_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

    async def async_added_to_hass(self):
        """Obnovit stav po restartu Home Assistant."""
        await super().async_added_to_hass()
        
        # Obnovit předchozí stav z databáze
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable", None):
            try:
                # Obnovit uloženou hodnotu energie
                restored_value = float(last_state.state)
                self._total_energy_kwh = restored_value
                _LOGGER.info("Restored Circulation Pump Energy %s: %s kWh from previous session", 
                           self._pump_data["port"], round(self._total_energy_kwh, 3))
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore energy value for circulation pump %s: %s", 
                              self._pump_data["port"], last_state.state)
        
        # Obnovit také čas posledního update (pokud je dostupný v atributech)
        if last_state is not None and last_state.attributes:
            last_update_str = last_state.attributes.get("last_update_time")
            if last_update_str:
                try:
                    self._last_update_time = datetime.fromisoformat(last_update_str)
                    self._last_pump_state = last_state.attributes.get("last_pump_state", "OFF")
                except (ValueError, TypeError):
                    pass

    async def async_update(self):
        data = self._shared_data.data
        current_time = datetime.now()
        
        if data:
            # Najít odpovídající CIRCULATION_PUMP podle portu
            pump_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "CIRCULATION_PUMP" and comp["port"] == self._pump_data["port"]
                ),
                None,
            )
            
            current_pump_state = pump_comp["value"] if pump_comp else "OFF"
            
            # Pokud máme předchozí update, počítat spotřebu
            if self._last_update_time is not None:
                time_delta = current_time - self._last_update_time
                hours_elapsed = time_delta.total_seconds() / 3600.0
                
                # Pokud bylo čerpadlo zapnuté během tohoto období (není OFF), přidat spotřebu
                if self._last_pump_state is not None and self._last_pump_state != "OFF":
                    # Přidat spotřebu: výkon (W) * čas (h) / 1000 = kWh
                    energy_added = (self._circulation_pump_power_watts * hours_elapsed) / 1000.0
                    self._total_energy_kwh += energy_added
                    _LOGGER.debug("Circulation Pump Energy %s: Added %s kWh (power: %s W, time: %s h, total: %s kWh)", 
                                 self._pump_data["port"], round(energy_added, 6), 
                                 self._circulation_pump_power_watts, round(hours_elapsed, 4), round(self._total_energy_kwh, 3))
            
            # Aktualizovat čas a stav
            self._last_update_time = current_time
            self._last_pump_state = current_pump_state
            
            _LOGGER.debug("Updated Circulation Pump Energy %s: %s kWh (state: %s)", 
                         self._pump_data["port"], round(self._total_energy_kwh, 3), current_pump_state)
        else:
            # Pokud nejsou dostupná data, inicializovat čas (ale neresetovat energii)
            if self._last_update_time is None:
                self._last_update_time = current_time
                self._last_pump_state = "OFF"

    @property
    def native_value(self):
        return round(self._total_energy_kwh, 3)

    @property
    def extra_state_attributes(self):
        """Vrátí dodatečné atributy pro uložení stavu."""
        attrs = {}
        if self._last_update_time is not None:
            attrs["last_update_time"] = self._last_update_time.isoformat()
        if self._last_pump_state is not None:
            attrs["last_pump_state"] = self._last_pump_state
        return attrs

