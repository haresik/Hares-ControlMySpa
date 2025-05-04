# import voluptuous as vol
# from homeassistant import config_entries
# from .const import DOMAIN

# class ControlMySpaOptionsFlowHandler(config_entries.OptionsFlow):
#     """Zpracování možností konfigurace pro ControlMySpa."""

#     def __init__(self, config_entry):
#         self.config_entry = config_entry

#     async def async_step_init(self, user_input=None):
#         """První krok konfigurace možností."""
#         if user_input is not None:
#             # Uloží nové nastavení
#             return self.async_create_entry(title="", data=user_input)

#         # Naètení aktuální hodnoty tempRange
#         options = self.config_entry.options
#         temp_range = options.get("temp_range", "HIGH")

#         # Definice formuláøe pro výbìr tempRange
#         return self.async_show_form(
#             step_id="init",
#             data_schema=vol.Schema({
#                 vol.Required("temp_range", default=temp_range): vol.In(["HIGH", "LOW"]),
#             }),
#         )
