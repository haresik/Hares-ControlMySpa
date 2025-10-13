"""Filter-related select entities."""

from .base import SpaSelectBase
import logging

_LOGGER = logging.getLogger(__name__)


class SpaFilterTimeSelect(SpaSelectBase):
    """Select entity for spa filter time."""
    
    def __init__(self, shared_data, device_info, filter_data, count_filter):
        self._shared_data = shared_data
        self._filter_data = filter_data
        self._attr_options = shared_data._client.createTimeOptions()  # Použít metodu z ControlMySpa
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:clock-outline"
        self._attr_unique_id = (
            f"select.spa_filter_time"
            if count_filter == 1 or filter_data['port'] is None
            else f"select.spa_filter_time_{int(filter_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "filter_time"
            if count_filter == 1 or filter_data['port'] is None
            else f"filter_time_{int(filter_data['port']) + 1}"
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
        return "mdi:clock-outline"

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
                # Sestavit čas z hour a minute
                hour = filter_comp.get('hour', 0)
                minute = filter_comp.get('minute', 0)
                time_str = f"{hour:02d}:{minute:02d}"
                self._attr_current_option = time_str
                _LOGGER.debug("Updated Filter Time %s: %s", self._filter_data["port"], time_str)

    async def _try_set_filter_time(self, time_str: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení času filtru s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            # Převedení času na hodiny a minuty
            hour, minute = map(int, time_str.split(':'))
            
            # Získání numOfIntervals z aktuálních dat filtru
            data = self._shared_data.data
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            
            if not filter_comp:
                _LOGGER.error("Filter component not found for port %s", self._filter_data["port"])
                return False
                
            # Převedení durationMinutes na 15minutové násobky
            duration_minutes = filter_comp.get("durationMinutes", 120)  # Default 2 hodiny
            num_of_intervals = duration_minutes // 15  # Převedení na 15minutové násobky
            
            # Pokud je duration větší než 12 hodin (48 × 15min), nastavit default na 2 hodiny (8 × 15min)
            if num_of_intervals > 48:  # 12 hodin = 48 × 15min
                num_of_intervals = 8   # 2 hodiny = 8 × 15min
            
            # Volání API pro nastavení času filtru
            response_data = await self._shared_data._client.setFilterCycle(
                int(self._filter_data["port"]),
                num_of_intervals,
                time_str
            )
            
            if response_data is None:
                _LOGGER.warning("Function setFilterCycle, parameter %s is not supported", time_str)
                return False
            
            if response_data:
                # Najít odpovídající FILTER v odpovědi
                filter_comp = next(
                    (
                        comp
                        for comp in response_data["components"]
                        if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                    ),
                    None,
                )
                
                if filter_comp:
                    # Sestavit čas z odpovědi
                    response_hour = filter_comp.get('hour', 0)
                    response_minute = filter_comp.get('minute', 0)
                    response_time_str = f"{response_hour:02d}:{response_minute:02d}"
                    
                    if response_time_str == time_str:
                        self._attr_current_option = time_str
                        _LOGGER.info(
                            "Úspěšně nastaven čas filtru %s na %s%s",
                            self._filter_data["port"],
                            time_str,
                            " (2. pokus)" if is_retry else ""
                        )
                        return True
                    else:
                        _LOGGER.warning(
                            "Filter %s time was not set. Expected: %s, Current: %s%s",
                            self._filter_data["port"],
                            time_str,
                            response_time_str,
                            " (2. pokus)" if is_retry else ""
                        )
                        return False
                else:
                    _LOGGER.error("Filter %s was not found in response", self._filter_data["port"])
                    return False
            else:
                _LOGGER.error("No API response for filter %s", self._filter_data["port"])
                return False
            
        except Exception as e:
            _LOGGER.error(
                "Error setting filter time %s to %s: %s",
                self._filter_data["port"],
                time_str,
                str(e)
            )
            return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna času filtru a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            
            # První pokus
            success = await self._try_set_filter_time(option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit čas filtru %s na %s", self._filter_data["port"], option)
                success = await self._try_set_filter_time(option, True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error setting filter time (port %s) to %s: %s", self._filter_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()

class SpaFilterDurationSelect(SpaSelectBase):
    """Select entity for spa filter duration."""
    
    def __init__(self, shared_data, device_info, filter_data, count_filter):
        self._shared_data = shared_data
        self._filter_data = filter_data
        self._attr_options = shared_data._client.createDurationOptions()  # Použít metodu z ControlMySpa
        self._attr_should_poll = False  # Data jsou sdílena, posluchač
        self._attr_current_option = None
        self._attr_device_info = device_info
        self._attr_icon = "mdi:timer-outline"
        self._attr_unique_id = (
            f"select.spa_filter_duration"
            if count_filter == 1 or filter_data['port'] is None
            else f"select.spa_filter_duration_{int(filter_data['port']) + 1}"
        )
        self._attr_translation_key = (
            "filter_duration"
            if count_filter == 1 or filter_data['port'] is None
            else f"filter_duration_{int(filter_data['port']) + 1}"
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
        return "mdi:timer-outline"

    def _minutes_to_duration_string(self, minutes):
        """Převede minuty na řetězec délky (např. 75 -> '1h 15m')."""
        if minutes < 60:
            return f"{minutes}m"
        else:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours}h"
            else:
                return f"{hours}h {remaining_minutes}m"

    def _duration_string_to_minutes(self, duration_str):
        """Převede řetězec délky na minuty (např. '1h 15m' -> 75)."""
        total_minutes = 0
        
        # Zpracování hodin
        if 'h' in duration_str:
            hours_part = duration_str.split('h')[0]
            total_minutes += int(hours_part) * 60
        
        # Zpracování minut
        if 'm' in duration_str:
            minutes_part = duration_str.split('m')[0]
            if 'h' in minutes_part:
                minutes_part = minutes_part.split('h ')[-1]
            total_minutes += int(minutes_part)
        
        return total_minutes

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
                # Převedení durationMinutes na řetězec
                duration_minutes = filter_comp.get('durationMinutes', 120)
                duration_str = self._minutes_to_duration_string(duration_minutes)
                self._attr_current_option = duration_str
                _LOGGER.debug("Updated Filter Duration %s: %s (%d minutes)", 
                             self._filter_data["port"], duration_str, duration_minutes)

    async def _try_set_filter_duration(self, duration_str: str, is_retry: bool = False) -> bool:
        """Pokus o nastavení délky filtru s možností opakování."""
        self._is_processing = True  # Zneplatnění tlačítka
        self.async_write_ha_state()
        
        try:
            # Převedení řetězce na minuty
            duration_minutes = self._duration_string_to_minutes(duration_str)
            
            # Získání aktuálního času filtru
            data = self._shared_data.data
            filter_comp = next(
                (
                    comp
                    for comp in data["components"]
                    if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                ),
                None,
            )
            
            if not filter_comp:
                _LOGGER.error("Filter component not found for port %s", self._filter_data["port"])
                return False
                
            # Sestavit aktuální čas
            hour = filter_comp.get('hour', 0)
            minute = filter_comp.get('minute', 0)
            time_str = f"{hour:02d}:{minute:02d}"
            
            # Převedení na 15minutové násobky
            num_of_intervals = duration_minutes // 15
            
            # Volání API pro nastavení délky filtru
            response_data = await self._shared_data._client.setFilterCycle(
                int(self._filter_data["port"]),
                num_of_intervals,
                time_str
            )
            
            if response_data is None:
                _LOGGER.warning("Function setFilterCycle, parameter %s is not supported", duration_str)
                return False
            
            if response_data:
                # Najít odpovídající FILTER v odpovědi
                filter_comp = next(
                    (
                        comp
                        for comp in response_data["components"]
                        if comp["componentType"] == "FILTER" and comp["port"] == self._filter_data["port"]
                    ),
                    None,
                )
                
                if filter_comp:
                    # Zkontrolovat, jestli se délka nastavila správně
                    response_duration_minutes = filter_comp.get('durationMinutes', 0)
                    response_duration_str = self._minutes_to_duration_string(response_duration_minutes)
                    
                    if response_duration_str == duration_str:
                        self._attr_current_option = duration_str
                        _LOGGER.info(
                            "Úspěšně nastavena délka filtru %s na %s%s",
                            self._filter_data["port"],
                            duration_str,
                            " (2. pokus)" if is_retry else ""
                        )
                        return True
                    else:
                        _LOGGER.warning(
                            "Filter %s duration was not set. Expected: %s, Current: %s%s",
                            self._filter_data["port"],
                            duration_str,
                            response_duration_str,
                            " (2. pokus)" if is_retry else ""
                        )
                        return False
                else:
                    _LOGGER.error("Filter %s was not found in response", self._filter_data["port"])
                    return False
            else:
                _LOGGER.error("No API response for filter %s", self._filter_data["port"])
                return False
            
        except Exception as e:
            _LOGGER.error(
                "Error setting filter duration %s to %s: %s",
                self._filter_data["port"],
                duration_str,
                str(e)
            )
            return False
        finally:
            self._is_processing = False  # Obnovení tlačítka
            self.async_write_ha_state()

    async def async_select_option(self, option: str):
        """Změna délky filtru a odeslání do zařízení."""
        if option not in self._attr_options:
            return

        try:
            self._shared_data.pause_updates()
            
            # První pokus
            success = await self._try_set_filter_duration(option)
            
            # Druhý pokus pokud první selhal
            if not success:
                _LOGGER.info("Zkouším znovu nastavit délku filtru %s na %s", self._filter_data["port"], option)
                success = await self._try_set_filter_duration(option, True)
                
            await self._shared_data.async_force_update()
        except Exception as e:
            _LOGGER.error("Error setting filter duration (port %s) to %s: %s", self._filter_data["port"], option, str(e))
            raise
        finally:
            self._shared_data.resume_updates()
