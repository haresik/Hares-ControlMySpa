# import voluptuous as vol
# from homeassistant import config_entries
# from .const import DOMAIN

# class ControlMySpaOptionsFlowHandler(config_entries.OptionsFlow):
#     """Zpracov�n� mo�nost� konfigurace pro ControlMySpa."""

#     def __init__(self, config_entry):
#         self.config_entry = config_entry

#     async def async_step_init(self, user_input=None):
#         """Prvn� krok konfigurace mo�nost�."""
#         if user_input is not None:
#             # Ulo�� nov� nastaven�
#             return self.async_create_entry(title="", data=user_input)

#         # Na�ten� aktu�ln� hodnoty tempRange
#         options = self.config_entry.options
#         temp_range = options.get("temp_range", "HIGH")

#         # Definice formul��e pro v�b�r tempRange
#         return self.async_show_form(
#             step_id="init",
#             data_schema=vol.Schema({
#                 vol.Required("temp_range", default=temp_range): vol.In(["HIGH", "LOW"]),
#             }),
#         )
