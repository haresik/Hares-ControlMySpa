import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .ControlMySpa import ControlMySpa
from .const import DOMAIN
from .options_flow import ControlMySpaOptionsFlowHandler
from .flow_helpers import (
    async_verify_spa_dashboard,
    build_available_spas,
    log_spa_list,
    resolve_spa_id,
    spa_selection_schema_dict,
)

_LOGGER = logging.getLogger(__name__)


class ControlMySpaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._username = None
        self._password = None
        self._update_interval = None
        self._spa_client = None
        self._reconfigure_entry = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            self._update_interval = user_input.get("updateintervalminutes", 1)

            _LOGGER.info("Config flow login for user=%s", self._username)
            self._spa_client = ControlMySpa(self._username, self._password)

            await self._spa_client.init_session()
            isLogin = await self._spa_client.login()

            if isLogin:
                _LOGGER.info("Config flow login OK, showing spa selection")
                # Pokračujeme na další krok - výběr spa
                return await self.async_step_select_spa()
            else:
                _LOGGER.error("Config flow login failed for user=%s", self._username)
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

    async def async_step_reconfigure(self, user_input=None):
        """Znovu vybrat vanu u existující integrace."""
        self._reconfigure_entry = self._resolve_reconfigure_entry()
        if not self._reconfigure_entry:
            _LOGGER.error("Reconfigure started but config entry was not found")
            return self.async_abort(reason="unknown")

        self._username = self._reconfigure_entry.data["username"]
        self._password = self._reconfigure_entry.data["password"]
        self._update_interval = self._reconfigure_entry.data.get("updateintervalminutes", 1)
        _LOGGER.info(
            "Reconfigure for user=%s stored spa_id=%s",
            self._username,
            self._reconfigure_entry.data.get("spa_id"),
        )

        if self._spa_client is None:
            self._spa_client = ControlMySpa(self._username, self._password)
            await self._spa_client.init_session()
            if not await self._spa_client.login():
                _LOGGER.error("Reconfigure login failed for user=%s", self._username)
                return self.async_abort(reason="cannot_login")
            _LOGGER.info("Reconfigure login OK, showing spa selection")

        return await self.async_step_select_spa(user_input)

    def _resolve_reconfigure_entry(self):
        """Najde entry pro reconfigure i na starších verzích HA."""
        try:
            return self._get_reconfigure_entry()
        except (AttributeError, ValueError, KeyError):
            _LOGGER.debug("async_get_reconfigure_entry failed, falling back to context")
        entry_id = self.context.get("entry_id")
        if entry_id:
            return self.hass.config_entries.async_get_entry(entry_id)
        return None

    async def async_step_select_spa(self, user_input=None):
        errors = {}

        # Seznam van z cloudu; None znamená výpadek API, prázdný list je platný
        spas = await self._spa_client.getSpaOwner()
        current_spa_id = None
        if self._reconfigure_entry:
            current_spa_id = self._reconfigure_entry.data.get("spa_id")
        log_spa_list("select_spa", spas, current_spa_id)
        available_spas = build_available_spas(spas, current_spa_id)

        if spas is None:
            errors["base"] = "connection_error"

        if user_input is not None:
            spa_id = resolve_spa_id(user_input)
            if not spa_id:
                _LOGGER.error("select_spa submitted without spa_id")
                errors["base"] = "spa_id_required"
            elif not await async_verify_spa_dashboard(self._spa_client, spa_id):
                errors["base"] = "dashboard_error"
            else:
                return await self._async_finish_spa_selection(spa_id)

        _LOGGER.info(
            "Showing select_spa form: %s option(s), errors=%s",
            len(available_spas),
            errors or None,
        )
        return self.async_show_form(
            step_id="select_spa",
            data_schema=vol.Schema(spa_selection_schema_dict(available_spas, current_spa_id)),
            errors=errors,
        )

    async def _async_finish_spa_selection(self, spa_id: str):
        """Vytvoří novou entry, nebo při reconfigure přepíše spa_id."""
        if self._reconfigure_entry:
            _LOGGER.info(
                "Reconfigure saving spa_id=%s (was %s)",
                spa_id,
                self._reconfigure_entry.data.get("spa_id"),
            )
            # Update + reload zvlášť, ať to naskočí i když předchozí setup spadl na starém ID
            self.hass.config_entries.async_update_entry(
                self._reconfigure_entry,
                data={**self._reconfigure_entry.data, "spa_id": spa_id},
            )
            await self.hass.config_entries.async_reload(self._reconfigure_entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        _LOGGER.info("Creating config entry with spa_id=%s user=%s", spa_id, self._username)
        return self.async_create_entry(
            title="ControlMySpa",
            data={
                "username": self._username,
                "password": self._password,
                "updateintervalminutes": self._update_interval,
                "spa_id": spa_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ControlMySpaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ControlMySpaOptionsFlowHandler()
