import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN


class ControlMySpaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for ControlMySpa."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    def _get_component_count(self, component_type, prefix, default_min):
        """Získá počet komponent z shared_data, pokud jsou dostupná.
        
        Args:
            component_type: Typ komponenty ("PUMP", "HEATER" nebo "BLOWER")
            prefix: Prefix pro konfigurační klíč ("pump_", "heater_" nebo "blower_")
            default_min: Minimální výchozí počet (3 pro pumpy, 2 pro heatery, 2 pro blowery)
        
        Returns:
            Počet komponent (maximálně 3)
        """
        try:
            # Zkusit získat data z hass.data
            hass = getattr(self, 'hass', None)
            if hass and DOMAIN in hass.data and self.config_entry.entry_id in hass.data[DOMAIN]:
                data = hass.data[DOMAIN][self.config_entry.entry_id]
                shared_data = data.get("data")
                if shared_data and shared_data.data and "components" in shared_data.data:
                    components = [
                        component for component in shared_data.data["components"]
                        if component.get("componentType") == component_type
                    ]
                    component_count = len(components) if components else (1 if component_type == "HEATER" else 0)
                    return min(component_count, 3)  # Maximálně 3 komponenty
        except Exception:
            pass
        # Pokud nejsou data dostupná, vrátit výchozí počet nebo z aktuální konfigurace
        current_config = self.config_entry.options or {}
        # Zjistit, kolik komponent máme v konfiguraci
        max_component = 0
        for key in current_config.keys():
            if key.startswith(prefix) and key.endswith("_power_watts"):
                try:
                    component_num = int(key.split("_")[1])
                    max_component = max(max_component, component_num)
                except (ValueError, IndexError):
                    pass
        return min(max(max_component, default_min), 3)  # Minimálně default_min, maximálně 3

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        
        if user_input is not None:
            # Uložení konfigurace
            return self.async_create_entry(title="", data=user_input)

        # Získání aktuálních hodnot z konfigurace
        current_config = self.config_entry.options or {}
        
        # Dynamické vytvoření schématu podle počtu pump, heaterů, blowerů a circulation pumps
        pump_count = self._get_component_count("PUMP", "pump_", 3)
        heater_count = self._get_component_count("HEATER", "heater_", 2)
        blower_count = self._get_component_count("BLOWER", "blower_", 2)
        circulation_pump_count = self._get_component_count("CIRCULATION_PUMP", "circulation_pump_", 1)
        
        schema_dict = {}
        
        # Přidat položky pro pumpy
        # Home Assistant automaticky použije překlady z translations/{lang}.json
        # pod klíčem options.step.init.data.pump_{i}_power_watts
        for i in range(1, pump_count + 1):
            config_key = f"pump_{i}_power_watts"
            schema_dict[vol.Optional(
                config_key,
                default=current_config.get(config_key, 2200)
            )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=10000))
        
        # Přidat položky pro heatery
        # Home Assistant automaticky použije překlady z translations/{lang}.json
        # pod klíčem options.step.init.data.heater_{i}_power_watts
        for i in range(1, heater_count + 1):
            config_key = f"heater_{i}_power_watts"
            schema_dict[vol.Optional(
                config_key,
                default=current_config.get(config_key, 2800)
            )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=15000))
        
        # Přidat položky pro blowery
        # Home Assistant automaticky použije překlady z translations/{lang}.json
        # pod klíčem options.step.init.data.blower_{i}_power_watts
        for i in range(1, blower_count + 1):
            config_key = f"blower_{i}_power_watts"
            schema_dict[vol.Optional(
                config_key,
                default=current_config.get(config_key, 900)
            )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=10000))
        
        # Přidat položky pro circulation pumps
        # Home Assistant automaticky použije překlady z translations/{lang}.json
        # pod klíčem options.step.init.data.circulation_pump_{i}_power_watts
        for i in range(1, circulation_pump_count + 1):
            config_key = f"circulation_pump_{i}_power_watts"
            schema_dict[vol.Optional(
                config_key,
                default=current_config.get(config_key, 400)
            )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=10000))
        
        # Přidat cenu elektřiny
        #schema_dict[vol.Optional(
        #    "energy_price_per_kwh",
        #    default=current_config.get("energy_price_per_kwh", 5.0)
        #)] = vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0))
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors
        )


