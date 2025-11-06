import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .ControlMySpa import ControlMySpa
from .const import DOMAIN
from .options_flow import ControlMySpaOptionsFlowHandler

class ControlMySpaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    
    def __init__(self):
        self._username = None
        self._password = None
        self._update_interval = None
        self._spa_client = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            self._update_interval = user_input.get("updateintervalminutes", 1)

            self._spa_client = ControlMySpa(self._username, self._password)

            await self._spa_client.init_session()
            isLogin = await self._spa_client.login()

            if isLogin:
                # Pokračujeme na další krok - výběr spa
                return await self.async_step_select_spa()
            else:
                errors["base"] = "cannot_login"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Optional("updateintervalminutes", default=1): int,
            }),
            errors=errors
        )

    async def async_step_select_spa(self, user_input=None):
        errors = {}

        # Získáme seznam spa zařízení
        spas = await self._spa_client.getSpaOwner()
        
        if spas is None:
            errors["base"] = "connection_error"
            return self.async_show_form(
                step_id="select_spa",
                errors=errors
            )

        if user_input is not None:
            # Uložíme vybrané spa ID a vytvoříme konfigurační záznam
            return self.async_create_entry(
                title="ControlMySpa",
                data={
                    "username": self._username,
                    "password": self._password,
                    "updateintervalminutes": self._update_interval,
                    "spa_id": user_input["spa_id"]
                }
            )

        # Vytvoříme seznam dostupných spa zařízení pro výběr
        available_spas = {
            spa["_id"]: f"{spa['serialNumber']} {spa['alias'] if spa['alias'] else ''}"
            for spa in spas
        }

        return self.async_show_form(
            step_id="select_spa",
            data_schema=vol.Schema({
                vol.Required("spa_id"): vol.In(available_spas)
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ControlMySpaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ControlMySpaOptionsFlowHandler(config_entry)

