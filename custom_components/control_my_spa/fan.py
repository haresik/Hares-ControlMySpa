from homeassistant.components.fan import FanEntity, FanEntityFeature
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    data = hass.data[DOMAIN][config_entry.entry_id]
    shared_data = data["data"]
    device_info = data["device_info"]
    unique_id_suffix = data["unique_id_suffix"]
    client = data["client"]

    if not shared_data.data:
        return False

    # Grab all PUMP components from the API payload
    pumps = [
        component for component in shared_data.data["components"]
        if component["componentType"] == "PUMP"
    ]

    _LOGGER.debug("Filtered components for Fan - Pumps: %d", len(pumps))

    entities = [SpaPumpFan(shared_data, device_info, pump, len(pumps), unique_id_suffix) for pump in pumps]

    if entities:
        async_add_entities(entities, True)

    _LOGGER.debug("START Fan control_my_spa - %d entities created", len(entities))

    for entity in entities:
        shared_data.register_subscriber(entity)


class SpaPumpFan(FanEntity):
    """Native Fan entity for multi-speed Spa Jets."""

    _attr_has_entity_name = True

    def __init__(self, shared_data, device_info, pump_data, pump_count, unique_id_suffix=""):
        self._shared_data = shared_data
        self._pump_data = pump_data
        self._attr_device_info = device_info
        # Push-driven via register_subscriber; don't let HA poll on its own timer too.
        self._attr_should_poll = False

        # Configure unique IDs and translation keys to match en.json
        base_id = (
            f"fan.spa_pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"fan.spa_pump_{int(pump_data['port']) + 1}"
        )
        self._attr_unique_id = f"{base_id}{unique_id_suffix}"
        self._attr_translation_key = (
            "pump"
            if pump_count == 1 or pump_data['port'] is None
            else f"pump_{int(pump_data['port']) + 1}"
        )
        self.entity_id = self._attr_unique_id

        # Map cloud available values to Fan presets (stripping out "OFF" as a preset)
        raw_values = pump_data.get("availableValues", ["OFF", "LOW", "HIGH"])
        self._attr_preset_modes = [val for val in raw_values if val != "OFF"]

        # Enable Standard On/Off + Presets UI in Home Assistant
        self._attr_supported_features = (
            FanEntityFeature.PRESET_MODE |
            FanEntityFeature.TURN_OFF |
            FanEntityFeature.TURN_ON
        )

    def _get_current_pump_data(self):
        """Helper to extract live pump state from shared payload."""
        data = self._shared_data.data
        if not data:
            return None
        return next(
            (comp for comp in data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
            None
        )

    async def async_update(self):
        """Update Home Assistant state from background cloud payload."""
        pump = self._get_current_pump_data()
        if pump:
            val = pump.get("value", "OFF")
            self._attr_is_on = (val != "OFF")
            self._attr_preset_mode = val if val != "OFF" else None
            _LOGGER.debug("Updated Fan/Pump %s: %s", self._pump_data["port"], val)
        else:
            self._attr_is_on = False
            self._attr_preset_mode = None

    async def _try_set_pump_state(self, target_state: str, is_retry: bool = False) -> bool:
        """Push target state directly to the Balboa API and check the instant response."""
        try:
            device_number = int(self._pump_data["port"])
            response_data = await self._shared_data._client.setJetState(device_number, target_state)

            if response_data is None:
                _LOGGER.warning("setJetState returned None for target %s", target_state)
                return False

            # Verify the API accepted our change
            pump = next(
                (comp for comp in response_data["components"] if comp["componentType"] == "PUMP" and comp["port"] == self._pump_data["port"]),
                None
            )
            new_state = pump["value"] if pump else "OFF"

            if new_state == target_state:
                self._attr_is_on = (new_state != "OFF")
                self._attr_preset_mode = new_state if new_state != "OFF" else None
                _LOGGER.info("Successfully changed pump %s to %s", self._pump_data["port"], target_state)
                return True
            else:
                _LOGGER.warning("Pump change rejected or stepped sequentially. Expected: %s, Got: %s", target_state, new_state)
                return False
        finally:
            # Push the (possibly updated) state to HA. No availability toggle,
            # so the entity never flashes 'unavailable' mid-command.
            self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """HA Interface: User selected a specific speed (LOW or HIGH) from dashboard."""
        if preset_mode not in self._attr_preset_modes:
            _LOGGER.error("Invalid preset mode %s selected", preset_mode)
            return

        try:
            self._shared_data.pause_updates()
            success = await self._try_set_pump_state(preset_mode)
            if not success:
                await self._try_set_pump_state(preset_mode, True)
            await self._shared_data.async_force_update()
        finally:
            self._shared_data.resume_updates()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        """HA Interface: User clicked the primary Turn On toggle."""
        # Default to the HIGHEST speed if turned on generically (full jets).
        target = preset_mode if preset_mode else (self._attr_preset_modes[-1] if self._attr_preset_modes else "HIGH")

        try:
            self._shared_data.pause_updates()
            success = await self._try_set_pump_state(target)
            if not success:
                await self._try_set_pump_state(target, True)
            await self._shared_data.async_force_update()
        finally:
            self._shared_data.resume_updates()

    async def async_turn_off(self, **kwargs) -> None:
        """HA Interface: User clicked the primary Turn Off toggle."""
        try:
            self._shared_data.pause_updates()
            success = await self._try_set_pump_state("OFF")
            if not success:
                await self._try_set_pump_state("OFF", True)
            await self._shared_data.async_force_update()
        finally:
            self._shared_data.resume_updates()
