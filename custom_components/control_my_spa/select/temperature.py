"""Temperature-related select entities."""

import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.helpers import translation

from ..const import DOMAIN
from .base import SpaSelectBase

_LOGGER = logging.getLogger(__name__)


class SpaTempRangeSelect(SpaSelectBase):
    """Select entity for spa temperature range."""
    
    def __init__(self, shared_data, device_info, unique_id_suffix, hass, config_options=None):
        self._shared_data = shared_data
        self._hass = hass  # Uložit hass objekt pro notifikace
        self._config_options = config_options or {}
        self._attr_options = ["HIGH", "LOW"]  # Možnosti výběru
        self._attr_should_poll = False  # Data jsou sdílena, posluchac
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:pool-thermometer"
        self._attr_unique_id = f"select.spa_temperature_range{unique_id_suffix}"
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
                            
                            # Porovnat hodnoty a zkontrolovat, zda je notifikace zapnutá v options
                            if (
                                abs(current_high_range_temp - new_desired_temp_c) > 0.1  # Tolerance 0.1°C
                                and self._config_options.get("enable_temp_change_notification", True)
                            ):
                                # Načtení překladů a sestavení notifikace
                                translations = await translation.async_get_translations(
                                    self._hass,
                                    self._hass.config.language,
                                    "notification",
                                )
                                notification_title = translations.get(
                                    f"component.{DOMAIN}.notification.temp_range_high_change.title",
                                    "Změna požadované teploty v HIGH rozsahu",
                                )
                                diff_c = new_desired_temp_c - current_high_range_temp
                                notification_message = translations.get(
                                    f"component.{DOMAIN}.notification.temp_range_high_change.message",
                                    "Požadovaná teplota v HIGH rozsahu se změnila!\n"
                                    "Předchozí hodnota: {previous_value}°C\n"
                                    "Nová hodnota: {new_value}°C\n"
                                    "Rozdíl: {diff}°C",
                                ).format(
                                    previous_value=current_high_range_temp,
                                    new_value=new_desired_temp_c,
                                    diff=f"{diff_c:+.1f}",
                                )

                                # Odeslat notifikaci
                                persistent_notification.async_create(
                                    self._hass,
                                    notification_message,
                                    title=notification_title,
                                    notification_id=f"spa_temp_change_{int(time.time())}"
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

class SpaHeaterModeSelect(SpaSelectBase):
    """Select entity for spa heater mode."""
    
    def __init__(self, shared_data, device_info, unique_id_suffix):
        self._shared_data = shared_data
        self._attr_options = ["READY", "REST", "READY_REST"]  
        self._attr_should_poll = False
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:radiator"
        self._attr_unique_id = f"select.spa_heater_mode{unique_id_suffix}"
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
