"""Simulátor dashboardu z testData. Cloud se nevolá."""

import asyncio
import json
import logging
import os
import time

import aiofiles

from . import const

_LOGGER = logging.getLogger(__name__)

_STEP_DELAY = 5

_COMPONENT_TYPES = {
    "jet": "PUMP",
    "light": "LIGHT",
    "blower": "BLOWER",
    "microsilk": "MICROSILK",
}


def is_test_mode():
    """True, když const.TEST_MODE míří na soubor testData/Data*.json."""
    return bool(const.TEST_MODE and str(const.TEST_MODE).startswith("Data"))


class SpaTestSimulator:
    """Drží jeden snapshot testData a při příkazu změní stav komponenty."""

    def __init__(self):
        self._dashboard = None

    def activate(self, client):
        """Nastaví falešné přihlášení, aby setup prošel bez cloudu."""
        client.tokenData = {
            "access_token": "test",
            "timestamp": int(time.time() * 1000),
            "expires_in": 86400,
        }
        client.userInfo = {"email": client.email, "testMode": const.TEST_MODE}
        _LOGGER.warning("ControlMySpa TEST_MODE=%s, příkazy jdou do simulátoru", const.TEST_MODE)
        return True

    async def get_spa(self, client):
        """Vrátí stav ze zapamatovaného snapshotu."""
        dashboard = await self._load()
        if dashboard is None:
            return None
        return client.constructCurrentState(dashboard)

    async def post_and_refresh(self, client, endpoint, payload):
        """Upraví snapshot, počká jako cloud a vrátí nový stav."""
        await self._load()
        self._apply(endpoint, payload)
        await asyncio.sleep(_STEP_DELAY)
        return await self.get_spa(client)

    async def _load(self):
        if self._dashboard is not None:
            return self._dashboard
        test_file_path = os.path.join(
            os.path.dirname(__file__), "testData", f"{const.TEST_MODE}.json"
        )
        try:
            async with aiofiles.open(test_file_path, "r", encoding="utf-8") as handle:
                raw = json.loads(await handle.read())
        except FileNotFoundError:
            _LOGGER.error("Test file not found: %s", test_file_path)
            return None
        except json.JSONDecodeError as err:
            _LOGGER.error("Error parsing JSON file: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Error loading test data: %s", err)
            return None
        self._dashboard = raw.get("data")
        _LOGGER.info("Loaded test data from %s", test_file_path)
        return self._dashboard

    def _apply(self, endpoint, payload):
        if self._dashboard is None or not str(endpoint).endswith("component-state"):
            return
        component_type = _COMPONENT_TYPES.get(payload.get("componentType"))
        if component_type is None:
            return
        component = _find_component(
            self._dashboard, component_type, payload.get("deviceNumber")
        )
        if component is None:
            _LOGGER.warning(
                "Test simulator: component %s device %s not found",
                component_type,
                payload.get("deviceNumber"),
            )
            return
        if payload.get("componentType") == "jet":
            _cycle_value(component)
        else:
            state = payload.get("state")
            if state in component.get("availableValues", []):
                component["value"] = state
        _LOGGER.info(
            "Test simulator: %s port %s -> %s",
            component.get("componentType"),
            component.get("port"),
            component.get("value"),
        )


def _find_component(dashboard, component_type, device_number):
    for component in dashboard.get("components", []):
        if component.get("componentType") != component_type:
            continue
        if device_number is None or str(component.get("port")) == str(device_number):
            return component
    return None


def _cycle_value(component):
    values = component.get("availableValues") or []
    if not values:
        return
    current = component.get("value")
    try:
        index = values.index(current)
    except ValueError:
        index = -1
    component["value"] = values[(index + 1) % len(values)]
