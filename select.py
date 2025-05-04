from datetime import timedelta
from homeassistant.components.select import SelectEntity
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Nastavení intervalu aktualizace na 2 minuty
SCAN_INTERVAL = timedelta(minutes=2)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]

    # Vytvoření sdíleného objektu pro data
    shared_data = SpaData(client)

    # Najít všechny PUMP komponenty
    await shared_data.update()
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]
    # Najít všechny BLOWER komponenty
    blowers = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "BLOWER"
    ]
    # Najít všechny LIGHT komponenty
    lights = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "LIGHT"
    ]

    # Vytvořit entity pro každou PUMP
    entities = [SpaPumpSelect(shared_data, pump) for pump in pumps]
    entities += [SpaBlowerSelect(shared_data, blower) for blower in blowers]
    entities += [SpaLightSelect(shared_data, light) for light in lights]
    entities.append(SpaTempRangeSelect(shared_data))  # Přidat existující entitu

    async_add_entities(entities, True)

class SpaData:
    """Sdílený objekt pro uchování dat z webového dotazu."""
    def __init__(self, client):
        self._client = client
        self._data = None

    async def update(self):
        """Aktualizace dat z webového dotazu."""
        self._data = await self._client.getSpa()
        _LOGGER.debug("Shared data updated: %s", self._data)

    @property
    def data(self):
        """Vrací aktuální data."""
        return self._data

class SpaTempRangeSelect(SelectEntity):
    def __init__(self, shared_data):
        self._shared_data = shared_data
        self._attr_name = "Spa Temperature Range"
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"   
 
    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
        data = self._shared_data.data
        if data:
            self._attr_current_option = data.get("tempRange")
            _LOGGER.debug("Updated tempRange: %s", self._attr_current_option)

    async def async_select_option(self, option: str):
        """Změna hodnoty tempRange a odeslání do zařízení."""
        if option in self._attr_options:
            success = await self._shared_data._client.setTempRange(option == "HIGH")
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set tempRange to %s", option)
            else:
                _LOGGER.error("Failed to set tempRange to %s", option)
 # type: ignore

class SpaPumpSelect(SelectEntity):
    def __init__(self, shared_data, pump_data):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_name = f"Spa Pump {pump_data['port']}"  # Název na základě portu
        self._attr_options = pump_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
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

    async def async_select_option(self, option: str):
        """Změna hodnoty PUMP a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._pump_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Pump: %s", self._pump_data["port"])
                return

            # Simulace odeslání příkazu do zařízení
            success = await self._shared_data._client.setJetState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Pump %s to %s", self._pump_data["port"], option)
            else:
                _LOGGER.error("Failed to set Pump %s to %s", self._pump_data["port"], option)

class SpaLightSelect(SelectEntity):
    def __init__(self, shared_data, light_data):
        self._shared_data = shared_data
        self._light_data = light_data
        self._attr_name = f"Spa Light {light_data['port']}"  # Název na základě portu
        self._attr_options = light_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
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

    async def async_select_option(self, option: str):
        """Změna hodnoty LIGHT a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._light_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Light: %s", self._light_data["port"])
                return

            success = await self._shared_data._client.setLightState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Light %s to %s", self._light_data["port"], option)
            else:
                _LOGGER.error("Failed to set Light %s to %s", self._light_data["port"], option)

class SpaBlowerSelect(SelectEntity):
    def __init__(self, shared_data, blower_data):
        self._shared_data = shared_data
        self._blower_data = blower_data
        self._attr_name = f"Spa Blower {blower_data['port']}"  # Název na základě portu
        self._attr_options = blower_data["availableValues"]  # Možnosti výběru
        self._attr_should_poll = True
        self._attr_current_option = None
        self._attr_unique_id = f"spa_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Informace o zařízení, ke kterému entita patří."""
        return {
            "identifiers": {(DOMAIN, "spa_device")},  # Unikátní identifikátor zařízení
            "name": "Spa Balboa Device",
            "manufacturer": "Balboa",
            "model": "Spa Model 1",
            "sw_version": "1.0",
        }

    async def async_update(self):
        await self._shared_data.update()  # Aktualizace sdílených dat
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

    async def async_select_option(self, option: str):
        """Změna hodnoty BLOWER a odeslání do zařízení."""
        if option in self._attr_options:
            try:
                device_number = int(self._blower_data["port"])  # Převod portu na číslo
            except (ValueError, TypeError):
                _LOGGER.error("Invalid port value for Blower: %s", self._blower_data["port"])
                return

            # Simulace odeslání příkazu do zařízení
            success = await self._shared_data._client.setBlowerState(device_number, option)
            if success:
                self._attr_current_option = option
                _LOGGER.info("Successfully set Blower %s to %s", self._blower_data["port"], option)
            else:
                _LOGGER.error("Failed to set Blower %s to %s", self._blower_data["port"], option)

